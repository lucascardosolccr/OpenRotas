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


# ==============================================================================
# [PERSISTÊNCIA DE SESSÃO] Resiliência da revalidação: uma falha TRANSIENTE (rede/servidor)
# NUNCA derruba a sessão com o navegador aberto; só uma rejeição DEFINITIVA do refresh token
# encerra. _sessao_expirada_no_servidor() é a função central desse contrato.
# ==============================================================================
from auth.auth_service import AuthResult  # noqa: E402


def _cliente_get_user_falha():
    """Mock de cliente cujo get_user SEMPRE falha — força o caminho de renovação por refresh_token."""
    _c = MagicMock()
    _c.auth.get_user.side_effect = Exception("jwt expired")
    return _c


def test_falha_transiente_na_renovacao_mantem_a_sessao(monkeypatch):
    session_manager._iniciar_sessao("u1", "a@b.com", "acc", "ref")
    monkeypatch.setattr(session_manager, "obter_cliente", lambda: _cliente_get_user_falha())
    monkeypatch.setattr(session_manager.auth_service, "renovar_sessao",
                        lambda _rt: AuthResult(False, "rede caiu", {"transiente": True}))
    assert session_manager._sessao_expirada_no_servidor() is False   # NÃO expira
    assert st.session_state.get("_auth_recheck_curto") is True        # agenda nova tentativa em breve


def test_rejeicao_definitiva_encerra_a_sessao(monkeypatch):
    session_manager._iniciar_sessao("u1", "a@b.com", "acc", "ref")
    monkeypatch.setattr(session_manager, "obter_cliente", lambda: _cliente_get_user_falha())
    monkeypatch.setattr(session_manager.auth_service, "renovar_sessao",
                        lambda _rt: AuthResult(False, "refresh revogado", {"transiente": False}))
    assert session_manager._sessao_expirada_no_servidor() is True    # expira DE VERDADE


def test_renovacao_bem_sucedida_atualiza_tokens_e_mantem_a_sessao(monkeypatch):
    session_manager._iniciar_sessao("u1", "a@b.com", "acc-velho", "ref-velho")
    monkeypatch.setattr(session_manager, "obter_cliente", lambda: _cliente_get_user_falha())
    monkeypatch.setattr(session_manager.auth_service, "renovar_sessao",
                        lambda _rt: AuthResult(True, "ok", {"user_id": "u1", "email": "a@b.com",
                                                            "access_token": "acc-novo",
                                                            "refresh_token": "ref-novo"}))
    assert session_manager._sessao_expirada_no_servidor() is False
    assert st.session_state["auth_access_token"] == "acc-novo"
    assert st.session_state["auth_refresh_token"] == "ref-novo"
    assert st.session_state.get("_auth_recheck_curto") is False


def test_sem_cliente_supabase_nunca_expira(monkeypatch):
    session_manager._iniciar_sessao("u1", "a@b.com", "acc", "ref")
    monkeypatch.setattr(session_manager, "obter_cliente", lambda: None)
    assert session_manager._sessao_expirada_no_servidor() is False   # fail-open sem servidor


def test_dados_sem_flag_transiente_faz_fail_open(monkeypatch):
    # se a renovação falhar sem dizer 'transiente' (dados vazio), o default é MANTER logado
    session_manager._iniciar_sessao("u1", "a@b.com", "acc", "ref")
    monkeypatch.setattr(session_manager, "obter_cliente", lambda: _cliente_get_user_falha())
    monkeypatch.setattr(session_manager.auth_service, "renovar_sessao",
                        lambda _rt: AuthResult(False, "erro qualquer", {}))
    assert session_manager._sessao_expirada_no_servidor() is False
