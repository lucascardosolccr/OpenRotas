# -*- coding: utf-8 -*-
"""[PERF-FUZZY / PERF-INDICE-UF] Índices nacionais construídos a cada rerun do Streamlit foram movidos para
@st.cache_resource (rodam 1× por processo, sem re-hash do dict de ~5.571 municípios nem cópia). Guarda de
regressão: mesma referência entre chamadas (cache_resource), conteúdo íntegro e somente-leitura."""
import streamlit_app as m


def test_lista_fuzzy_e_cache_resource_mesma_referencia():
    a = m.inicializar_listas_fuzzy()
    b = m.inicializar_listas_fuzzy()
    assert a is b                       # cache_resource → mesma referência (sem cópia, sem re-hash)


def test_lista_fuzzy_conteudo_integro():
    lst = m.inicializar_listas_fuzzy()
    assert isinstance(lst, tuple) and len(lst) > 5000
    # cada entrada é "NOME UF" (nome do município normalizado + sigla de 2 letras)
    amostra = lst[0]
    assert isinstance(amostra, str) and amostra[-3] == " " and amostra[-2:].isalpha()
    # a lista de contexto do módulo é a mesma do cache
    assert m.LISTA_CONTEXTO_FUZZY is lst


def test_indice_por_uf_cache_resource_e_estrutura():
    i1 = m._construir_ibge_municipios_por_uf()
    i2 = m._construir_ibge_municipios_por_uf()
    assert i1 is i2                     # cache_resource → mesma referência
    assert m.IBGE_MUNICIPIOS_POR_UF is i1
    # estrutura {uf: {municipio_norm: [itens]}} com as 27 UFs
    assert len(i1) == 27
    assert "SP" in i1 and isinstance(i1["SP"], dict) and len(i1["SP"]) > 0
