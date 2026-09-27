# -*- coding: utf-8 -*-
"""
construir_overview_hidro_nacional.py
====================================
Gera o OVERVIEW hidrográfico NACIONAL — um asset leve, versionado no repositório, que permite ao
"Mapa Hidrográfico Nacional" cobrir o Brasil INTEIRO (de Roraima ao Chuí) mesmo sem baixar o Parquet
denso de drenagem (451 MB, camada pesada baixada sob demanda).

Como cobre tudo sem ser pesado: AMOSTRAGEM ESPACIAL. O território é dividido numa grade; em cada célula
mantemos os N rios de maior extensão (e os maiores corpos d'água). Assim toda região do país fica
representada — em vez de truncar pela ordem do arquivo (que enviesava para um só canto).

Entrada:  data/brasil/ibge/derivadas/drenagem.parquet + massas_dagua.parquet  (BC250; drenagem é pesada)
Saída:    data/brasil/ibge/derivadas/hidro_nacional_overview.json.gz  (~0,4 MB, versionado no git)

Uso:  python construir_overview_hidro_nacional.py
Regenere sempre que atualizar as bases BC250.
"""
import gzip
import json
import os
import struct

import pandas as pd
import pyarrow.parquet as pq

DER = os.path.join("data", "brasil", "ibge", "derivadas")
OUT = os.path.join(DER, "hidro_nacional_overview.json.gz")

# Parâmetros da amostragem (grade em graus e nº de feições por célula) — ajuste fino de densidade × tamanho.
# [HIDRO-DENSIDADE] Grade REFINADA e mais feições por célula (era 0.9°/top4 · 1.3°/top1) para que as
# janelas REGIONAIS do Mapa Hidrográfico (recorte do overview quando a drenagem densa de 431 MB não foi
# baixada) mostrem MUITO mais rios — cobertura nacional máxima sem depender da camada pesada. A saída é
# ordenada por EXTENSÃO (maiores primeiro), então o teto de render da visão nacional mantém os rios mais
# significativos e os recortes regionais recebem toda a densidade.
RIOS_CELULA_DEG, RIOS_POR_CELULA, RIOS_MAX_PTS = 0.5, 6, 32
MASSAS_CELULA_DEG, MASSAS_POR_CELULA, MASSAS_MAX_PTS = 0.8, 2, 24


def _deco_wkb(w):
    """WKB → ('L', pts) linha | ('A', [anéis]) polígono | ('P', [pt]). None se nulo/insuportado."""
    if not w:
        return None
    endian = "<" if w[0] == 1 else ">"
    t = struct.unpack_from(endian + "I", w, 1)[0]
    off = 5
    if t == 1:
        x, y = struct.unpack_from(endian + "dd", w, off)
        return ("P", [(x, y)])
    if t == 2:
        n = struct.unpack_from(endian + "I", w, off)[0]; off += 4
        pts = struct.unpack_from(endian + "d" * (2 * n), w, off)
        return ("L", [(pts[i], pts[i + 1]) for i in range(0, 2 * n, 2)])
    if t == 3:
        n = struct.unpack_from(endian + "I", w, off)[0]; off += 4
        rings = []
        for _ in range(n):
            m = struct.unpack_from(endian + "I", w, off)[0]; off += 4
            rp = struct.unpack_from(endian + "d" * (2 * m), w, off); off += 16 * m
            rings.append([(rp[i], rp[i + 1]) for i in range(0, 2 * m, 2)])
        return ("A", rings)
    return None


def _decimar(pts, lim):
    if len(pts) <= lim:
        return pts
    passo = max(1, len(pts) // lim)
    s = pts[::passo]
    if s[-1] != pts[-1]:
        s.append(pts[-1])
    return s


def _indices_por_grade(camada, cell_deg, por_celula):
    """Posições das feições de maior extensão por célula de grade (cobre o país todo)."""
    bx = pd.read_parquet(os.path.join(DER, camada + ".parquet"),
                         columns=["xmin", "ymin", "xmax", "ymax"])
    cx = (bx["xmin"] + bx["xmax"]) / 2
    cy = (bx["ymin"] + bx["ymax"]) / 2
    ext = (bx["xmax"] - bx["xmin"]).abs() + (bx["ymax"] - bx["ymin"]).abs()
    g = pd.DataFrame({"cx": (cx / cell_deg).round(), "cy": (cy / cell_deg).round(),
                      "ext": ext.fillna(0.0)}).dropna()
    sel = (g.reset_index().sort_values("ext", ascending=False)
           .groupby(["cx", "cy"], sort=False).head(por_celula))
    return sorted(int(i) for i in sel["index"].tolist()), int(len(bx)), int(sel.groupby(["cx", "cy"]).ngroups)


def _geoms(camada, idx, max_pts, so_maior_anel):
    """Lê a geometria só das posições selecionadas (por row-group, com take) e devolve polilinhas (lat,lon)."""
    pf = pq.ParquetFile(os.path.join(DER, camada + ".parquet"))
    base = ptr = 0
    out = []
    for rg in range(pf.num_row_groups):
        n = pf.metadata.row_group(rg).num_rows
        hi = base + n
        loc = []
        while ptr < len(idx) and idx[ptr] < hi:
            loc.append(idx[ptr] - base); ptr += 1
        if loc:
            ws = pf.read_row_group(rg, columns=["geometry_wkb"]).take(loc).column(0).to_pylist()
            for w in ws:
                try:
                    g = _deco_wkb(w)
                except Exception:
                    g = None
                if not g:
                    continue
                kind, geom = g
                if kind == "A":
                    rings = [max(geom, key=lambda rr: len(rr))] if (geom and so_maior_anel) else geom
                else:
                    rings = [geom]
                for r in rings:
                    pts = _decimar([[round(y, 4), round(x, 4)] for (x, y) in r], max_pts)
                    if len(pts) >= 2:
                        _las = [p[0] for p in pts]; _los = [p[1] for p in pts]
                        _ext = (max(_las) - min(_las)) + (max(_los) - min(_los))  # extensão do bbox (graus)
                        out.append((_ext, pts))
        base = hi
    # [HIDRO-DENSIDADE] ordena por EXTENSÃO desc: qualquer teto de render (visão nacional) mantém os
    # rios/corpos d'água mais significativos primeiro; os recortes regionais recebem toda a densidade.
    out.sort(key=lambda t: -t[0])
    return [pts for (_ext, pts) in out]


def main():
    ir, tot_r, cel_r = _indices_por_grade("drenagem", RIOS_CELULA_DEG, RIOS_POR_CELULA)
    im, tot_m, cel_m = _indices_por_grade("massas_dagua", MASSAS_CELULA_DEG, MASSAS_POR_CELULA)
    rios = _geoms("drenagem", ir, RIOS_MAX_PTS, so_maior_anel=True)
    massas = _geoms("massas_dagua", im, MASSAS_MAX_PTS, so_maior_anel=True)
    data = {
        "rios": rios, "massas": massas, "n_rios": len(rios), "n_massas": len(massas),
        "total_rios": tot_r, "total_massas": tot_m, "celulas_rios": cel_r,
        "grade": f"rios {RIOS_CELULA_DEG}° top{RIOS_POR_CELULA} · massas {MASSAS_CELULA_DEG}° top{MASSAS_POR_CELULA}",
        "fonte": "IBGE BC250 (drenagem + massas d'água) — amostragem espacial nacional (write-once)",
    }
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    with gzip.open(OUT, "wb", compresslevel=9) as f:
        f.write(raw)
    print("OK: %d rios (%d células) + %d corpos d'água → %s (%.2f MB gz)"
          % (len(rios), cel_r, len(massas), OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
