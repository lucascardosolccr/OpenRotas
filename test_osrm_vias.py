# -*- coding: utf-8 -*-
"""Rede de segurança para a extração das PRINCIPAIS VIAS/RODOVIAS da rota OSRM (OSRM-VIAS): a app já
buscava steps=true (só para detectar balsa) e descartava os nomes/refs das vias. O núcleo é PURO
(agrega distância por via, reconhece rodovias BR/estaduais) e é keyless (roda em toda rota OSRM).

Roda via pytest a partir da raiz: `python3 -m pytest test_osrm_vias.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402

# JSON sintético fiel ao formato OSRM /route com steps: cada step traz distance (metros), name e ref.
_ROTA = {
    "legs": [{
        "steps": [
            {"distance": 120000.0, "name": "Rodovia Governador Mário Covas", "ref": "BR-101"},
            {"distance": 85000.0, "name": "Rodovia Régis Bittencourt", "ref": "BR-116"},
            {"distance": 40000.0, "name": "Rodovia Castello Branco", "ref": "SP-280"},
            {"distance": 3000.0, "name": "Rua Local", "ref": ""},
            {"distance": 0.0, "name": "", "ref": ""},          # step degenerado: ignorado
        ]
    }]
}


def test_agrega_por_distancia_e_reconhece_rodovias():
    r = m._osrm_vias_principais(_ROTA)
    assert r is not None
    desigs = [x["desig"] for x in r["rodovias"]]
    assert desigs[0] == "BR-101"     # mais longa primeiro
    assert "BR-116" in desigs
    assert "SP-280" in desigs
    # km_total_nomeado soma só trechos com nome/ref (ignora o degenerado)
    assert abs(r["km_total_nomeado"] - (120 + 85 + 40 + 3)) < 0.5


def test_prefere_ref_sobre_nome_na_chave():
    r = m._osrm_vias_principais(_ROTA)
    nomes_vias = [v["nome"] for v in r["vias"]]
    assert "BR-101" in nomes_vias      # usou o ref como chave da via


def test_resumo_amigavel_prioriza_rodovias():
    r = m._osrm_vias_principais(_ROTA)
    txt = m._osrm_vias_resumo(r)
    assert txt.startswith("Rodovias:")
    assert "BR-101" in txt
    assert "km" in txt


def test_resumo_cai_para_vias_sem_rodovia_reconhecida():
    rota = {"legs": [{"steps": [
        {"distance": 5000.0, "name": "Avenida Central", "ref": ""},
        {"distance": 2000.0, "name": "Rua das Flores", "ref": ""},
    ]}]}
    r = m._osrm_vias_principais(rota)
    assert not r["rodovias"]
    txt = m._osrm_vias_resumo(r)
    assert txt.startswith("Principais vias:")
    assert "Avenida Central" in txt


def test_robusto_a_entrada_invalida():
    assert m._osrm_vias_principais(None) is None
    assert m._osrm_vias_principais({}) is None
    assert m._osrm_vias_principais({"legs": []}) is None
    assert m._osrm_vias_resumo(None) == ""
    assert m._osrm_vias_resumo({}) == ""


def test_nao_inventa_rodovia_com_prefixo_invalido():
    # "XX-999" não é UF válida nem BR → não deve entrar como rodovia reconhecida.
    rota = {"legs": [{"steps": [{"distance": 10000.0, "name": "Estrada XX-999", "ref": ""}]}]}
    r = m._osrm_vias_principais(rota)
    assert r["rodovias"] == []
