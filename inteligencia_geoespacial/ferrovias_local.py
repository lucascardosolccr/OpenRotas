# -*- coding: utf-8 -*-
"""
ferrovias_local.py — ferrovia de referência de um ponto, LOCAL e sem rede
=========================================================================
Usa o índice nacional de ferrovias (ferrovias_index.parquet, versionado no repo) para dizer qual a
ferrovia mais próxima de um ponto — operadora/linha, bitola e situação — via cKDTree local.
Enriquece o contexto de infraestrutura das rotas. Fail-open (sem asset/scipy → None).
"""
from __future__ import annotations

import os
from functools import lru_cache

_FERRO_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "brasil", "ibge", "derivadas", "ferrovias_index.parquet")


@lru_cache(maxsize=1)
def _indice():
    try:
        import numpy as _np
        import pandas as _pd
        from scipy.spatial import cKDTree as _KD
        _df = _pd.read_parquet(_FERRO_INDEX, columns=["lat", "lon", "via", "bitola", "situacao"])
        if _df is None or _df.empty:
            return None
        _pts = _np.radians(_df[["lat", "lon"]].to_numpy(dtype=float))
        _rows = _df[["via", "bitola", "situacao"]].astype(str).to_dict("records")
        return (_rows, _KD(_pts))
    except Exception:
        return None


def ferrovia_mais_proxima(lat, lon, max_km=8.0):
    """Ferrovia mais próxima de um ponto (índice local). Devolve {via,bitola,situacao,distancia_km} ou None."""
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
        return {"via": _r.get("via", ""), "bitola": _r.get("bitola", ""),
                "situacao": _r.get("situacao", ""), "distancia_km": round(_dk, 1)}
    except Exception:
        return None
