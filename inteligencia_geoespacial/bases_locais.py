"""
Bases Locais - camadas derivadas das bases oficiais IBGE (BC250/BC100).

Este módulo consome as bases locais geradas por `construir_bases_locais_ibge.py`
(Parquet em `data/brasil/ibge/derivadas/`) e oferece consultas geoespaciais
sem dependências binárias (sem GDAL/geopandas/shapely):

    carregar_base(camada)                  -> DataFrame completo (em cache)
    municipio_do_ponto(lat, lon)           -> município IBGE que contém o ponto
    mais_proximos(camada, lon, lat, ...)   -> feições dentro de um raio (km)
    camadas_disponiveis()                  -> nomes das camadas derivadas
    manifest()                             -> catálogo de extração (manifest.json)

Geometrias são WKB big-endian (EPSG:4326) — POINT, LINESTRING e POLYGON com
anéis (multi-partes são anéis, buracos detectados por orientação/contimento).
"""

from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_PROJ_ROOT = _PKG_ROOT.parent
_DERIVADAS = _PROJ_ROOT / "data" / "brasil" / "ibge" / "derivadas"

DISPONIVEIS = (
    "pontes",
    "travessias",
    "hidrovias",
    "atracadouros_terminal",
    "complexos_portuarios",
    "eclusas",
    "sinalizacao",
    "rodovias",
    "ferrovias",
    "massas_dagua",
    "drenagem",
    "municipios",
)

# camadas pesadas: leitura sob demanda com filtro no disco (não em memória inteira)
_PESADAS = frozenset({"rodovias", "drenagem", "massas_dagua", "ferrovias"})


def _caminho(camada: str) -> Path:
    if camada not in DISPONIVEIS:
        raise ValueError(
            "Camada desconhecida %r. Disponíveis: %s" % (camada, ", ".join(DISPONIVEIS))
        )
    p = _DERIVADAS / (camada + ".parquet")
    if not p.exists():
        raise FileNotFoundError(
            "Camada derivada não encontrada em %s. Gere com construir_bases_locais_ibge.py." % p
        )
    return p


def camadas_disponiveis() -> list:
    """Devolve as camadas existentes em data/brasil/ibge/derivadas/."""
    if not _DERIVADAS.exists():
        return []
    return [c for c in DISPONIVEIS if (_DERIVADAS / (c + ".parquet")).exists()]


def manifest() -> dict:
    path = _DERIVADAS / "manifest.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- WKB
def _deco_wkb(wkb: bytes):
    """Decodifica WKB big/little-endian → (x, y) | [(x, y), ...] | [[(x, y), ...]].

    Saída: POINT→tupla; LINESTRING→lista de pontos; POLYGON→lista de anéis.
    """
    if wkb is None:
        return None
    bo = wkb[0]
    endian = "<" if bo == 1 else ">"
    (t,) = struct.unpack_from(endian + "I", wkb, 1)
    off = 5
    if t == 1:
        (x, y) = struct.unpack_from(endian + "dd", wkb, off)
        return (x, y)
    (n,) = struct.unpack_from(endian + "I", wkb, off)
    off += 4
    pts = list(struct.unpack_from(endian + "d" * (2 * n), wkb, off))
    out = [(pts[i], pts[i + 1]) for i in range(0, 2 * n, 2)]
    if t == 2:
        return out
    if t == 3:
        rings = []
        for _ in range(n):
            (m,) = struct.unpack_from(endian + "I", wkb, off)
            off += 4
            rp = list(struct.unpack_from(endian + "d" * (2 * m), wkb, off))
            off += 16 * m
            rings.append([(rp[i], rp[i + 1]) for i in range(0, 2 * m, 2)])
        return rings
    raise ValueError("Tipo WKB não suportado: %d" % t)


def _latlon_to_xy(pt, cos_lat):
    return pt[0] * cos_lat, pt[1]


def _area_sinalizada(rings):
    """Área assinada (shoelace) em graus para cada anel."""
    areas = []
    for r in rings:
        if len(r) < 3:
            areas.append(0.0)
            continue
        s = 0.0
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            s += x1 * y2 - x2 * y1
        areas.append(0.5 * s)
    return areas


def _pip_ring(px, py, ring):
    """Point-in-polygon clássico (ray casting) para um anel de (lon, lat)."""
    dentro = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1):
            dentro = not dentro
    return dentro


def _ponto_em_wkb(lon, lat, wkb) -> bool:
    rings = _deco_wkb(wkb)
    if not rings:
        return False
    areas = _area_sinalizada(rings)
    maior = max(range(len(rings)), key=lambda i: abs(areas[i]))
    sinal_outer = 1.0 if areas[maior] >= 0 else -1.0
    outers = [i for i, a in enumerate(areas) if a * sinal_outer > 0]
    buracos = [i for i, a in enumerate(areas) if a * sinal_outer <= 0]
    if not outers:
        outers = list(range(len(rings)))
        buracos = []
    # associa cada buraco ao menor outer que o contém
    buraco_de = {}
    for h in buracos:
        vertice = rings[h][0]
        cont = [o for o in outers if _pip_ring(vertice[0], vertice[1], rings[o])]
        if cont:
            menor = min(cont, key=lambda o: abs(areas[o]))
            buraco_de.setdefault(menor, []).append(h)
    for o in outers:
        if not _pip_ring(lon, lat, rings[o]):
            continue
        if all(not _pip_ring(lon, lat, rings[h]) for h in buraco_de.get(o, [])):
            return True
    return False


# --------------------------------------------------------------------------- leitura
@lru_cache(maxsize=None)
def carregar_base(camada: str):
    """Carrega a camada Parquet completa (com cache). Para camadas pesadas use `_ler`/`_busca_com_filtro`."""
    import pandas as pd

    return pd.read_parquet(_caminho(camada))


def _ler(camada: str, colunas=None):
    import pandas as pd

    return pd.read_parquet(_caminho(camada), columns=colunas)


def _busca_com_filtro(camada: str, lon: float, lat: float, raio_km: float, colunas):
    """Leitura de disco usando filtros de bbox (pyarrow), sem carregar a camada inteira."""
    import pandas as pd

    import numpy as np

    dlat = raio_km / 110.574
    cos_lat = max(0.0001, abs(np.cos(np.radians(lat))))
    dlon = min(raio_km / (111.320 * cos_lat), 180.0)
    filtros = [
        ("xmin", "<=", lon + dlon),
        ("xmax", ">=", lon - dlon),
        ("ymin", "<=", lat + dlat),
        ("ymax", ">=", lat - dlat),
    ]
    return pd.read_parquet(_caminho(camada), columns=colunas, filters=filtros)


def _haversine(lon, lat, lons, lats):
    import numpy as np

    R = 6371.0088
    la1 = np.radians(lat)
    la2 = np.radians(np.asarray(lats, dtype=float))
    dlat = la2 - la1
    dlon = np.radians(np.asarray(lons, dtype=float) - lon)
    h = np.sin(dlat / 2.0) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * R * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


# --------------------------------------------------------------------------- consultas
def municipio_do_ponto(lat: float, lon: float) -> dict:
    """Município IBGE que contém (lat, lon). Retorna dict ou {} se fora do Brasil."""
    import numpy as np

    df = carregar_base("municipios")
    m = df[(df.ymin <= lat) & (df.ymax >= lat) & (df.xmin <= lon) & (df.xmax >= lon)]
    if m.empty:
        return {}
    for _, row in m.iterrows():
        if _ponto_em_wkb(float(lon), float(lat), row.geometry_wkb):
            return {
                "geocodigo": str(row.geocodigo),
                "nome": row.nome,
                "fonte": "IBGE BC250 v2025",
                "lon": float(row.lon),
                "lat": float(row.lat),
            }
    return {}


def mais_proximos(camada: str, lon: float, lat: float, raio_km: float, limite: int = 10,
                  filtros: dict | None = None, refinar_linhas: bool = True) -> list:
    """Retorna as feições de `camada` a até `raio_km` de (lon, lat), ordenadas por distância.

    Args:
        camada: nome da camada (ver DISPONIVEIS).
        lon/lat: ponto de referência (EPSG:4326).
        raio_km: raio de busca em km.
        limite: número máximo de resultados (mínimo 1).
        filtros: igualdade de colunas (ex.: {"tipoembarc": "Balsa"}).
        refinar_linhas: recalcula a distância ponto-segmento para linhas/polígonos
            (rank mais fiel; um pouco mais caro).
    """
    import pandas as pd

    colunas = ["geometry_wkb", "lon", "lat", "xmin", "ymin", "xmax", "ymax",
               "tipo_geom", "nome", "fonte_base", "fonte_uf"]
    extra = sorted({c for c in (filtros or {}) if c not in colunas})
    colunas = colunas + extra

    df = _busca_com_filtro(camada, lon, lat, raio_km, colunas)
    if df.empty:
        return []
    if filtros:
        for c, v in filtros.items():
            df = df[df[c].astype(object).eq(v)]
        if df.empty:
            return []
    df["distancia_km"] = _haversine(lon, lat, df.lon.to_numpy(), df.lat.to_numpy())
    df = df[df.distancia_km <= raio_km].sort_values("distancia_km")
    if df.empty:
        return []

    if refinar_linhas:
        pool = df.head(min(len(df), max(limite * 80, 512)))
        calc = []
        for _, r in pool.iterrows():
            if r.tipo_geom == "PONTO":
                calc.append((float(r.distancia_km), r))
                continue
            d_bbox = _dist_bbox_km(lon, lat, r.xmin, r.ymin, r.xmax, r.ymax)
            if len(calc) >= limite and d_bbox >= calc[limite - 1][0]:
                continue
            d = _distancia_geometria(lon, lat, r.geometry_wkb)
            calc.append((d if d is not None else float(r.distancia_km), r))
        calc.sort(key=lambda t: t[0])
        return [{**dict(r), "distancia_km": d} for d, r in calc[:limite]]

    return [dict(row) for row in df.head(limite).to_dict(orient="records")]


def _dist_bbox_km(lon, lat, xmin, ymin, xmax, ymax):
    """Distância mínima (km) entre o ponto e o bbox da feição, projeção local."""
    import numpy as np

    cos_lat = np.cos(np.radians(lat))
    px, py = lon * cos_lat, lat
    xmin_p, xmax_p = xmin * cos_lat, xmax * cos_lat
    dx = 0.0 if xmin_p <= px <= xmax_p else min(abs(px - xmin_p), abs(px - xmax_p))
    dy = 0.0 if ymin <= py <= ymax else min(abs(py - ymin), abs(py - ymax))
    return float((dx * dx + dy * dy) ** 0.5 * 111.32)


def _distancia_geometria(lon, lat, wkb):
    """Distância (km) do ponto ao linestring/polígono, projeção equiretangular local."""
    if wkb is None:
        return None
    pts = _deco_wkb(wkb)
    if not pts:
        return None
    if isinstance(pts, tuple):  # POINT
        return float(_haversine(lon, lat, [pts[0]], [pts[1]])[0])
    rings = pts if isinstance(pts[0], list) else [pts]  # POLYGON→anéis; LINESTRING→1 linha
    import numpy as np

    cos_lat = np.cos(np.radians(lat))
    px, py = lon * cos_lat, lat
    melhor2 = float("inf")
    for ring in rings:
        arr = np.asarray(ring, dtype=float)
        if arr.ndim != 2 or len(arr) < 2:
            continue
        a = arr[:-1]
        b = arr[1:]
        aim = a.copy()
        aim[:, 0] *= cos_lat
        bim = b.copy()
        bim[:, 0] *= cos_lat
        dx = bim[:, 0] - aim[:, 0]
        dy = bim[:, 1] - aim[:, 1]
        l2 = dx * dx + dy * dy
        t = np.zeros(len(dx))
        nz = l2 > 0
        t[nz] = np.clip(((px - aim[:, 0]) * dx + (py - aim[:, 1]) * dy)[nz] / l2[nz], 0.0, 1.0)
        cx = aim[:, 0] + t * dx
        cy = aim[:, 1] + t * dy
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        m = float(d2.min()) if len(d2) else float("inf")
        if m < melhor2:
            melhor2 = m
    if melhor2 == float("inf"):
        return None
    return float(melhor2 ** 0.5 * 111.32)