# -*- coding: utf-8 -*-
"""Testes dos recursos persistentes do usuário (estudos salvos, anotações) com um cliente
Supabase FALSO em memória — SEM rede.

Objetivo central (pedido do usuário): garantir que um estudo salvo no perfil continue
atrelado à CONTA e não à sessão do navegador. Ou seja: salvar numa sessão e, depois de
"sair + fechar o navegador + logar de novo" (tokens NOVOS), o estudo tem de reaparecer.
Modelamos o banco como um dicionário compartilhado entre clientes (como o Postgres do
Supabase é compartilhado entre sessões), e provamos o round-trip por user_id."""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

logging.disable(logging.WARNING)

from auth import auth_service  # noqa: E402


class _FakeQuery:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._op = None
        self._payload = None
        self._filters = {}

    def insert(self, data):
        self._op, self._payload = "insert", data
        return self

    def select(self, *a, **k):
        self._op = "select"
        return self

    def update(self, data):
        self._op, self._payload = "update", data
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, key, val):
        self._filters[key] = val
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def _match(self, row):
        return all(row.get(k) == v for k, v in self._filters.items())

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._op == "insert":
            import uuid
            r = dict(self._payload)
            r.setdefault("id", str(uuid.uuid4()))
            rows.append(r)
            return SimpleNamespace(data=[r])
        if self._op == "select":
            return SimpleNamespace(data=[dict(r) for r in rows if self._match(r)])
        if self._op == "delete":
            keep = [r for r in rows if not self._match(r)]
            self._store[self._table] = keep
            return SimpleNamespace(data=[])
        if self._op == "update":
            for r in rows:
                if self._match(r):
                    r.update(self._payload)
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[])


class _FakeClient:
    """Cliente Supabase falso; compartilha o mesmo 'banco' (store) entre instâncias —
    exatamente como sessões diferentes falam com o MESMO Postgres."""
    def __init__(self, store):
        self._store = store
        self.auth = MagicMock()

    def table(self, name):
        return _FakeQuery(self._store, name)


def test_estudo_salvo_persiste_entre_sessoes_diferentes(monkeypatch):
    _banco = {}
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _FakeClient(_banco))

    # Sessão 1 (primeiro login): usuário salva um estudo.
    _r = auth_service.salvar_estudo(
        "user-42", "Meu estudo nacional", "lote",
        {"linhas_total": 10}, [{"Origem": "A", "Destino": "B"}],
        access_token="TOKEN_SESSAO_1", refresh_token="REFRESH_1")
    assert _r.ok

    # "Sai do perfil + fecha o navegador + loga de novo": NOVA sessão, tokens DIFERENTES.
    _lista = auth_service.listar_estudos(
        "user-42", access_token="TOKEN_SESSAO_2_NOVO", refresh_token="REFRESH_2_NOVO")
    assert len(_lista) == 1
    assert _lista[0]["nome"] == "Meu estudo nacional"

    # E dá para CARREGAR os dados completos na nova sessão (restaurar).
    _full = auth_service.carregar_estudo(
        "user-42", _lista[0]["id"], access_token="TOKEN_SESSAO_2_NOVO", refresh_token="REFRESH_2_NOVO")
    assert _full is not None
    assert _full["dados"] == [{"Origem": "A", "Destino": "B"}]


def test_estudo_de_um_usuario_nao_aparece_para_outro(monkeypatch):
    _banco = {}
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _FakeClient(_banco))
    auth_service.salvar_estudo("user-A", "Estudo do A", "lote", {}, [{"x": 1}], "AT", "RT")
    # Outro usuário não enxerga (isolamento por user_id — no Supabase real, reforçado por RLS).
    assert auth_service.listar_estudos("user-B", "AT", "RT") == []
    assert len(auth_service.listar_estudos("user-A", "AT", "RT")) == 1


def test_anotacao_persiste_entre_sessoes(monkeypatch):
    _banco = {}
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _FakeClient(_banco))
    assert auth_service.criar_anotacao("user-1", "T", "conteúdo", "AT1", "RT1").ok
    _lista = auth_service.listar_anotacoes("user-1", "AT2_NOVO", "RT2_NOVO")
    assert len(_lista) == 1 and _lista[0]["titulo"] == "T"


def test_iniciar_login_social_mapeia_microsoft_para_azure_e_devolve_url():
    _cli = MagicMock()
    _cli.auth.sign_in_with_oauth.return_value = SimpleNamespace(url="https://provedor/autoriza?x=1")
    _r = auth_service.iniciar_login_social("microsoft", "https://app.exemplo/", _cli)
    assert _r.ok and _r.dados["url"].startswith("https://provedor/")
    _payload = _cli.auth.sign_in_with_oauth.call_args[0][0]
    assert _payload["provider"] == "azure"  # Microsoft = provider 'azure' no Supabase
    assert _payload["options"]["redirect_to"] == "https://app.exemplo/"


def test_iniciar_login_social_provedor_invalido():
    assert not auth_service.iniciar_login_social("orkut", "https://app/", MagicMock()).ok


def test_finalizar_login_social_troca_code_por_sessao():
    _cli = MagicMock()
    _cli.auth.exchange_code_for_session.return_value = SimpleNamespace(
        session=SimpleNamespace(access_token="AT", refresh_token="RT"),
        user=SimpleNamespace(id="uid-9", email="g@x.com"))
    _r = auth_service.finalizar_login_social("o-code", _cli)
    assert _r.ok
    assert _r.dados == {"user_id": "uid-9", "email": "g@x.com", "access_token": "AT", "refresh_token": "RT"}


def test_finalizar_login_social_sem_code():
    assert not auth_service.finalizar_login_social("", MagicMock()).ok


def test_cliente_do_usuario_renova_quando_access_token_vencido(monkeypatch):
    """Se o access_token estiver vencido (comum após ficar fora), set_session falha e a
    função renova via refresh_session — garantindo que a leitura dos dados salvos funcione
    de forma confiável no re-login."""
    _c = MagicMock()
    _c.auth.set_session.side_effect = Exception("token expired")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _c)
    _res = auth_service._cliente_do_usuario("AT_VENCIDO", "RT_VALIDO")
    assert _res is _c
    _c.auth.refresh_session.assert_called_once_with("RT_VALIDO")
