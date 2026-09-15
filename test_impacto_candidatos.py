# -*- coding: utf-8 -*-
"""Rede de segurança para o ESTUDO DE IMPACTO NOS CANDIDATOS (IMPACTO-CANDIDATOS): análise ponderada por
candidato (não por município), com quantis ponderados, Gini de concentração e recortes por balsa/risco/UF.
Núcleo 100% PURO — fixa o contrato, a ponderação e a robustez.

Roda: `python3 -m pytest test_impacto_candidatos.py`."""
import logging

logging.disable(logging.WARNING)

import pandas as pd  # noqa: E402

import streamlit_app as m  # noqa: E402


def _df():
    return pd.DataFrame({
        "Origem": ["A", "B", "C", "D"], "UF Origem": ["AM", "AM", "SP", "SP"],
        "Distancia": [300.0, 30.0, 500.0, 80.0], "Tempo": ["6 h", "30 min", "8 h", "1 h"],
        "Inscritos": [5000, 100, 50, 2000], "Balsas": ["Sim", "Não", "Não", "Não"],
        "Risco Operacional": ["crítico (78)", "baixo (10)", "alto (52)", "baixo (12)"],
    })


def test_sem_coluna_de_candidatos_nao_produz_estudo():
    df = pd.DataFrame({"Origem": ["A"], "Distancia": [100.0]})
    assert m._estudo_impacto_candidatos(df)["tem_candidatos"] is False


def test_detecta_coluna_e_totais():
    e = m._estudo_impacto_candidatos(_df())
    assert e["tem_candidatos"] and e["col_candidatos"] == "Inscritos"
    assert e["total_candidatos"] == 7150
    assert e["n_municipios"] == 4


def test_ponderacao_por_candidato_difere_da_media_simples():
    e = m._estudo_impacto_candidatos(_df())
    # candidato-km = 300*5000 + 30*100 + 500*50 + 80*2000 = 1.688.000; /7150 ≈ 236.1
    assert abs(e["km_candidato_total"] - 1688000.0) < 1.0
    assert abs(e["deslocamento_medio_ponderado"] - 236.1) < 0.2
    assert abs(e["deslocamento_medio_simples"] - 227.5) < 0.2


def test_quantil_ponderado_direto():
    # 3 municípios: dist 10 (peso 1), 20 (peso 1), 100 (peso 8) → mediana ponderada = 100
    assert m._quantil_ponderado([(10, 1), (20, 1), (100, 8)], 0.5) == 100.0
    assert m._quantil_ponderado([], 0.5) is None


def test_gini_extremos():
    assert m._gini([5, 5, 5, 5]) == 0.0              # igualdade total
    assert m._gini([0, 0, 0, 100]) > 0.6             # forte concentração


def test_recortes_balsa_e_risco_ponderados():
    e = m._estudo_impacto_candidatos(_df())
    assert e["balsa"]["candidatos"] == 5000          # só A tem balsa (5000 inscritos)
    assert e["risco"]["candidatos"] == 5050          # A (crítico) + C (alto) = 5000 + 50


def test_candidatos_longo_e_faixas():
    e = m._estudo_impacto_candidatos(_df(), limiar_longo_km=200.0)
    assert e["candidatos_longo"] == 5050             # A (300) + C (500)
    assert abs(sum(f["candidatos"] for f in e["distribuicao_faixas"]) - 7150) < 1


def test_por_uf_ponderado():
    e = m._estudo_impacto_candidatos(_df())
    _uf = {u["uf"]: u for u in e["por_uf"]}
    assert _uf["AM"]["candidatos"] == 5100 and _uf["SP"]["candidatos"] == 2050


def test_secao_html():
    h = m._secao_impacto_candidatos_html(m._estudo_impacto_candidatos(_df()))
    assert h and "Candidato-km total" in h and "Estudo" not in h.split("<h3")[0][:5]
    assert m._secao_impacto_candidatos_html({"tem_candidatos": False}) == ""
    assert m._secao_impacto_candidatos_html(None) == ""
