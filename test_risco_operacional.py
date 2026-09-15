# -*- coding: utf-8 -*-
"""Rede de segurança para o ÍNDICE DE RISCO OPERACIONAL DA ROTA (RISCO-OPERACIONAL): síntese explicável
(balsa, sinuosidade, pavimento, distância, snap) num score 0-100 para apoio à decisão logística. Núcleo
100% PURO/determinístico — este teste fixa o contrato, a monotonicidade e a robustez.

Roda via pytest a partir da raiz: `python3 -m pytest test_risco_operacional.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402


def test_rota_asfaltada_direta_e_baixo_risco():
    r = m._indice_risco_operacional(100.0, dist_reta_km=95.0, balsa=False, frac_pavimentado=1.0)
    assert r["nivel"] == "baixo"
    assert r["score"] < 20
    assert r["componentes"] == []  # nada a sinalizar


def test_balsa_e_o_maior_fator_isolado():
    r = m._indice_risco_operacional(120.0, dist_reta_km=110.0, balsa=True, ferry_km=4.0, n_travessias=2)
    assert r["score"] >= 25
    assert r["componentes"][0]["fator"] == "Travessia por balsa"  # ordenado por pontos desc
    # a contribuição da balsa é limitada a 40
    assert r["componentes"][0]["pontos"] <= 40


def test_sinuosidade_contribui_e_e_monotonica():
    baixo = m._indice_risco_operacional(140.0, dist_reta_km=100.0)   # V/R = 1.4 (limiar)
    alto = m._indice_risco_operacional(250.0, dist_reta_km=100.0)    # V/R = 2.5
    assert alto["score"] > baixo["score"]


def test_nao_pavimentado_aumenta_risco():
    pav = m._indice_risco_operacional(200.0, dist_reta_km=180.0, frac_pavimentado=1.0)
    terra = m._indice_risco_operacional(200.0, dist_reta_km=180.0, frac_pavimentado=0.4)
    assert terra["score"] > pav["score"]
    assert any("não pavimentado" in c["fator"].lower() or "pavimentad" in c["fator"].lower()
               for c in terra["componentes"])


def test_score_saturado_em_100_e_nivel_critico():
    r = m._indice_risco_operacional(900.0, dist_reta_km=200.0, balsa=True, ferry_km=20.0,
                                    n_travessias=5, frac_pavimentado=0.0, snap_max_m=5000.0)
    assert r["score"] <= 100
    assert r["nivel"] == "crítico"


def test_robusto_a_entradas_ausentes():
    r = m._indice_risco_operacional(None)
    assert r["score"] == 0 and r["nivel"] == "baixo" and r["componentes"] == []
    # reta ausente → não calcula sinuosidade, mas não quebra
    r2 = m._indice_risco_operacional(150.0, dist_reta_km=None, balsa=False)
    assert isinstance(r2["score"], int)


def test_snap_ruim_sinaliza_geocodificacao():
    r = m._indice_risco_operacional(80.0, dist_reta_km=70.0, snap_max_m=2000.0)
    assert any("geocodific" in c["fator"].lower() for c in r["componentes"])


def test_resumo_amigavel():
    r = m._indice_risco_operacional(300.0, dist_reta_km=120.0, balsa=True, n_travessias=1)
    txt = m._risco_operacional_resumo(r)
    assert "Risco operacional" in txt
    assert str(r["score"]) in txt
    assert m._risco_operacional_resumo(None) == ""
    assert m._risco_operacional_resumo({"componentes": []}) == ""
