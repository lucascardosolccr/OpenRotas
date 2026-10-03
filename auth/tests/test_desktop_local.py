# -*- coding: utf-8 -*-
"""Bypass de login LOCAL (modo desktop offline) — auth/session_manager.

Trava a NÃO-REGRESSÃO da web: sem a env OPENROTAS_DESKTOP_LOCAL, o modo local está DESLIGADO e
nada muda no caminho online. Com a env ligada (o que só o launcher do desktop faz), uma sessão
LOCAL é estabelecida sem bater no Supabase."""
import logging

import pytest

logging.disable(logging.WARNING)

import streamlit as st  # noqa: E402

from auth import session_manager as sm  # noqa: E402


@pytest.fixture(autouse=True)
def _limpa(monkeypatch):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    monkeypatch.delenv("OPENROTAS_DESKTOP_LOCAL", raising=False)
    yield


def test_web_padrao_modo_local_desligado(monkeypatch):
    # Sem a env (= ambiente web), o modo local NUNCA liga. Zero regressão.
    assert sm._modo_desktop_local() is False
    assert sm.esta_autenticado() is False  # nada de sessão fantasma


def test_env_liga_modo_local(monkeypatch):
    monkeypatch.setenv("OPENROTAS_DESKTOP_LOCAL", "1")
    assert sm._modo_desktop_local() is True


def test_env_valor_diferente_de_1_nao_liga(monkeypatch):
    monkeypatch.setenv("OPENROTAS_DESKTOP_LOCAL", "0")
    assert sm._modo_desktop_local() is False
    monkeypatch.setenv("OPENROTAS_DESKTOP_LOCAL", "true")
    assert sm._modo_desktop_local() is False  # só "1" liga (estrito)


def test_iniciar_sessao_local_estabelece_sentinela():
    assert sm.esta_autenticado() is False
    sm._iniciar_sessao_local()
    assert sm.esta_autenticado() is True
    assert st.session_state["auth_user_id"] == sm._LOCAL_USER_ID
    assert st.session_state["auth_access_token"] == "LOCAL"  # não autoriza nada no servidor
    assert st.session_state["auth_refresh_token"] == ""      # sem refresh (offline)
    u = sm.usuario_atual()
    assert u and u["user_id"] == sm._LOCAL_USER_ID
