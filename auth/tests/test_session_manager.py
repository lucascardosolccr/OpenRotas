# -*- coding: utf-8 -*-
"""Testes de auth/session_manager.py — só a parte TESTÁVEL sem um servidor Streamlit real:
gerenciamento de estado (esta_autenticado/usuario_atual/_iniciar_sessao/encerrar_sessao) e o
toggle de abertura do perfil (abrir_perfil). As TELAS (_tela_login/_tela_cadastro/_tela_perfil/
etc.) renderizam widgets Streamlit reais e não têm cobertura automatizada aqui — mesma
limitação já documentada para o restante deste módulo (verificação manual/smoke test)."""
import logging
from unittest.mock import MagicMock

import pytest

logging.disable(logging.WARNING)

import streamlit as st  # noqa: E402

from auth import session_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _limpar_session_state():
    for _k in list(st.session_state.keys()):
        del st.session_state[_k]
    yield


def test_esta_autenticado_falso_sem_sessao():
    assert session_manager.esta_autenticado() is False


def test_esta_autenticado_falso_so_com_user_id():
    st.session_state["auth_user_id"] = "u1"
    assert session_manager.esta_autenticado() is False  # falta o access_token


def test_iniciar_sessao_autentica_e_usuario_atual_reflete_os_dados():
    session_manager._iniciar_sessao("u1", "a@b.com", "tok-acesso", "tok-refresh")
    assert session_manager.esta_autenticado() is True
    _u = session_manager.usuario_atual()
    assert _u == {"user_id": "u1", "email": "a@b.com"}


def test_usuario_atual_none_quando_nao_autenticado():
    assert session_manager.usuario_atual() is None


def test_encerrar_sessao_limpa_todas_as_chaves_de_auth(monkeypatch):
    session_manager._iniciar_sessao("u1", "a@b.com", "tok-acesso", "tok-refresh")
    monkeypatch.setattr(session_manager.auth_service, "fazer_logout", MagicMock())
    session_manager.encerrar_sessao()
    assert session_manager.esta_autenticado() is False
    for _k in session_manager._SESSION_KEYS:
        assert _k not in st.session_state


def test_encerrar_sessao_chama_fazer_logout_uma_vez(monkeypatch):
    session_manager._iniciar_sessao("u1", "a@b.com", "tok-acesso", "tok-refresh")
    _logout = MagicMock()
    monkeypatch.setattr(session_manager.auth_service, "fazer_logout", _logout)
    session_manager.encerrar_sessao()
    _logout.assert_called_once_with()


def test_abrir_perfil_liga_a_flag():
    assert not st.session_state.get("_mostrar_perfil")
    session_manager.abrir_perfil()
    assert st.session_state.get("_mostrar_perfil") is True
