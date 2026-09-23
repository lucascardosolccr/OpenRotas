# -*- coding: utf-8 -*-
"""
geo_kdtree.py — vizinho mais próximo EXATO na esfera (helper compartilhado)
===========================================================================
Antes cada índice (rios/rodovias/ferrovias) montava um cKDTree em (lat, lon) radianos com distância
euclidiana 2D. Isso NÃO é a distância no terreno: 1 rad de longitude vale menos km que 1 rad de latitude
fora do equador (fator cos(lat)); no Sul do Brasil (cos ≈ 0,83) o "vizinho mais próximo" podia sair errado.

Aqui projetamos cada ponto na ESFERA UNITÁRIA 3D (x,y,z). A distância euclidiana 3D é a CORDA, função
monótona da distância geodésica → o vizinho mais próximo é EXATO em qualquer latitude. Depois convertemos a
corda de volta para km. Sem dependência de projeção local nem de aproximação por latitude.
"""
from __future__ import annotations

import math

_R_KM = 6371.0088


def to_xyz(lat, lon):
    """(graus) → coordenadas na esfera unitária, shape (N, 3). Aceita escalares ou arrays."""
    import numpy as _np
    _la = _np.radians(_np.asarray(lat, dtype=float))
    _lo = _np.radians(_np.asarray(lon, dtype=float))
    _cl = _np.cos(_la)
    return _np.column_stack([_cl * _np.cos(_lo), _cl * _np.sin(_lo), _np.sin(_la)])


def build(lats, lons):
    """Constrói o cKDTree 3D a partir de arrays de lat/lon (graus). Levanta se scipy ausente (chamador trata)."""
    from scipy.spatial import cKDTree as _KD
    return _KD(to_xyz(lats, lons))


def nearest(tree, lat, lon):
    """(indice, distancia_km) do vizinho mais próximo — EXATO. Converte a corda 3D em distância geodésica."""
    import numpy as _np
    _d, _i = tree.query(to_xyz([lat], [lon]), k=1)
    _dc = float(min(2.0, _np.atleast_1d(_d)[0]))          # corda ∈ [0, 2]
    _idx = int(_np.atleast_1d(_i)[0])
    return _idx, 2.0 * _R_KM * math.asin(_dc / 2.0)
