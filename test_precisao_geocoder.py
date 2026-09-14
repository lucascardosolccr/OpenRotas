# -*- coding: utf-8 -*-
"""Rede de segurança para a EXTRAÇÃO DO SINAL DE QUALIDADE dos geocoders (GEO-PRECISAO):
o ArcGIS/Nominatim/Photon devolvem a granularidade do casamento (rooftop, via, aproximado) que a app
antes descartava. Estes testes fixam o contrato do núcleo PURO que traduz esses metadados em um tier +
rótulo amigáveis, incluindo o fallback determinístico pelos campos já resolvidos e a robustez a lixo.

Roda via pytest a partir da raiz: `python3 -m pytest test_precisao_geocoder.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402


def test_addr_type_arcgis_autoritativo():
    assert m._precisao_geocoder({"addr_type": "PointAddress"})[0] == "exato"
    assert m._precisao_geocoder({"addr_type": "StreetAddress"})[0] == "via_numero"
    assert m._precisao_geocoder({"addr_type": "StreetName"})[0] == "via"
    assert m._precisao_geocoder({"addr_type": "Locality"})[0] == "aproximado"
    assert m._precisao_geocoder({"addr_type": "Postal"})[0] == "aproximado"


def test_addr_type_case_insensitive():
    a = m._precisao_geocoder({"addr_type": "POINTADDRESS"})
    b = m._precisao_geocoder({"addr_type": "pointaddress"})
    assert a == b and a[0] == "exato"


def test_fallback_por_campos_quando_sem_addr_type():
    # Sem addr_type (ex.: Nominatim/Photon) → infere do próprio candidato.
    assert m._precisao_geocoder({"numero": "123", "logradouro": "RUA X"})[0] == "via_numero"
    assert m._precisao_geocoder({"logradouro": "RUA X"})[0] == "via"
    assert m._precisao_geocoder({"bairro": "CENTRO"})[0] == "aproximado"
    assert m._precisao_geocoder({"cidade": "SAO PAULO"})[0] == "aproximado"
    assert m._precisao_geocoder({})[0] == ""


def test_robustez_a_entrada_invalida():
    assert m._precisao_geocoder(None) == ("", "")
    assert m._precisao_geocoder("lixo") == ("", "")
    assert m._precisao_geocoder({"addr_type": "TIPO_DESCONHECIDO"}) == ("", "")


def test_rotular_precisao_enriquece_in_place_sem_tocar_score():
    cand = {"fonte": "ARCGIS", "score_base": 30, "addr_type": "PointAddress", "logradouro": "AV X", "numero": "10"}
    out = m._rotular_precisao(cand)
    assert out is cand  # in-place
    assert cand["score_base"] == 30  # NUNCA altera a pontuação calibrada
    assert cand["precisao_tier"] == "exato"
    assert cand["precisao_rotulo"]
    assert cand["precisao_rank"] == m._TIER_ORDEM["exato"]


def test_ordem_dos_tiers_e_monotonica():
    # rooftop > via c/ número > via > aproximado > nada
    o = m._TIER_ORDEM
    assert o["exato"] > o["via_numero"] > o["via"] > o["aproximado"] > o[""]


def test_consenso_carrega_melhor_precisao_do_cluster():
    # Dois votos ~no mesmo ponto: um aproximado (cidade) e um rooftop. O consenso deve reportar rooftop.
    aprox = m._rotular_precisao({"lat": -23.55, "lon": -46.63, "fonte": "PHOTON", "score_base": 20,
                                 "cidade": "SAO PAULO"})
    exato = m._rotular_precisao({"lat": -23.5501, "lon": -46.6301, "fonte": "ARCGIS", "score_base": 30,
                                 "addr_type": "PointAddress", "logradouro": "AV PAULISTA", "numero": "1000"})
    cc = m._votar_consenso([aprox, exato], limiar_km=1.0)
    assert cc is not None
    assert cc["precisao_tier"] == "exato"
    assert cc["precisao_rotulo"]
