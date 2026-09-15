# -*- coding: utf-8 -*-
"""Rede de segurança para a ANÁLISE DA SÉRIE HIDROLÓGICA da ANA/HidroWeb (ANA-SERIE): a resposta bruta
da API vira ESTATÍSTICA + SÉRIE TEMPORAL (mín/máx/média/último + data). O núcleo é PURO e precisa ser
robusto à variação de schema (nomes de coluna diferem por tipo de série) — o que só se testa com
DataFrames sintéticos, já que a rede está bloqueada no build.

Roda via pytest a partir da raiz: `python3 -m pytest test_ana_serie.py`."""
import logging

logging.disable(logging.WARNING)

import pandas as pd  # noqa: E402

import streamlit_app as m  # noqa: E402


def test_detecta_coluna_de_valor_por_alias_do_tipo():
    df = pd.DataFrame({
        "dataHora": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "cota": ["120", "130", "125"],
        "status": ["A", "A", "A"],
    })
    r = m._ana_serie_analitica(df, "Cotas")
    assert r is not None
    s = r["stats"]
    assert s["col_valor"] == "cota"
    assert s["n"] == 3
    assert s["min"] == 120.0 and s["max"] == 130.0
    assert s["ultimo"] == 125.0  # ordena por data → última leitura


def test_ordena_por_data_e_pega_ultimo_correto():
    # linhas fora de ordem: o "último" deve ser o de data mais recente, não a última linha.
    df = pd.DataFrame({
        "data": ["2024-03-01", "2024-01-01", "2024-02-01"],
        "vazao": [50.0, 10.0, 30.0],
    })
    r = m._ana_serie_analitica(df, "Vazões")
    assert r["stats"]["ultimo"] == 50.0
    assert r["stats"]["col_valor"] == "vazao"


def test_fallback_primeira_coluna_numerica_sem_alias():
    df = pd.DataFrame({"quando": ["2024-01-01", "2024-01-02"], "medicao_x": [1.5, 2.5]})
    r = m._ana_serie_analitica(df, "TipoDesconhecido")
    assert r is not None
    assert r["stats"]["col_valor"] == "medicao_x"
    assert r["stats"]["media"] == 2.0


def test_sem_dado_numerico_retorna_none():
    df = pd.DataFrame({"data": ["2024-01-01"], "obs": ["texto"]})
    assert m._ana_serie_analitica(df, "Cotas") is None


def test_robusto_a_entrada_invalida():
    assert m._ana_serie_analitica(None, "Cotas") is None
    assert m._ana_serie_analitica(pd.DataFrame(), "Cotas") is None


def test_serie_sem_coluna_de_data_ainda_estatistica():
    df = pd.DataFrame({"cota": [10, 20, 30]})
    r = m._ana_serie_analitica(df, "Cotas")
    assert r is not None
    assert r["stats"]["media"] == 20.0
    assert r["stats"]["ultimo"] == 30.0  # sem data → última linha


def test_ignora_valores_nao_numericos_na_coluna():
    df = pd.DataFrame({"data": ["2024-01-01", "2024-01-02", "2024-01-03"],
                       "cota": ["100", "", "200"]})
    r = m._ana_serie_analitica(df, "Cotas")
    assert r["stats"]["n"] == 2
    assert r["stats"]["min"] == 100.0 and r["stats"]["max"] == 200.0
