"""
construir_bases_locais_ibge.py
==============================
Constrói as CAMADAS DERIVADAS LOCAIS de inteligência geoespacial a partir das bases oficiais
IBGE BC250 v2025 (nacional) + BC100 (UFs: AC, AL, BA, ES, GO/DF, RS, RR, SE — ver UF_MAP) baixadas em
`data/brasil/ibge/`.

Saída (write-once, versionada por manifesto):
    data/brasil/ibge/derivadas/
        pontes.parquet               # tra_ponte_p + tra_ponte_l  (BC250 + BC100)
        travessias.parquet           # tra_travessia_p + tra_travessia_l (balsas/cruzamentos)
        hidrovias.parquet            # hdv_trecho_hidroviario_l  (hidrovias navegáveis)
        atracadouros_terminal.parquet# hdv_atracadouro_terminal_p/l (terminais/atracadouros)
        complexos_portuarios.parquet # hdv_complexo_portuario_p (portos)
        eclusas.parquet              # hdv_eclusa_p
        sinalizacao.parquet          # hdv_sinalizacao_p (sinalização de navegação)
        rodovias.parquet             # rod_trecho_rodoviario_l (rede viária)
        ferrovias.parquet            # fer_trecho_ferroviario_l (rede ferroviária)
        massas_dagua.parquet         # hid_massa_dagua_a (corpos d'água)
        drenagem.parquet             # hid_trecho_drenagem_l (trechos de drenagem, decimados)
        municipios.parquet           # lml_municipio_a (polígonos municipais IBGE)
        manifest.json                # catálogo de extração (fontes, contagens, CRS, datas)

Sem geopandas/GDAL: usa `pyshp` (100% Python) + pandas/pyarrow. Geometria normalizada em
WKB big-endian, CRS EPSG:4326 (SIRGAS2000). Cada registro ganha cols auxiliares:
tipo_geom, lon, lat (ponto representativo), xmin/ymin/xmax/ymax e a origem da feição.

Requer pyshp (build-time):  pip install pyshp
Execução:  py -X utf8 construir_bases_locais_ibge.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import struct
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import shapefile as pyshp
except ImportError:  # pragma: no cover
    raise SystemExit("Falta pyshp. Instale com: pip install pyshp")

ROOT = os.path.dirname(os.path.abspath(__file__))
IBGE = os.path.join(ROOT, "data", "brasil", "ibge")
BC250_EXTRACT = os.path.join(IBGE, "bc250", "versao2025", "shapefiles", "extract")
BC100 = os.path.join(IBGE, "bc100")
OUT = os.path.join(IBGE, "derivadas")

CRS = "EPSG:4326"
DEC_PONTOS_DRENAGEM = 12      # drenagem tem ~1,9M feições → geometria decimada
DEC_PONTOS_PADRAO = 256       # demais camadas: praticamente sem decimação

UF_MAP = {
    "acre": "AC", "alagoas": "AL", "bcal": "BA", "espirito_santo": "ES",
    "go_df": "GO", "rio_grande_do_sul": "RS", "roraima": "RR", "sergipe": "SE",
}

# Camadas: nome_parquet -> [(shp_layer, tipo_geom, max_pts_dec, campos_relevantes), ...]
CAMADAS = {
    "pontes": [
        ("tra_ponte_p", "PONTO", DEC_PONTOS_PADRAO,
         ["nome", "matconstr", "operaciona", "situacaofi", "largura", "extensao",
          "nrfaixas", "nrpistas", "posicaopis", "tipopavime", "tipoponte",
          "vaolivreho", "vaovertica", "cargasupor"]),
        ("tra_ponte_l", "LINHA", DEC_PONTOS_PADRAO,
         ["nome", "matconstr", "operaciona", "situacaofi", "largura", "extensao",
          "nrfaixas", "nrpistas", "posicaopis", "tipopavime", "tipoponte",
          "vaolivreho", "vaovertica", "cargasupor"]),
    ],
    "travessias": [
        ("tra_travessia_p", "PONTO", DEC_PONTOS_PADRAO, ["nome", "tipotraves", "tipouso", "tipoembarc"]),
        ("tra_travessia_l", "LINHA", DEC_PONTOS_PADRAO, ["nome", "tipotraves", "tipouso", "tipoembarc"]),
    ],
    "hidrovias": [
        ("hdv_trecho_hidroviario_l", "LINHA", DEC_PONTOS_PADRAO,
         ["nome", "operaciona", "situacaofi", "regime", "extensaotr", "caladomaxs"]),
    ],
    "atracadouros_terminal": [
        ("hdv_atracadouro_terminal_p", "PONTO", DEC_PONTOS_PADRAO,
         ["nome", "tipoatraca", "administra", "matconstr", "operaciona", "situacaofi", "aptidaoope"]),
        ("hdv_atracadouro_terminal_l", "LINHA", DEC_PONTOS_PADRAO,
         ["nome", "tipoatraca", "administra", "matconstr", "operaciona", "situacaofi", "aptidaoope"]),
    ],
    "complexos_portuarios": [
        ("hdv_complexo_portuario_p", "PONTO", DEC_PONTOS_PADRAO,
         ["nome", "modaluso", "administra", "jurisdicao", "concession", "operaciona",
          "situacaofi", "tipotransp", "tipocomple", "portosempa"]),
    ],
    "eclusas": [
        ("hdv_eclusa_p", "PONTO", DEC_PONTOS_PADRAO,
         ["nome", "desnivel", "largura", "extensao", "calado", "matconstr", "operaciona", "situacaofi"]),
    ],
    "sinalizacao": [
        ("hdv_sinalizacao_p", "PONTO", DEC_PONTOS_PADRAO, ["nome", "tiposinal", "operaciona", "situacaofi"]),
    ],
    "rodovias": [
        ("rod_trecho_rodoviario_l", "LINHA", DEC_PONTOS_PADRAO,
         ["tipovia", "jurisdicao", "administra", "concession", "revestimen", "operaciona",
          "situacaofi", "canteirodi", "nrpistas", "nrfaixas", "trafego", "tipopavime",
          "sigla", "acostament", "codtrechor", "limitevelo", "emperimetr"]),
    ],
    "ferrovias": [
        ("fer_trecho_ferroviario_l", "LINHA", DEC_PONTOS_PADRAO,
         ["nome", "codtrechof", "posicaorel", "tipotrecho", "bitola", "eletrifica",
          "nrlinhas", "jurisdicao", "administra", "concession", "operaciona", "situacaofi"]),
    ],
    "massas_dagua": [
        ("hid_massa_dagua_a", "POLIGONO", DEC_PONTOS_PADRAO,
         ["nome", "tipomassad", "regime", "salgada", "dominialid", "artificial", "possuitrec"]),
    ],
    "drenagem": [
        ("hid_trecho_drenagem_l", "LINHA", DEC_PONTOS_DRENAGEM,
         ["nome", "tipotrecho", "navegavel", "larguramed", "regime", "encoberto"]),
    ],
    "municipios": [
        ("lml_municipio_a", "POLIGONO", DEC_PONTOS_PADRAO,
         ["nome", "geocodigo", "anoderefer"]),
    ],
}

# Valores numéricos inválidos (sentinelas DBF) -> NaN
DBF_NULL = {"0", "-9999", ""}


# ----------------------------------------------------------------------------- WKB
def _wkb_point(x, y):
    return struct.pack(">BIdd", 0, 1, float(x), float(y))


def _ring(pts):
    return b"".join(struct.pack(">dd", float(x), float(y)) for x, y in pts)


def _wkb_linestring(pts):
    return struct.pack(">BII", 0, 2, len(pts)) + _ring(pts)


def _wkb_polygon(rings):
    return struct.pack(">BII", 0, 3, len(rings)) + b"".join(
        struct.pack(">I", len(r)) + _ring(r) for r in rings
    )


def _decimate(pts, max_pts):
    if len(pts) <= max_pts:
        return pts
    idx = np.linspace(0, len(pts) - 1, max_pts).round().astype(int)
    return [pts[int(i)] for i in idx]


def _pontos_shape(shape):
    """Devolve a lista aplanada de (x, y) da geometria (PONTO/LINHA/POLIGONO)."""
    if hasattr(shape, "x"):
        return [(shape.x, shape.y)]
    return list(shape.points)


def _rings_shape(shape):
    """Devolve as linhas (rings) do polígono, a partir de shape.parts."""
    pts = list(shape.points)
    if not pts:
        return []
    parts = list(shape.parts)
    stops = list(parts[1:]) + [len(pts)]
    return [pts[a:b] for a, b in zip(parts, stops)]


def _wkb_e_shape(shape, kind, max_pts):
    pts = _pontos_shape(shape)
    if not pts:
        return None, None
    if kind == "PONTO":
        x, y = pts[0]
        return _wkb_point(x, y), (x, y)
    if kind == "LINHA":
        dec = _decimate(pts, max_pts)
        return _wkb_linestring(dec), _ponto_repr(dec)
    if kind == "POLIGONO":
        rings = [_decimate(r, max_pts) for r in _rings_shape(shape)]
        rings = [r for r in rings if r]
        if not rings:
            return None, None
        allpts = [p for r in rings for p in r]
        return _wkb_polygon(rings), _ponto_repr(allpts)
    raise ValueError(kind)


def _ponto_repr(pts):
    """Ponto representativo: vértice mais próximo do centro do bbox da geometria."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    best = min(range(len(pts)), key=lambda i: (pts[i][0] - cx) ** 2 + (pts[i][1] - cy) ** 2)
    return (float(xs[best]), float(ys[best]))


def _norm_attr(v, is_num):
    if v is None:
        return np.nan if is_num else None
    if is_num:
        try:
            s = str(v).strip()
            if s in DBF_NULL:
                return np.nan
            f = float(s)
            return f if f == f else np.nan
        except (TypeError, ValueError):
            return np.nan
    s = str(v).strip()
    return s or None


def _fields_tipos(reader):
    tipos = {}
    for f in reader.fields[1:]:
        tipos[f[0]] = f[1] in ("N", "F", "L", "B", "I")  # numérico?
    return tipos


def _abre_reader(arq_shp):
    """Abre o shapefile decodificando o DBF corretamente (utf-8/.cpg ou latin-1)."""
    last_err = None
    for enc in (None, "latin1"):
        r = None
        try:
            r = pyshp.Reader(arq_shp, encoding=enc)
            for _ in zip(range(300), r.iterShapeRecords()):
                pass
            return r
        except Exception as e:  # noqa: BLE001 - tenta próxima codificação
            last_err = e
            if r is not None:
                try:
                    r.close()
                except Exception:  # noqa: BLE001
                    pass
    raise last_err


def _extrai_camada(arq_shp, campos, kind, max_pts, fonte_base, fonte_uf, fonte_versao,
                   chunk=200_000, n_chunks_report=20):
    rows = []
    reader = _abre_reader(arq_shp)
    tipos = _fields_tipos(reader)
    shape = reader.shapeTypeName  # 'POINT' | 'POLYLINE' | 'POLYGON'
    n = len(reader)
    n_chunks = 0
    for sr in reader.iterShapeRecords():
        rec, shp = sr.record, sr.shape
        d = dict(zip([f[0] for f in reader.fields[1:]], rec))
        wkb, repr_pt = _wkb_e_shape(shp, kind, max_pts)
        if wkb is None:
            continue
        if hasattr(shp, "bbox") and shp.bbox:
            xmin, ymin, xmax, ymax = shp.bbox
        else:
            xmin, xmax, ymin, ymax = repr_pt[0], repr_pt[0], repr_pt[1], repr_pt[1]
        row = {
            "tipo_geom": kind,
            "geometry_wkb": wkb,
            "lon": repr_pt[0], "lat": repr_pt[1],
            "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
            "fonte_base": fonte_base, "fonte_uf": fonte_uf, "fonte_versao": fonte_versao,
        }
        for c in campos:
            row[c] = _norm_attr(d.get(c), tipos.get(c, False))
        # garante coluna 'nome' mesmo se o shapefile não tiver
        if "nome" not in campos:
            row["nome"] = _norm_attr(d.get("nome"), False)
        rows.append(row)
        if len(rows) >= chunk:
            n_chunks += 1
            if n_chunks % n_chunks_report == 0:
                sys.stdout.write("    ...%d arquivos (%d feições)\n" % (os.path.basename(arq_shp), n_chunks * chunk))
                sys.stdout.flush()
            yield rows
            rows = []
    if rows:
        yield rows


COL_FIXAS = ["tipo_geom", "geometry_wkb", "lon", "lat",
             "xmin", "ymin", "xmax", "ymax", "fonte_base", "fonte_uf", "fonte_versao"]


def _versao_do_caminho(path):
    """Extrai o rótulo de versão do diretório do extract (ex.: 'versao2023' -> '2023')."""
    dirs = os.path.dirname(path).replace("\\", "/").split("/")
    for d in reversed(dirs):
        if d.startswith("versao") and len(d) > 6:
            return d[len("versao"):]
    # UFs sem marcador 'versao' nos diretórios
    fallback = {
        "\\bc100\\roraima\\": "2016",
        "\\bc100\\bcal\\": "2016",
        "\\bc100\\sergipe\\": "2019",
    }
    for k, v in fallback.items():
        if k.replace("/", "\\") in path or k in path:
            return v
    return "desconhecida"


def _num_versao(path):
    m = re.search(r"versao(\d+)", path)
    return int(m.group(1)) if m else 0


def descobre_bc100_camadas() -> dict:
    """Mapeia (uf) -> {camada_shp: (versao_label, path)} escolhendo a versão mais nova por UF."""
    map_uf = {}
    for uf in UF_MAP:
        ufdir = os.path.join(BC100, uf)
        if not os.path.isdir(ufdir):
            continue
        cand = {}
        for shp in glob.glob(os.path.join(ufdir, "**", "*.shp"), recursive=True):
            base = os.path.splitext(os.path.basename(shp))[0].lower()
            if base not in {l for grp in CAMADAS.values() for l, _, _, _ in grp}:
                continue
            cur = cand.get(base)
            if cur is None or _num_versao(shp) > _num_versao(cur[1]):
                cand[base] = (_versao_do_caminho(shp), shp)
        if cand:
            map_uf[uf] = cand
    return map_uf


def coleta_layer(camada, campos, kind, max_pts, fonte_base, fonte_uf, fonte_versao, arqs):
    frames = []
    for arq in arqs:
        for chunk in _extrai_camada(arq, campos, kind, max_pts, fonte_base, fonte_uf, fonte_versao):
            frames.append(pd.DataFrame(chunk))
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def build():
    os.makedirs(OUT, exist_ok=True)
    bc100 = descobre_bc100_camadas()
    t0 = datetime.now(timezone.utc)
    manifest = {"versao": "1.0", "crs": CRS, "extraido_em_utc": t0.isoformat(),
                "fontes": {}, "camadas": {}}

    manifest["fontes"]["bc250"] = {
        "base": "BC250 v2025", "path": os.path.relpath(BC250_EXTRACT, ROOT),
        "versao": "2025", "url": "https://geoftp.ibge.gov.br/cartas_e_mapas/bases_cartograficas_continuas/bc250/versao2025/shapefiles/bc_250_shapefiles_2026_03_03.zip",
    }
    bc100_fontes = {}
    for uf, layers in bc100.items():
        versoes = sorted({v for v, _ in layers.values()})
        bc100_fontes[uf] = {"versoes": versoes}
    manifest["fontes"]["bc100"] = {
        "base": "BC100 por UF", "path": os.path.relpath(BC100, ROOT), "ufs": bc100_fontes,
        "urls": ["https://geoftp.ibge.gov.br/cartas_e_mapas/bases_cartograficas_continuas/bc100/"],
    }

    for camada, grupos in CAMADAS.items():
        print(">> %s" % camada)
        # --- fontes BC250
        arqs_250 = []
        campos_finais = grupos[0][3]
        for layer, kind, max_pts, campos in grupos:
            p = os.path.join(BC250_EXTRACT, layer + ".shp")
            if os.path.exists(p):
                arqs_250.append((layer, kind, max_pts, p))
        df = None
        for layer, kind, max_pts, arq in arqs_250:
            df2 = coleta_layer(camada, campos_finais, kind, max_pts,
                               "BC250", "BR", "2025", [arq])
            if df2 is not None:
                df = df2 if df is None else pd.concat([df, df2], ignore_index=True)

        # --- fontes BC100 (camada mais nova por UF que possuir a camada)
        for uf, layers in bc100.items():
            sub = []
            for layer, kind, max_pts, campos in grupos:
                item = layers.get(layer)
                if item:
                    sub.append(item)
            if not sub:
                continue
            for versao, arq in sub:
                df2 = coleta_layer(camada, grupos[0][3], grupos[0][1], grupos[0][2],
                                   "BC100", UF_MAP[uf], versao, [arq])
                if df2 is not None:
                    df = df2 if df is None else pd.concat([df, df2], ignore_index=True)

        if df is None or df.empty:
            manifest["camadas"][camada] = {"registros": 0}
            print("   (0 registros)")
            continue

        # colunas fixas em ordem estável
        campos_finais = grupos[0][3]
        extra = [c for c in ["nome"] if c not in campos_finais]
        cols = COL_FIXAS + campos_finais + extra
        cols = [c for c in cols if c in df.columns]
        df = df[cols]
        parq = os.path.join(OUT, camada + ".parquet")
        df.to_parquet(parq, index=False)
        manifest["camadas"][camada] = {
            "arquivo": os.path.basename(parq),
            "registros": int(len(df)),
            "contagem_por_fonte": {
                "BC250": int((df["fonte_base"] == "BC250").sum()),
                "BC100": int((df["fonte_base"] == "BC100").sum()),
            },
        }
        n_geral = int(len(df))
        n_bc100 = int((df["fonte_base"] == "BC100").sum())
        print("   -> %d registros (BC250=%d, BC100=%d)" % (n_geral, n_geral - n_bc100, n_bc100))

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\nConcluído em %.1fs. Saída: %s" % ((datetime.now(timezone.utc) - t0).total_seconds(), OUT))


if __name__ == "__main__":
    build()