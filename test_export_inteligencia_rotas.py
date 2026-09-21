# -*- coding: utf-8 -*-
"""[GEO-INTEL-ANALITICO] Regressão de `_analise_rotas_geo` / `_escrever_aba_inteligencia_rotas`.

Garante que as colunas de inteligência geográfica das rotas (rios, pontes, travessias, rodovias,
ferrovias, confiabilidade, anomalias) — já anexadas por `_enriquecer_geo_inteligencia_df` — são
efetivamente ANALISADAS e IMPRESSAS na exportação Excel, e não só carregadas em bruto. Cobre também o
fail-open (df sem enriquecimento → nenhuma aba, sem exceção)."""
import io

import pandas as pd
import pytest

import streamlit_app as m


def _df_enriquecido():
    return pd.DataFrame({
        "QT_RIOS": [2, 0, 1, 3], "QT_CORPOS_DAGUA": [0, 0, 1, 0],
        "QT_PONTES": [1, 0, 0, 2], "QT_TRAVESSIAS": [0, 0, 1, 0],
        "QT_HIDROVIAS": [0, 0, 1, 0], "QT_RODOVIAS": [2, 1, 0, 3],
        "QT_FERROVIAS": [0, 0, 1, 0], "QT_ANOMALIAS": [0, 1, 0, 0],
        "QT_ALERTAS_CONFIABILIDADE": [0, 1, 2, 0],
        "Dependencia Aquaviaria": [10, 0, 80, 5],
        "Confianca Geografica": [90, 70, 40, 88],
        "Confianca Fundida": [85, 65, 45, 80],
        "Bacia Hidrografica": ["Amazonas", "", "Tocantins", "Amazonas"],
        "Rios Cruzados": ["Rio Negro, Rio Solimões", "", "Rio Tocantins",
                          "Rio Negro, Rio Branco, Rio Xingu"],
        "NM_RODOVIAS": ["BR-319, AM-070", "BR-174", "", "BR-319, PA-150, BR-163"],
        "NM_FERROVIAS": ["", "", "EFC", ""],
        "NM_HIDROVIAS": ["", "", "Hidrovia do Tocantins", ""],
        "Alertas de Confiabilidade": ["", "Rio sazonal",
                                      "Travessia sazonal; Rodovia não pavimentada", ""],
        "Anomalia Mais Severa": ["", "Detour excessivo", "", ""],
        "NM_ANOMALIAS": ["", "Detour", "", " "],
        "Conflito de Confianca": ["Não", "Não", "Sim", "Não"],
    })


def test_analise_gera_todas_as_secoes():
    linhas = m._analise_rotas_geo(_df_enriquecido())
    secoes = {l["Seção"] for l in linhas}
    # os seis blocos analíticos principais têm de estar presentes
    for prefixo in ("1. Cobertura", "2. Hidrografia", "3. Travessias", "4. Rodovias",
                    "5. Confiabilidade", "6. Anomalias"):
        assert any(s.startswith(prefixo) for s in secoes), f"faltou bloco {prefixo}"
    assert len(linhas) >= 20  # análise substantiva, não um punhado de linhas


def test_percentuais_e_top_listas_corretos():
    linhas = m._analise_rotas_geo(_df_enriquecido())
    _mapa = {(l["Seção"], l["Indicador"]): l["Valor"] for l in linhas}
    # 3 de 4 rotas cruzam rio
    assert _mapa[("1. Cobertura da análise", "Rotas que cruzam rio/córrego")] == "3 de 4 (75%)"
    # Rio Negro aparece em 2 rotas -> deve ser o top rio
    _rios = [(l["Indicador"], l["Valor"]) for l in linhas if l["Seção"] == "2b. Rios mais cruzados"]
    assert _rios and _rios[0][0] == "Rio Negro" and _rios[0][1] == "2 rota(s)"
    # BR-319 aparece em 2 rotas -> top rodovia
    _rods = [(l["Indicador"], l["Valor"]) for l in linhas if l["Seção"] == "4a. Rodovias mais frequentes"]
    assert _rods and _rods[0][0] == "BR-319" and _rods[0][1] == "2 rota(s)"


def test_aba_excel_escreve_de_verdade():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        ok = m._escrever_aba_inteligencia_rotas(w, _df_enriquecido())
    assert ok is True
    dados = buf.getvalue()
    assert len(dados) > 2000
    # a aba foi lida de volta e contém as colunas analíticas
    xl = pd.ExcelFile(io.BytesIO(dados))
    assert "Inteligencia das Rotas" in xl.sheet_names
    df_aba = xl.parse("Inteligencia das Rotas")
    assert list(df_aba.columns)[:3] == ["Seção", "Indicador", "Valor"]


def test_fail_open_sem_enriquecimento():
    # df sem as colunas geo -> [] e nenhuma aba escrita, sem exceção
    df = pd.DataFrame({"Distancia": [10, 20], "Municipio Origem": ["A", "B"]})
    assert m._analise_rotas_geo(df) == []
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        # precisa de ao menos uma aba para o writer não falhar ao fechar
        pd.DataFrame({"x": [1]}).to_excel(w, index=False, sheet_name="dummy")
        ok = m._escrever_aba_inteligencia_rotas(w, df)
    assert ok is False


def test_df_vazio_ou_none_nao_quebra():
    assert m._analise_rotas_geo(None) == []
    assert m._analise_rotas_geo(pd.DataFrame()) == []
