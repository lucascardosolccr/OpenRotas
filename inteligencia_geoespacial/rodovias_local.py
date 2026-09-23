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
    """(rows:list[dict], tree:cKDTree) do índice de rodovias, ou None. LOCAL, sem rede."""
    try:
        import numpy as _np
        import pandas as _pd
        from scipy.spatial import cKDTree as _KD
        _df = _pd.read_parquet(_RODO_INDEX, columns=["lat", "lon", "via", "jur", "rev"])
        if _df is None or _df.empty:
            return None
        _pts = _np.radians(_df[["lat", "lon"]].to_numpy(dtype=float))
        _rows = _df[["via", "jur", "rev"]].astype(str).to_dict("records")
        return (_rows, _KD(_pts))
    except Exception:
        return None


def rodovia_mais_proxima(lat, lon, max_km=5.0):
    """Rodovia significativa mais próxima de um ponto (índice local). Devolve
    {via,jurisdicao,revestimento,distancia_km} ou None (nada dentro do raio / indisponível)."""
    _idx = _indice()
    if _idx is None:
        return None
    try:
        import numpy as _np
        _rows, _tree = _idx
        _d, _i = _tree.query(_np.radians([[float(lat), float(lon)]]), k=1)
        _dk = 6371.0088 * float(_np.atleast_1d(_d)[0])
        if max_km and _dk > float(max_km):
            return None
        _r = _rows[int(_np.atleast_1d(_i)[0])]
        return {"via": _r.get("via", ""), "jurisdicao": _r.get("jur", ""),
                "revestimento": _r.get("rev", ""), "distancia_km": round(_dk, 1)}
    except Exception:
        return None
