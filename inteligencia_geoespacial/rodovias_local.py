# -*- coding: utf-8 -*-
"""
rodovias_local.py — rodovia de referência de um ponto, LOCAL e sem rede
=======================================================================
Usa o índice nacional de rodovias significativas (rodovias_index.parquet, ~1 MB, versionado no repo) para
dizer qual a rodovia mais próxima de um ponto — sigla (BR-101…), jurisdição (Federal/Estadual) e
revestimento — sem depender do Parquet pesado (122 MB). Enriquece o contexto rodoviário das rotas.

Fail-open: sem o asset ou sem scipy, devolve None (o enriquecimento segue sem a rodovia).
"""
from __future__ import annotations

import os
from functools import lru_cache

_RODO_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "brasil", "ibge", "derivadas", "rodovias_index.parquet")


@lru_cache(maxsize=1)
def _indice():
    """(rows:list[dict], tree:cKDTree 3D) do índice de rodovias, ou None. LOCAL, sem rede."""
    try:
        import pandas as _pd
        from . import geo_kdtree as _gk
        _df = _pd.read_parquet(_RODO_INDEX, columns=["lat", "lon", "via", "jur", "rev"])
        if _df is None or _df.empty:
            return None
        _rows = _df[["via", "jur", "rev"]].astype(str).to_dict("records")
        return (_rows, _gk.build(_df["lat"].to_numpy(), _df["lon"].to_numpy()))
    except Exception:
        return None


def rodovia_mais_proxima(lat, lon, max_km=5.0):
    """Rodovia significativa mais próxima de um ponto (índice local). Devolve
    {via,jurisdicao,revestimento,distancia_km} ou None (nada dentro do raio / indisponível)."""
    _idx = _indice()
    if _idx is None:
        return None
    try:
        from . import geo_kdtree as _gk
        _rows, _tree = _idx
        _i, _dk = _gk.nearest(_tree, float(lat), float(lon))
        if max_km and _dk > float(max_km):
            return None
        _r = _rows[_i]
        return {"via": _r.get("via", ""), "jurisdicao": _r.get("jur", ""),
                "revestimento": _r.get("rev", ""), "distancia_km": round(_dk, 1)}
    except Exception:
        return None
