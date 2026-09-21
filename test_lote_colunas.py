# -*- coding: utf-8 -*-
"""[LOTE-COLUNAS] `_diagnosticar_colunas_lote`: mensagem de erro ACIONÁVEL quando a planilha do Lote
não tem as colunas obrigatórias. Antes o erro era genérico e não dizia o que a planilha tinha — o
usuário ficava adivinhando o cabeçalho certo. Estes testes travam o diagnóstico: OK quando presentes,
lista as colunas encontradas e sugere a mais parecida (difflib) para renomear quando faltam."""
import streamlit_app as m


def test_colunas_presentes_ok():
    ok, msg = m._diagnosticar_colunas_lote(["Origem", "Destino"])
    assert ok is True and msg == ""
    # ordem não importa e colunas extras são toleradas
    ok2, _ = m._diagnosticar_colunas_lote(["Inscritos", "Destino", "Origem", "UF"])
    assert ok2 is True


def test_sugere_coluna_parecida():
    # "Origens"/"Destinos" (plural) → falta o nome exato, mas a sugestão aponta o parecido
    ok, msg = m._diagnosticar_colunas_lote(["Origens", "Destinos"])
    assert ok is False
    assert "Origens" in msg and "Destinos" in msg
    assert "renomeie" in msg.lower()


def test_lista_colunas_encontradas():
    ok, msg = m._diagnosticar_colunas_lote(["Cidade", "Polo"])
    assert ok is False
    assert "Cidade" in msg and "Polo" in msg      # mostra o que a planilha tinha
    assert "Origem" in msg and "Destino" in msg    # e o que precisa


def test_planilha_sem_cabecalho():
    ok, msg = m._diagnosticar_colunas_lote([])
    assert ok is False
    assert "cabeçalho" in msg.lower()


def test_falta_apenas_uma():
    ok, msg = m._diagnosticar_colunas_lote(["Origem", "Polo"])
    assert ok is False
    # Origem presente não deve ser cobrada; Destino ausente sim
    assert "Faltou **Destino**" in msg
    assert "Faltou **Origem**" not in msg
