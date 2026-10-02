# -*- coding: utf-8 -*-
"""Testes de auth/supabase_client.py — CONTRATO DE CONSTRUÇÃO do cliente Supabase.

Trava a correção do logout no meio de estudos longos: o cliente compartilhado
(`obter_cliente()`) DEVE ser criado com o auto-refresh em thread de fundo DESLIGADO
(`auto_refresh_token=False`). Se alguém reverter isso, o supabase-py volta a disparar
um threading.Timer que renova o token numa thread de fundo e, como o refresh_token é
ROTATIVO, rotaciona o token por trás do st.session_state -> 400 -> logout forçado no
meio do processamento. Este teste é a rede de segurança contra essa regressão.

Nada aqui bate na rede: `create_client` é substituído por um gravador que apenas
captura as `options` com que o cliente seria construído."""
import logging

import pytest

logging.disable(logging.WARNING)

import streamlit as st  # noqa: E402

from auth import supabase_client  # noqa: E402


class _SecretsFake:
    """Mimetiza st.secrets.get(...) com credenciais válidas (sem arquivo secrets.toml)."""
    def __init__(self, dados):
        self._d = dict(dados)

    def get(self, chave, padrao=None):
        return self._d.get(chave, padrao)


@pytest.fixture
def _credenciais_ok(monkeypatch):
    monkeypatch.setattr(supabase_client.st, "secrets", _SecretsFake({
        "SUPABASE_URL": "https://projeto-fake.supabase.co",
        "SUPABASE_ANON_KEY": "anon-publica-fake",
    }))
    # o cliente é cacheado por processo (@st.cache_resource) — limpa antes e depois para
    # que CADA teste execute o corpo de verdade e não vaze o sentinel para outros testes.
    try:
        supabase_client.obter_cliente.clear()
    except Exception:
        pass
    yield
    try:
        supabase_client.obter_cliente.clear()
    except Exception:
        pass


def test_obter_cliente_desliga_auto_refresh_em_thread_de_fundo(_credenciais_ok, monkeypatch):
    """O contrato central: o cliente compartilhado NÃO pode ter o auto-refresh de fundo ligado."""
    _capturado = {}

    def _create_client_fake(_url, _key, options=None):
        _capturado["url"] = _url
        _capturado["key"] = _key
        _capturado["options"] = options
        return object()  # sentinel: não é None -> quem chama trata como "cliente ok"

    monkeypatch.setattr(supabase_client, "create_client", _create_client_fake)

    _cli = supabase_client.obter_cliente()

    assert _cli is not None, "deveria devolver um cliente quando as credenciais existem"
    _opts = _capturado.get("options")
    assert _opts is not None, "o cliente DEVE ser construído com ClientOptions explícitas"
    # O coração da correção: sem refresher de fundo competindo com o refresh manual da app.
    assert getattr(_opts, "auto_refresh_token", True) is False, (
        "auto_refresh_token DEVE ser False — senão volta a corrida de rotação de token "
        "que desloga o usuário no meio de estudos longos")
    # Singleton compartilhado por processo: não deve guardar sessão de usuário no storage do SDK.
    assert getattr(_opts, "persist_session", True) is False
    # Usa a anon key pública recebida (segurança via RLS) — nunca inventa credencial.
    assert _capturado["key"] == "anon-publica-fake"
    assert _capturado["url"] == "https://projeto-fake.supabase.co"


def test_obter_cliente_sem_credenciais_devolve_none(monkeypatch):
    """Sem SUPABASE_URL/ANON_KEY -> None (nunca levanta, nunca adivinha credencial)."""
    monkeypatch.setattr(supabase_client.st, "secrets", _SecretsFake({}))
    try:
        supabase_client.obter_cliente.clear()
    except Exception:
        pass
    # se o corpo chegasse a create_client, falharia o teste (não deve chegar)
    monkeypatch.setattr(supabase_client, "create_client",
                        lambda *a, **k: pytest.fail("não deveria criar cliente sem credenciais"))
    try:
        assert supabase_client.obter_cliente() is None
    finally:
        try:
            supabase_client.obter_cliente.clear()
        except Exception:
            pass


def test_obter_cliente_fallback_quando_clientoptions_indisponivel(_credenciais_ok, monkeypatch):
    """Se o create_client com options falhar (versão do SDK sem os campos), cai para o
    create_client SEM options — nunca levanta, sempre devolve um cliente utilizável."""
    _chamadas = {"com_options": 0, "sem_options": 0}

    def _create_client_fake(_url, _key, options=None):
        if options is not None:
            _chamadas["com_options"] += 1
            raise TypeError("ClientOptions incompatível nesta versão do SDK")
        _chamadas["sem_options"] += 1
        return object()

    monkeypatch.setattr(supabase_client, "create_client", _create_client_fake)

    _cli = supabase_client.obter_cliente()
    assert _cli is not None
    assert _chamadas["com_options"] == 1, "deve TENTAR primeiro com as options (auto-refresh off)"
    assert _chamadas["sem_options"] == 1, "e cair para o fallback sem options se a 1ª tentativa falhar"
