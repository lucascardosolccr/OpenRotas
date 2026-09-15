# -*- coding: utf-8 -*-
"""Rede de segurança para o PERFIL DE VIAS do GraphHopper (GRAPHHOPPER-PERFIL): o motor devolve, por
trecho, o pavimento/classe/ambiente da via — dado antes descartado (e cuja ausência de solicitação
mantinha a detecção de balsa sempre vazia). O núcleo é PURO (pondera por distância real dos trechos) e
o round-trip do campo aditivo no `dados_graphhopper` precisa ser retrocompatível.

Roda via pytest a partir da raiz: `python3 -m pytest test_graphhopper_perfil.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402

# Path sintético fiel ao formato GraphHopper: 4 pontos [lon,lat] ~ trechos de comprimentos diferentes,
# com details cujos índices apontam para os pontos. Trecho 0-2 asfalto, 2-3 terra; 2-3 é balsa.
_PATH = {
    "distance": 3000.0,
    "points": {"coordinates": [
        [-46.60, -23.50],   # 0
        [-46.60, -23.51],   # 1  (~1.11 km ao sul)
        [-46.60, -23.52],   # 2  (~1.11 km ao sul)
        [-46.61, -23.52],   # 3  (~1.02 km a oeste)
    ]},
    "details": {
        "surface": [[0, 2, "asphalt"], [2, 3, "ground"]],
        "road_class": [[0, 2, "primary"], [2, 3, "track"]],
        "road_environment": [[2, 3, "ferry"]],
    },
}


def test_perfil_pondera_por_distancia():
    p = m._gh_perfil_rota(_PATH)
    assert p is not None
    # ~2.22 km asfalto de ~3.24 km totais → maioria asfalto; terra é o restante.
    assert p["surface"]["asphalt"] > p["surface"]["ground"]
    assert abs(sum(p["surface"].values()) - 1.0) < 1e-6
    # frac_pavimentado = fração de asfalto (única superfície pavimentada aqui)
    assert abs(p["frac_pavimentado"] - p["surface"]["asphalt"]) < 1e-6
    assert p["km"] > 3.0


def test_perfil_detecta_km_de_balsa():
    p = m._gh_perfil_rota(_PATH)
    assert p["ferry_km"] > 0.9   # o trecho 2-3 (~1 km) é balsa


def test_perfil_robusto_a_entrada_invalida():
    assert m._gh_perfil_rota(None) is None
    assert m._gh_perfil_rota({}) is None
    assert m._gh_perfil_rota({"points": {"coordinates": [[0, 0]]}, "details": {}}) is None  # < 2 pontos


def test_resumo_amigavel():
    p = m._gh_perfil_rota(_PATH)
    txt = m._gh_perfil_resumo(p)
    assert "asfalto" in txt          # rótulo pt-BR
    assert "%" in txt
    assert "balsa" in txt
    assert m._gh_perfil_resumo(None) == ""
    assert m._gh_perfil_resumo({}) == ""


def test_roundtrip_dados_graphhopper_com_perfil():
    p = m._gh_perfil_rota(_PATH)
    s = m._montar_dados_graphhopper(12.3, 20, "Sim", "http://x", "polyABC", p)
    d = m._parsear_dados_graphhopper(s)
    assert d is not None
    assert d["km"] == 12.3
    assert d["balsa"] == "Sim"
    assert d["geo_poly"] == "polyABC"
    assert isinstance(d["perfil"], dict)
    assert "surface" in d["perfil"]


def test_roundtrip_retrocompativel_sem_perfil():
    # Formato ANTIGO (5 campos, sem perfil) continua decodificando — nada regride.
    antigo = "10.0‖15‖Não‖http://y‖polyXYZ"
    d = m._parsear_dados_graphhopper(antigo)
    assert d is not None
    assert d["km"] == 10.0
    assert d["geo_poly"] == "polyXYZ"
    assert d["perfil"] is None
    # E o novo encoder sem perfil também fica limpo.
    s = m._montar_dados_graphhopper(10.0, 15, "Não", "http://y", "polyXYZ")
    assert m._parsear_dados_graphhopper(s)["perfil"] is None
