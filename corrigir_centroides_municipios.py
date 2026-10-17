"""
corrigir_centroides_municipios.py
=================================
REPARO DE DADO (reprodutível) do ponto representativo (lon/lat) de municípios na base derivada
`data/brasil/ibge/derivadas/municipios.parquet`.

Motivo: o gerador antigo (`construir_bases_locais_ibge.py`, _ponto_repr) escolhia o "vértice mais
próximo do centro do bbox". Para municípios que incluem ILHAS OCEÂNICAS distantes (ex.: Vitória/ES
possui Trindade e Martim Vaz, ~1.100 km mar adentro), o centro do bbox cai no oceano e o ponto
representativo ia parar no Atlântico — geocodificando a cidade no lugar errado. Brasília/DF e
Vitória/ES eram os casos visíveis.

Este script recomputa o ponto representativo a partir da PRÓPRIA geometria já armazenada
(`geometry_wkb`), usando o CENTRÓIDE DO MAIOR ANEL (o continente) — o mesmo critério robusto agora
usado pelo gerador — e corrige SOMENTE as linhas cujo ponto se move materialmente (> LIMIAR_KM),
deixando as demais byte a byte idênticas. Preserva schema/ordem/tipos do parquet (só altera lon/lat).

Uso:
    python3 corrigir_centroides_municipios.py            # dry-run (só relatório)
    python3 corrigir_centroides_municipios.py --aplicar  # grava a correção no parquet
"""
from __future__ import annotations

import math
import os
import struct
import sys

CAMINHO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "brasil", "ibge", "derivadas", "municipios.parquet")
LIMIAR_KM = 20.0


def _parse_wkb_rings(b):
    """Rings [(x,y),...] de um WKB Polygon(3)/MultiPolygon(6). [] se não for polígono."""
    try:
        b = bytes(b)
        order = "<" if b[0] == 1 else ">"
        gtype = struct.unpack(order + "I", b[1:5])[0]
        pos = 5
        rings = []
        if gtype == 3:
            nr = struct.unpack(order + "I", b[pos:pos + 4])[0]; pos += 4
            for _ in range(nr):
                npt = struct.unpack(order + "I", b[pos:pos + 4])[0]; pos += 4
                r = []
                for _ in range(npt):
                    x, y = struct.unpack(order + "dd", b[pos:pos + 16]); pos += 16
                    r.append((x, y))
                rings.append(r)
            return rings
        if gtype == 6:
            npoly = struct.unpack(order + "I", b[pos:pos + 4])[0]; pos += 4
            for _ in range(npoly):
                o2 = "<" if b[pos] == 1 else ">"; pos += 1
                pos += 4  # type do sub-polígono
                nr = struct.unpack(o2 + "I", b[pos:pos + 4])[0]; pos += 4
                for _ in range(nr):
                    npt = struct.unpack(o2 + "I", b[pos:pos + 4])[0]; pos += 4
                    r = []
                    for _ in range(npt):
                        x, y = struct.unpack(o2 + "dd", b[pos:pos + 16]); pos += 16
                        r.append((x, y))
                    rings.append(r)
            return rings
    except Exception:
        return []
    return []


def _area(r):
    n = len(r); a = 0.0
    for i in range(n):
        x0, y0 = r[i]; x1, y1 = r[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def _centroide(r):
    n = len(r)
    if n < 3:
        return (sum(p[0] for p in r) / n, sum(p[1] for p in r) / n)
    A = cx = cy = 0.0
    for i in range(n):
        x0, y0 = r[i]; x1, y1 = r[(i + 1) % n]
        cr = x0 * y1 - x1 * y0; A += cr; cx += (x0 + x1) * cr; cy += (y0 + y1) * cr
    if abs(A) < 1e-12:
        return (sum(p[0] for p in r) / n, sum(p[1] for p in r) / n)
    A *= 0.5
    return (cx / (6.0 * A), cy / (6.0 * A))


def _maior_anel(wkb):
    rings = _parse_wkb_rings(wkb)
    melhor = None; melhor_a = -1.0
    for r in rings:
        if len(r) < 3:
            continue
        a = _area(r)
        if a > melhor_a:
            melhor_a = a; melhor = r
    return melhor


def _hav(lo0, la0, lo1, la1):
    R = 6371.0
    p1 = math.radians(la0); p2 = math.radians(la1)
    dphi = math.radians(la1 - la0); dl = math.radians(lo1 - lo0)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, x))))


def main(aplicar=False):
    import pyarrow as pa
    import pyarrow.parquet as pq
    t = pq.read_table(CAMINHO)
    nomes = t.column("nome").to_pylist()
    gc = t.column("geocodigo").to_pylist()
    lon = t.column("lon").to_pylist()
    lat = t.column("lat").to_pylist()
    wkb = t.column("geometry_wkb").to_pylist()
    novo_lon = list(lon); novo_lat = list(lat)
    mudancas = []
    for i in range(len(wkb)):
        anel = _maior_anel(wkb[i])
        if anel is None or lon[i] is None or lat[i] is None:
            continue
        # O ponto representativo está no CORPO PRINCIPAL (maior anel = continente)?
        # Mede a menor distância do ponto atual aos vértices do maior anel. Se o ponto é um
        # vértice do próprio corpo principal → ~0 km (ok, não mexe). Se está longe (no oceano
        # ou numa ilha distante que também pertence ao município) → é o defeito → corrige.
        dmin = min(_hav(lon[i], lat[i], vx, vy) for (vx, vy) in anel)
        if dmin > LIMIAR_KM:
            rp = _centroide(anel)
            novo_lon[i] = float(rp[0]); novo_lat[i] = float(rp[1])
            mudancas.append((nomes[i], gc[i], round(lon[i], 3), round(lat[i], 3),
                             round(rp[0], 3), round(rp[1], 3), round(dmin)))
    print("Linhas corrigidas (ponto fora do corpo principal, > %.0f km): %d de %d"
          % (LIMIAR_KM, len(mudancas), len(wkb)))
    for m in sorted(mudancas, key=lambda x: -x[6]):
        print("  %-28s %s  (%.3f,%.3f) -> (%.3f,%.3f)  %d km" %
              (m[0], m[1], m[2], m[3], m[4], m[5], m[6]))
    if aplicar and mudancas:
        i_lon = t.schema.get_field_index("lon")
        i_lat = t.schema.get_field_index("lat")
        t2 = t.set_column(i_lon, "lon", pa.array(novo_lon, type=t.schema.field("lon").type))
        t2 = t2.set_column(i_lat, "lat", pa.array(novo_lat, type=t.schema.field("lat").type))
        pq.write_table(t2, CAMINHO)
        print("GRAVADO: %s" % CAMINHO)
    elif aplicar:
        print("Nada a gravar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(aplicar=("--aplicar" in sys.argv)))
