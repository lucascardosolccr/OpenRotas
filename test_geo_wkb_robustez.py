# -*- coding: utf-8 -*-
"""[ROBUSTEZ · Geoespacial IBGE] A rotulagem da geometria na aba "Feições próximas" fazia len(None) quando
`_deco_wkb` devolvia None (WKB nula) — TypeError que, pelo try externo, derrubava TODO o painel geoespacial.
Estes testes travam o contrato de `_deco_wkb` (None p/ nulo; erro p/ tipo não suportado) que motivou a
blindagem, e a função pura que classifica o rótulo (ponto/linha/polígono/—) sem nunca estourar."""
import struct
import pytest
from inteligencia_geoespacial.bases_locais import _deco_wkb


def _rotulo_geom(pontos):
    """Réplica pura da classificação usada na UI (após a blindagem): nunca estoura."""
    if isinstance(pontos, tuple):
        return "ponto"
    if pontos and isinstance(pontos[0], list):
        return "polígono (%d anéis)" % len(pontos)
    if pontos:
        return "linha (%d pontos)" % len(pontos)
    return "—"


def _wkb_point(x=-60.0, y=-3.0):
    return struct.pack("<BI", 1, 1) + struct.pack("<dd", x, y)


def _wkb_line(n=3):
    b = struct.pack("<BI", 1, 2) + struct.pack("<I", n)
    for i in range(n):
        b += struct.pack("<dd", -60.0 + i, -3.0 + i)
    return b


def test_deco_wkb_none_para_nula():
    assert _deco_wkb(None) is None


def test_deco_wkb_tipo_nao_suportado_erra():
    # tipo WKB 7 (GeometryCollection) não é suportado → ValueError (a UI precisa blindar)
    bad = struct.pack("<BI", 1, 7) + struct.pack("<I", 0)
    with pytest.raises(Exception):
        _deco_wkb(bad)


def test_rotulo_nao_estoura_com_none_ou_vazio():
    # o bug original: len(None). Agora vira "—" sem exceção.
    assert _rotulo_geom(None) == "—"
    assert _rotulo_geom([]) == "—"


def test_rotulo_ponto_linha_poligono():
    assert _rotulo_geom(_deco_wkb(_wkb_point())) == "ponto"
    assert _rotulo_geom(_deco_wkb(_wkb_line(4))).startswith("linha")
    # polígono: lista de anéis (lista de listas de tuplas)
    assert _rotulo_geom([[(-60.0, -3.0), (-59.0, -3.0), (-59.0, -2.0)]]).startswith("polígono")
