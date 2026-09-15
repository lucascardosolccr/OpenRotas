# -*- coding: utf-8 -*-
"""Testes de auth/consent.py — o NÚCLEO do consentimento LGPD (interpretação da escolha, espelho em
session_state e gravação). O banner e o controle de preferências renderizam widgets Streamlit reais
e são fail-open por construção — não têm cobertura automatizada aqui."""
import logging
from unittest.mock import MagicMock

import pytest

logging.disable(logging.WARNING)

import streamlit as st  # noqa: E402

from auth import consent  # noqa: E402


@pytest.fixture(autouse=True)
def _limpar_session_state():
    for _k in list(st.session_state.keys()):
        del st.session_state[_k]
    yield


def test_interpretar_valores():
    assert consent._interpretar("sim") is True
    assert consent._interpretar("SIM") is True
    assert consent._interpretar("aceito") is True
    assert consent._interpretar("nao") is False
    assert consent._interpretar("não") is False
    assert consent._interpretar("recusado") is False
    assert consent._interpretar("") is None
    assert consent._interpretar(None) is None
    assert consent._interpretar("qualquer coisa") is None


def test_decisao_prefere_o_espelho_da_sessao():
    st.session_state[consent._CACHE_SESSAO] = True
    assert consent.decisao() is True
    st.session_state[consent._CACHE_SESSAO] = False
    assert consent.decisao() is False


def test_registrar_grava_espelho_na_sessao_e_o_cookie(monkeypatch):
    _set = MagicMock()
    monkeypatch.setattr(consent, "_set_cookie", _set)
    consent.registrar(True)
    assert st.session_state[consent._CACHE_SESSAO] is True
    assert _set.call_count == 1
    _args = _set.call_args[0]
    assert _args[0] == consent._COOKIE and _args[1] == "sim"


def test_registrar_recusa_grava_nao(monkeypatch):
    _set = MagicMock()
    monkeypatch.setattr(consent, "_set_cookie", _set)
    consent.registrar(False)
    assert st.session_state[consent._CACHE_SESSAO] is False
    assert _set.call_args[0][1] == "nao"


def test_disponivel_devolve_bool_sem_levantar():
    assert isinstance(consent.disponivel(), bool)


def test_decisao_none_sem_cookie_e_sem_espelho(monkeypatch):
    # sem espelho na sessão e sem cookie -> indeciso (None). Fail-open a qualquer erro de leitura.
    class _Ctx:
        cookies = {}
    monkeypatch.setattr(consent.st, "context", _Ctx(), raising=False)
    assert consent.decisao() is None
