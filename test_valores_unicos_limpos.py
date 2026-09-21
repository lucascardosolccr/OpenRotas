# -*- coding: utf-8 -*-
"""[ALOC-LIMPEZA] `_valores_unicos_limpos`: extrai os valores únicos NÃO vazios de uma coluna da
planilha (origens/polos da Alocação) e conta as linhas descartadas. Antes, o fluxo fazia
`dropna().astype(str).str.strip().unique()` — mas o strip transforma uma célula só com espaços em ''
e o '' SOBREVIVIA ao unique, entrando no universo como uma origem/polo FANTASMA que era geocodificada
à toa (lixo ou (0,0)). Estes testes travam o descarte e a contagem para transparência ao usuário."""
import numpy as np
import pandas as pd

import streamlit_app as m


def test_descarta_nan_e_brancos():
    s = pd.Series(["Belem", "  ", "Manaus", None, "Belem", "", "   Recife  ", np.nan])
    valores, n_desc = m._valores_unicos_limpos(s)
    assert "" not in valores                       # nenhuma origem fantasma
    assert set(valores) == {"Belem", "Manaus", "Recife"}   # únicos, com trim
    assert n_desc == 4                             # 2 NaN + 2 em branco/espacos


def test_tudo_valido_nao_descarta():
    s = pd.Series(["A", "B", "C"])
    valores, n_desc = m._valores_unicos_limpos(s)
    assert sorted(valores) == ["A", "B", "C"] and n_desc == 0


def test_tudo_vazio_retorna_lista_vazia():
    s = pd.Series([None, "  ", "", np.nan])
    valores, n_desc = m._valores_unicos_limpos(s)
    assert valores == [] and n_desc == 4


def test_numerico_vira_texto_sem_quebrar():
    # código IBGE numérico não deve quebrar (astype str)
    s = pd.Series([1501402, 1302603, None])
    valores, n_desc = m._valores_unicos_limpos(s)
    assert "1501402" in valores and n_desc == 1
