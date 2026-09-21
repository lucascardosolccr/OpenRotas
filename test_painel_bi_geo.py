# -*- coding: utf-8 -*-
"""[PAINEL-GEO-FIX] O "Mapa de concentração" do Painel Executivo Interativo exigia colunas lat/lon
explícitas na planilha — que a maioria dos estudos NÃO traz — e caía sempre em "requer coordenadas".
Agora, quando faltam essas colunas, o centroide da origem é resolvido OFFLINE (base IBGE embarcada)
pelo Código IBGE ou pelo nome+UF, e o mapa passa a ter pontos. Estes testes travam o enriquecimento
sem regressão (coordenada explícita continua valendo; sem resolução, o painel ainda renderiza)."""
import pandas as pd

import streamlit_app as m


def test_enriquece_coordenada_por_codigo_ibge():
    # sem colunas lat/lon, mas com Código IBGE → o painel embute coordenadas (TEM_GEO=true)
    df = pd.DataFrame({
        "Municipio Origem": ["Belem", "Manaus"],
        "UF Origem": ["PA", "AM"],
        "Cod IBGE Origem": ["1501402", "1302603"],
        "Municipio Destino": ["Ananindeua", "Manaus"],
        "Distancia": [8.4, 0.0],
        "Inscritos": [50, 100],
    })
    html = m._painel_interativo_bi_html(df)
    assert html, "o painel deve renderizar"
    assert "TEM_GEO=true" in html, "coordenadas resolvidas offline pelo Código IBGE"
    # a coordenada de Belém (~-1.45, -48.5) deve aparecer embutida no JSON de dados
    assert '"la":' in html and '"lo":' in html


def test_codigo_ibge_float_resolve():
    # pandas costuma ler o Código IBGE como float (1501402.0) — o path de código deve casar mesmo assim
    df = pd.DataFrame({
        "Municipio Origem": ["Belem"],
        "UF Origem": ["PA"],
        "Cod IBGE Origem": [1501402.0],
        "Municipio Destino": ["Ananindeua"],
        "Distancia": [8.4],
        "Inscritos": [50],
    })
    html = m._painel_interativo_bi_html(df)
    assert html and "TEM_GEO=true" in html


def test_enriquece_coordenada_por_nome_uf():
    # sem lat/lon e sem código, mas nome+UF resolvem o centroide na base embarcada
    df = pd.DataFrame({
        "Municipio Origem": ["Belem"],
        "UF Origem": ["PA"],
        "Municipio Destino": ["Ananindeua"],
        "Distancia": [8.4],
        "Inscritos": [50],
    })
    html = m._painel_interativo_bi_html(df)
    assert html
    assert "TEM_GEO=true" in html


def test_sem_resolucao_ainda_renderiza():
    # município inexistente → sem coordenada, mas o painel não quebra (fail-open)
    df = pd.DataFrame({
        "Municipio Origem": ["Xxxxninguem"],
        "UF Origem": ["ZZ"],
        "Municipio Destino": ["Yyyy"],
        "Distancia": [10.0],
        "Inscritos": [1],
    })
    html = m._painel_interativo_bi_html(df)
    assert html, "mesmo sem geo, o painel renderiza"
    assert "TEM_GEO=false" in html
