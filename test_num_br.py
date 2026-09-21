# -*- coding: utf-8 -*-
"""[NUM-BR] `_to_num_br`: parser numérico tolerante ao formato brasileiro no Comparador de Estudos.

Planilhas de referência brasileiras usam VÍRGULA decimal ('95,4') e PONTO de milhar ('1.234,56'). O
`float()` puro rejeitava esses valores — a distância virava None e a linha era descartada da comparação
em silêncio (ou TODA a planilha reprovava no pré-voo como "distância não numérica"). Estes testes
travam o parser e o comportamento ponta-a-ponta do comparador com dados no formato BR."""
import pandas as pd

import streamlit_app as m


def test_formatos_brasileiro_e_americano():
    assert m._to_num_br("95,4") == 95.4                 # vírgula decimal (BR)
    assert m._to_num_br("1.234,56") == 1234.56          # ponto milhar + vírgula decimal (BR)
    assert m._to_num_br("1,234.56") == 1234.56          # vírgula milhar + ponto decimal (US)
    assert m._to_num_br("95.4") == 95.4                 # ponto decimal
    assert m._to_num_br("1234") == 1234.0
    assert m._to_num_br("-3,5") == -3.5                 # negativo com vírgula
    assert m._to_num_br("  12,0 km ") == 12.0           # remove sufixo/espaços


def test_lone_dot_mantem_semantica_de_float():
    # caso ambíguo: mantemos a semântica do float() (ponto = decimal), como era antes — sem regressão
    assert m._to_num_br("1.234") == 1.234
    assert m._to_num_br("3.14") == 3.14


def test_valores_ja_numericos_e_invalidos():
    assert m._to_num_br(42) == 42.0
    assert m._to_num_br(3.14) == 3.14
    assert m._to_num_br(True) is None      # bool não é número aqui
    assert m._to_num_br(float("nan")) is None
    for ruim in (None, "", "  ", "abc", "-", ",", "."):
        assert m._to_num_br(ruim) is None
    assert m._to_num_br("", 0.0) == 0.0    # padrão respeitado


def test_validacao_aceita_planilha_br_com_virgula():
    # antes: TODAS as distâncias 'não numéricas' -> bloqueante. Agora: planilha íntegra.
    df_ref = pd.DataFrame({"NO_MUNICIPIO": ["Belem", "Manaus"], "NO_MUN_PROX": ["Ananindeua", "Manaus"],
                           "DISTANCIA_KM": ["8,4", "0,0"], "UF": ["PA", "AM"],
                           "CO_MUNICIPIO": ["1501402", "1302603"], "INSCRITOS": ["50", "100"]})
    mapa = {"origem": "NO_MUNICIPIO", "destino": "NO_MUN_PROX", "distancia": "DISTANCIA_KM",
            "uf_origem": "UF", "ibge_origem": "CO_MUNICIPIO", "inscritos": "INSCRITOS", "tempo": None}
    vp = m._validar_planilha_comparativa(df_ref, mapa)
    tipos = [b["tipo"] for b in vp["bloqueantes"]]
    assert "Distância não numérica" not in tipos
    assert vp["pode_processar"] is True


def test_conciliacao_parseia_distancia_br():
    df_app = pd.DataFrame({"Municipio Origem": ["Belem"], "UF Origem": ["PA"],
                           "Cod IBGE Origem": ["1501402"], "Municipio Destino": ["Belem"],
                           "Distancia": [12.5], "Tempo": [15.0], "Balsas": ["Nao"],
                           "Linha Reta": [10.0], "Inscritos": [50]})
    df_ref = pd.DataFrame({"NO_MUNICIPIO": ["Belem"], "UF": ["PA"], "CO_MUNICIPIO": ["1501402"],
                           "NO_MUN_PROX": ["Ananindeua"], "DISTANCIA_KM": ["8,4"], "INSCRITOS": ["50"]})
    mapa = {"origem": "NO_MUNICIPIO", "uf_origem": "UF", "ibge_origem": "CO_MUNICIPIO",
            "destino": "NO_MUN_PROX", "inscritos": "INSCRITOS", "distancia": "DISTANCIA_KM", "tempo": None}
    lin, _ = m._conciliar_comparativo(df_app, df_ref, mapa, limiar_empate_km=1.0)
    assert lin and abs(float(lin[0]["Distancia Referencia"]) - 8.4) < 1e-6
