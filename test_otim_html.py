# -*- coding: utf-8 -*-
"""[OTIM-HTML] O ganho dos passes de otimalidade de rota (resgate por circuidade + fechamento de
otimalidade) existia só na tela da Alocação. `_html_resumo_otimalidade` leva-o para o relatório HTML
exportável. PURO e defensivo: sem ganho → '' (nenhuma seção é adicionada); com ganho → cards com rotas
melhoradas e km economizados, somando os dois passes."""
import streamlit_app as m


def test_sem_ganho_retorna_vazio():
    assert m._html_resumo_otimalidade(None, None) == ""
    assert m._html_resumo_otimalidade({"n_trocas": 0, "km_economizados": 0},
                                      {"trocas": 0, "km_salvo_total": 0}) == ""


def test_soma_os_dois_passes_e_formata():
    h = m._html_resumo_otimalidade(
        resgate={"n_trocas": 3, "km_economizados": 120.0},
        fechamento={"trocas": 5, "km_salvo_total": 380.0})
    assert h  # não vazio
    # total de trocas 3+5=8 e km 120+380=500
    assert "8" in h
    assert "500 km" in h
    # detalha a origem de cada bloco
    assert "resgate por circuidade" in h
    assert "fechamento de otimalidade" in h


def test_apenas_fechamento():
    h = m._html_resumo_otimalidade(resgate=None, fechamento={"trocas": 2, "km_salvo_total": 45.4})
    assert h
    assert "2" in h and "45 km" in h
    # sem resgate, não cita o bloco do resgate
    assert "pelo resgate por circuidade" not in h


def test_defensivo_valores_invalidos():
    # valores não numéricos não quebram
    assert m._html_resumo_otimalidade({"n_trocas": None, "km_economizados": None},
                                      {"trocas": None, "km_salvo_total": None}) == ""
