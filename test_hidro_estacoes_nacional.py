# -*- coding: utf-8 -*-
"""[ESTAÇÕES / VAZÕES — COBERTURA NACIONAL] A consulta de cotas/vazões precisa de estações REAIS (código ANA)
cobrindo TODO o Brasil. Antes: só uma amostra de 8 pontos sem código (vazões indisponíveis), e mesmo baixando
o catálogo de 91 MB as colunas cruas da ANA não batiam com a UI. Agora: um OVERVIEW nacional versionado no repo
(estações fluviométricas reais, 27 UFs) + normalizador do catálogo cru. Estes testes travam a cobertura."""
import pandas as pd
import streamlit_app as m


# ---- Overview nacional versionado (asset no repo) ------------------------------------------
def test_overview_estacoes_cobre_as_27_ufs_com_codigos_reais():
    ov = m._carregar_estacoes_overview_nacional()
    assert ov is not None and not ov.empty
    assert ov["uf"].nunique() == 27, "a rede nacional de estações deve cobrir as 27 UFs"
    for _c in ["codigo", "nome", "rio", "uf", "lat", "lon", "tipo"]:
        assert _c in ov.columns
    # códigos ANA fluviométricos: 8 dígitos, prefixo de bacia 1-9 (nunca placeholder)
    cods = ov["codigo"].astype(str)
    assert (cods.str.fullmatch(r"\d{6,10}")).all(), "todos os códigos são numéricos reais"
    assert (cods != "—").all()
    # varre o país (Roraima ao Chuí)
    assert ov["lat"].max() > 3.5 and ov["lat"].min() < -29.0
    assert ov["lon"].min() < -66.0 and ov["lon"].max() > -40.0


def test_overview_estacoes_nao_e_tratado_como_amostra():
    # a fonte do overview é "real" → NÃO deve casar com a fonte da amostra fabricada de 8 pontos
    ov = m._carregar_estacoes_overview_nacional()
    assert ov["fonte"].iloc[0] != m._FONTE_ESTACOES_AMOSTRA
    assert ov["fonte"].iloc[0] == m._FONTE_ESTACOES_NACIONAL


# ---- Normalizador do catálogo CRU da ANA (colunas idFormatadoComZero/nomeRio/nomeEstado/…) ---
def _raw_ana():
    return pd.DataFrame([
        # fluviométrica BR (mantém) — código com zero à esquerda preservado
        {"idFormatadoComZero": "00048000", "nome": "PORTO X", "nomeRio": "RIO A", "codigoNomeBacia": "1 - AM",
         "nomeEstado": "AMAZONAS", "latitude": -3.1, "longitude": -60.0, "tipoEstacao": 1, "tipoEstacaoTelemetrica": 1},
        # pluviométrica (tipoEstacao=2 → removida: não mede vazão)
        {"idFormatadoComZero": "00048002", "nome": "CHUVA Y", "nomeRio": "", "codigoNomeBacia": "1 - AM",
         "nomeEstado": "AMAZONAS", "latitude": -3.2, "longitude": -60.1, "tipoEstacao": 2, "tipoEstacaoTelemetrica": 0},
        # estação do PERU (deve sair — e NUNCA virar 'PE'=Pernambuco)
        {"idFormatadoComZero": "10010000", "nome": "PATATE", "nomeRio": "RIO NAPO", "codigoNomeBacia": "1",
         "nomeEstado": "PERU", "latitude": -1.2, "longitude": -78.5, "tipoEstacao": 1, "tipoEstacaoTelemetrica": 0},
    ])


def test_normalizador_mantem_so_fluviometricas_brasileiras():
    norm = m._normalizar_estacoes_ana(_raw_ana())
    assert norm is not None
    assert list(norm.columns) == ["codigo", "nome", "rio", "bacia", "uf", "lat", "lon", "tipo"]
    # só a fluviométrica do Amazonas sobrevive
    assert len(norm) == 1
    r = norm.iloc[0]
    assert r["uf"] == "AM" and r["codigo"] == "00048000" and r["tipo"] == "Telemétrica"


def test_normalizador_nao_confunde_peru_com_pernambuco():
    norm = m._normalizar_estacoes_ana(_raw_ana())
    assert "PE" not in set(norm["uf"]), "PERU jamais pode virar PE (Pernambuco)"
