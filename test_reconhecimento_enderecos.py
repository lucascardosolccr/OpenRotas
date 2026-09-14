# -*- coding: utf-8 -*-
"""Rede de segurança automatizada para o RECONHECIMENTO DE ENDEREÇOS/CORPOS HÍDRICOS —
recursos que hoje só eram exercitados manualmente e podiam regredir em silêncio:

  1. Expansão de abreviações de logradouro/honoríficos (semantica.normalizar), com a
     BLINDAGEM das 27 siglas de UF e a preservação do município "Venha-Ver/RN".
  2. Nomeação do CORPO HÍDRICO atravessado (rio OU lago/represa/lagoa/baía): o grafo de
     drenagem nomeia rios; a base IBGE massas_dagua nomeia os demais — inclusive quando o
     grafo fluvial não está carregado.

Roda via pytest a partir da raiz: `python3 -m pytest test_reconhecimento_enderecos.py`.
Importa `streamlit_app` em modo bare (mesmo padrão de test_comparador_correcao.py)."""
import logging
import os

logging.disable(logging.WARNING)

import pytest  # noqa: E402

import streamlit_app as m  # noqa: E402

_MASSAS = "data/brasil/ibge/derivadas/massas_dagua.parquet"


# ==============================================================================
# 1. Expansão de abreviações + blindagem de UF
# ==============================================================================
def test_normalizar_expande_tipos_de_logradouro():
    n = m.semantica.normalizar("AV PAULISTA, JD EUROPA, SAO PAULO, SP")
    assert "AVENIDA" in n
    assert "JARDIM" in n


def test_normalizar_expande_honorificos():
    assert "PRESIDENTE" in m.semantica.normalizar("AV PRES VARGAS, RIO DE JANEIRO, RJ")
    assert "DOUTOR" in m.semantica.normalizar("R DR XAVIER, FORTALEZA, CE")
    assert "ENGENHEIRO" in m.semantica.normalizar("AV ENG LUIS CARLOS BERRINI, SP")


def test_normalizar_blinda_sigla_uf():
    # "AL" (Alagoas) NUNCA pode virar "ALAMEDA" (bug histórico da 46ª geração).
    n = m.semantica.normalizar("SANTANA DO IPANEMA, AL")
    assert "ALAMEDA" not in n
    assert n.rstrip().endswith("AL")


def test_normalizar_preserva_municipio_venha_ver():
    # "VER" NÃO pode virar "VEREADOR" — colidiria com o município Venha-Ver/RN.
    assert "VEREADOR" not in m.semantica.normalizar("VENHA-VER, RN")


# ==============================================================================
# 2. Nomeação de corpo hídrico (rio OU massa d'água)
# ==============================================================================
def _amostra_massa_dagua_nomeada():
    """(lat, lon, nome) de uma massa d'água NOMEADA da base IBGE, ou None se indisponível."""
    if not os.path.exists(_MASSAS):
        return None
    import pandas as pd
    df = pd.read_parquet(_MASSAS, columns=["nome", "lat", "lon"])
    _s = df["nome"].astype(str).str.strip()
    df = df[(_s != "") & (~_s.str.lower().isin(["none", "nan"]))]
    if df.empty:
        return None
    r = df.iloc[0]
    return float(r["lat"]), float(r["lon"]), str(r["nome"]).strip()


def test_corpo_hidrico_ibge_nomeia_massa_dagua():
    amostra = _amostra_massa_dagua_nomeada()
    if amostra is None:
        pytest.skip("base IBGE massas_dagua ausente neste ambiente")
    lat, lon, nome = amostra
    r = m._nome_corpo_hidrico_ibge(lat, lon, raio_km=4.0)
    assert r is not None, "deveria nomear a massa d'água sob o ponto"
    assert r["nome"].strip().lower() == nome.lower()
    assert r["dist_km"] is not None and r["dist_km"] <= 4.0


def test_nome_rio_na_travessia_nomeia_corpo_hidrico():
    amostra = _amostra_massa_dagua_nomeada()
    if amostra is None:
        pytest.skip("base IBGE massas_dagua ausente neste ambiente")
    lat, lon, nome = amostra
    r = m._nome_rio_na_travessia(lat, lon, raio_km=4.0)
    # Deve nomear ALGO (o rio local, se houver, ou o corpo hídrico via fallback) — nunca
    # cair em "não determinado" estando sobre um corpo d'água nomeado.
    assert r.get("confianca") in ("alta", "media"), r
    assert r.get("nome_rio")


def test_nome_rio_na_travessia_contrato_offshore():
    # Ponto no oceano, longe de qualquer hidrografia mapeada e de massas d'água nomeadas:
    # a função é defensiva e devolve o contrato completo, sem inventar nome.
    r = m._nome_rio_na_travessia(-20.0, -33.0, raio_km=4.0)
    for k in ("nome_rio", "nomes_rios", "dist_km", "confianca"):
        assert k in r
    assert r["nome_rio"] is None
    assert r["confianca"] in ("nao_determinado", "indisponivel", "corpo_sem_nome")
