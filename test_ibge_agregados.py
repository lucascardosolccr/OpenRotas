# -*- coding: utf-8 -*-
"""Rede de segurança para o ENRIQUECIMENTO ESTATÍSTICO via API v3 de Agregados do IBGE
(Censo 2022 — população, densidade e área territorial derivada).

O download é rede (bloqueado no ambiente de build), mas o NÚCLEO DE PARSING é 100% PURO e é o
que pode regredir em silêncio. Estes testes exercitam o parser contra uma AMOSTRA CAPTURADA do
formato real de resposta v3 do IBGE, garantindo o contrato: extrai o valor mais recente, respeita
os sentinelas de indisponibilidade ('...', '-', 'X'), deriva a área exata (pop/densidade) e é
fail-open (nunca inventa, nunca levanta exceção).

Roda via pytest a partir da raiz: `python3 -m pytest test_ibge_agregados.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402

# Amostra fiel ao formato v3 real: /agregados/4714/periodos/2022/variaveis/93|5934?localidades=N6[3550308]
# São Paulo/SP (cod 3550308). População 11.451.999; densidade 7.398,26 hab/km².
_AMOSTRA_SP = [
    {
        "id": "93",
        "variavel": "População residente",
        "unidade": "Pessoas",
        "resultados": [
            {"classificacoes": [],
             "series": [
                 {"localidade": {"id": "3550308", "nivel": {"id": "N6", "nome": "Município"},
                                 "nome": "São Paulo - SP"},
                  "serie": {"2022": "11451999"}}
             ]}
        ],
    },
    {
        "id": "5934",
        "variavel": "Densidade demográfica",
        "unidade": "Habitante por quilômetro quadrado",
        "resultados": [
            {"classificacoes": [],
             "series": [
                 {"localidade": {"id": "3550308", "nivel": {"id": "N6", "nome": "Município"},
                                 "nome": "São Paulo - SP"},
                  "serie": {"2022": "7398.26"}}
             ]}
        ],
    },
]


def test_valor_numerico_trata_sentinelas():
    assert m._ibge_valor_numerico("11451999") == 11451999.0
    assert m._ibge_valor_numerico("7398.26") == 7398.26
    for sentinela in ("...", "-", "X", "x", "..", "", None):
        assert m._ibge_valor_numerico(sentinela) is None


def test_parse_extrai_variaveis_do_municipio():
    p = m._parse_ibge_agregado(_AMOSTRA_SP, "3550308")
    assert p["93"]["valor"] == 11451999.0
    assert p["93"]["periodo"] == "2022"
    assert p["5934"]["valor"] == 7398.26
    assert p["5934"]["unidade"].lower().startswith("habitante")


def test_parse_ignora_municipio_diferente():
    # Pedindo outro código, nada casa — dict vazio, sem exceção.
    assert m._parse_ibge_agregado(_AMOSTRA_SP, "3304557") == {}


def test_parse_robusto_a_lixo():
    # Contrato defensivo: entradas malformadas nunca levantam exceção.
    assert m._parse_ibge_agregado(None, "3550308") == {}
    assert m._parse_ibge_agregado({}, "3550308") == {}
    assert m._parse_ibge_agregado([{"id": "93"}], "3550308") == {}


def test_consolidar_deriva_area_exata():
    resumo = m._consolidar_estatisticas_ibge(m._parse_ibge_agregado(_AMOSTRA_SP, "3550308"))
    assert resumo["populacao"] == 11451999
    assert resumo["densidade"] == 7398.26
    # área = população / densidade (definição oficial do IBGE)
    assert abs(resumo["area_km2"] - (11451999 / 7398.26)) < 0.1
    assert resumo["periodo"] == "2022"
    assert "IBGE" in resumo["fonte"]


def test_consolidar_vazio_quando_nada_numerico():
    amostra_vazia = [
        {"id": "93", "variavel": "População residente", "unidade": "Pessoas",
         "resultados": [{"classificacoes": [],
                         "series": [{"localidade": {"id": "3550308"}, "serie": {"2022": "..."}}]}]},
    ]
    assert m._consolidar_estatisticas_ibge(m._parse_ibge_agregado(amostra_vazia, "3550308")) == {}


def test_fetcher_fail_open_com_codigo_invalido():
    # Sem rede/código inválido → {} (nunca inventa, nunca levanta).
    assert m._ibge_estatisticas_municipio("") == {}
    assert m._ibge_estatisticas_municipio("abc") == {}
    assert m._ibge_estatisticas_municipio(None) == {}
