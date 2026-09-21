# -*- coding: utf-8 -*-
"""[COMPARADOR] Regressão do bug 'type tuple doesn't define round method' ao anexar/comparar.

`calcular_distancia_linha_reta` devolve uma TUPLA (km, status). Em `_conciliar_comparativo` uma única
chamada pegava a tupla inteira (em vez de desempacotar o escalar, como TODO o resto do arquivo faz) e o
`round(...)` logo abaixo estourava — derrubando a comparação com "Não consegui processar a planilha de
referência: type tuple doesn't define round method". Só disparava quando as coordenadas do destino da
REFERÊNCIA resolviam (origem e destino-ref distintos), por isso passou despercebido até a leitura de
planilhas melhorar. Este teste força esse caminho e garante número (não tupla)."""
import pandas as pd

import streamlit_app as m


def _inputs():
    df_app = pd.DataFrame({
        "Municipio Origem": ["Manaus", "Belem", "Santarem"], "UF Origem": ["AM", "PA", "PA"],
        "Cod IBGE Origem": ["1302603", "1501402", "1506807"],
        "Municipio Destino": ["Manaus", "Belem", "Santarem"],
        "Distancia": [0.0, 12.5, 40.0], "Tempo": [0.0, 15.0, 55.0],
        "Balsas": ["Nao", "Nao", "Sim"], "Linha Reta": [0.0, 10.0, 33.0],
        "Inscritos": [100, 50, 30],
    })
    # destino da referência DIFERENTE da origem (Belem -> Ananindeua) força resolver reta origem->destino_ref
    df_ref = pd.DataFrame({
        "NO_MUNICIPIO": ["Manaus", "Belem", "Santarem"], "UF": ["AM", "PA", "PA"],
        "CO_MUNICIPIO": ["1302603", "1501402", "1506807"],
        "NO_MUN_PROX": ["Manaus", "Ananindeua", "Santarem"],
        "DISTANCIA_KM": [0.0, 20.0, 45.0], "INSCRITOS": [100, 50, 30],
    })
    mapa = {"origem": "NO_MUNICIPIO", "uf_origem": "UF", "ibge_origem": "CO_MUNICIPIO",
            "destino": "NO_MUN_PROX", "inscritos": "INSCRITOS", "distancia": "DISTANCIA_KM", "tempo": None}
    return df_app, df_ref, mapa


def test_conciliar_nao_estoura_com_reta_referencia():
    df_app, df_ref, mapa = _inputs()
    # não pode levantar TypeError (o bug era 'type tuple doesn't define round method')
    linhas, aud = m._conciliar_comparativo(df_app, df_ref, mapa, limiar_empate_km=1.0)
    assert isinstance(linhas, list) and len(linhas) >= 1


def test_linha_reta_referencia_e_numero_nao_tupla():
    df_app, df_ref, mapa = _inputs()
    linhas, _ = m._conciliar_comparativo(df_app, df_ref, mapa, limiar_empate_km=1.0)
    achou_numero = False
    for _l in linhas:
        _v = _l.get("Linha Reta Referencia (km)")
        assert not isinstance(_v, tuple), "Linha Reta Referencia voltou a ser TUPLA (regressão)"
        if _v is not None:
            assert isinstance(_v, (int, float)) and _v > 0
            achou_numero = True
    # ao menos a linha Belem->Ananindeua tem reta > 0 resolvida
    assert achou_numero


def test_cadeia_completa_ate_xlsx():
    df_app, df_ref, mapa = _inputs()
    linhas, aud = m._conciliar_comparativo(df_app, df_ref, mapa, limiar_empate_km=1.0)
    cmp = m._comparar_alocacoes(linhas, limiar_empate_km=1.0)
    stc = m._estatisticas_comparacao(cmp, limiar_empate_km=1.0)
    rel = m._relatorio_executivo_comparacao(stc, aud, top_municipios=cmp)
    xb = m._montar_xlsx_comparacao(cmp, stc, aud, rel)
    assert isinstance(xb, (bytes, bytearray)) and len(xb) > 2000
