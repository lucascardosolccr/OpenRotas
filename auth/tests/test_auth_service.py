# -*- coding: utf-8 -*-
"""Testes de auth/auth_service.py com um cliente Supabase FALSO (nenhuma chamada de rede).

Verifica: (a) que este módulo chama o SDK com os argumentos certos, (b) que traduz as
respostas em AuthResult corretamente, (c) que nunca vaza detalhe interno na mensagem de
erro, (d) que o rate limit por sessão funciona. Nada aqui depende de um projeto Supabase
real — é exatamente o motivo de existir uma camada de serviço fina: o resto da aplicação
nunca precisa saber que existe uma chamada de rede por trás."""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

logging.disable(logging.WARNING)

import streamlit as st  # noqa: E402

from auth import auth_service  # noqa: E402


@pytest.fixture(autouse=True)
def _limpar_session_state():
    # Isola o rate-limit (guardado em st.session_state) entre testes.
    for _k in list(st.session_state.keys()):
        del st.session_state[_k]
    yield


def _cliente_falso():
    return MagicMock()


# ==============================================================================
# cadastrar
# ==============================================================================

def test_cadastrar_sucesso_chama_sign_up_com_metadados(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="uid-1", email="a@b.com"))
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.cadastrar("a@b.com", "SenhaForte123!", "Fulano de Tal", "+5511987654321")

    assert _res.ok
    assert _res.dados["user_id"] == "uid-1"
    _args, _kwargs = _cliente.auth.sign_up.call_args
    _payload = _args[0]
    assert _payload["email"] == "a@b.com"
    assert _payload["password"] == "SenhaForte123!"
    assert _payload["options"]["data"]["nome_completo"] == "Fulano de Tal"
    assert _payload["options"]["data"]["telefone"] == "+5511987654321"


def test_cadastrar_email_duplicado_mensagem_especifica(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_up.side_effect = Exception("User already registered")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.cadastrar("a@b.com", "SenhaForte123!", "Fulano de Tal", "+5511987654321")
    assert not _res.ok
    assert "já possui uma conta" in _res.mensagem


def test_cadastrar_erro_generico_nao_vaza_detalhe_interno(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_up.side_effect = Exception("connection refused to internal-db-host:5432")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.cadastrar("a@b.com", "SenhaForte123!", "Fulano de Tal", "+5511987654321")
    assert not _res.ok
    assert "internal-db-host" not in _res.mensagem
    assert "5432" not in _res.mensagem


def test_cadastrar_sem_cliente_configurado_falha_com_seguranca(monkeypatch):
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: None)
    _res = auth_service.cadastrar("a@b.com", "SenhaForte123!", "Fulano de Tal", "+5511987654321")
    assert not _res.ok


def test_cadastrar_rate_limit_apos_5_tentativas(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_up.return_value = SimpleNamespace(user=None)
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    for _ in range(5):
        auth_service.cadastrar("a@b.com", "SenhaForte123!", "Fulano de Tal", "+5511987654321")
    _res = auth_service.cadastrar("a@b.com", "SenhaForte123!", "Fulano de Tal", "+5511987654321")
    assert not _res.ok
    assert "muitas tentativas" in _res.mensagem.lower()


# ==============================================================================
# fazer_login
# ==============================================================================

def test_fazer_login_sucesso(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="uid-1", email="a@b.com"),
        session=SimpleNamespace(access_token="tok-a", refresh_token="tok-r"))
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.fazer_login("a@b.com", "SenhaForte123!")
    assert _res.ok
    assert _res.dados["access_token"] == "tok-a"


def test_fazer_login_credenciais_incorretas_mensagem_generica_nao_revela_qual_campo(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.fazer_login("a@b.com", "SenhaErrada")
    assert not _res.ok
    assert _res.mensagem == "E-mail ou senha incorretos."


def test_fazer_login_usuario_inexistente_mesma_mensagem_generica(monkeypatch):
    # [ANTI-ENUMERATION] usuário inexistente e senha errada devem produzir a MESMA
    # mensagem — nunca dar pista de qual dos dois casos ocorreu.
    _cliente = _cliente_falso()
    _cliente.auth.sign_in_with_password.side_effect = Exception("User not found")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.fazer_login("naoexiste@b.com", "QualquerSenha1!")
    assert _res.mensagem == "E-mail ou senha incorretos."


def test_fazer_login_rate_limit_e_por_email_nao_global(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    for _ in range(8):
        auth_service.fazer_login("a@b.com", "x")
    _res_a = auth_service.fazer_login("a@b.com", "x")
    assert "muitas tentativas" in _res_a.mensagem.lower()
    # outro e-mail, mesma sessão -> ainda não deve estar limitado (throttle por chave, não global).
    _res_b = auth_service.fazer_login("outro@b.com", "x")
    assert "muitas tentativas" not in _res_b.mensagem.lower()


# ==============================================================================
# fazer_logout
# ==============================================================================

def test_fazer_logout_chama_sign_out(monkeypatch):
    _cliente = _cliente_falso()
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)
    _res = auth_service.fazer_logout()
    assert _res.ok
    _cliente.auth.sign_out.assert_called_once()


def test_fazer_logout_sem_cliente_ainda_e_sucesso_local(monkeypatch):
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: None)
    _res = auth_service.fazer_logout()
    assert _res.ok  # nada a invalidar no servidor, mas a sessão local é considerada encerrada


# ==============================================================================
# Recuperação de senha
# ==============================================================================

def test_solicitar_recuperacao_mensagem_identica_para_email_existente_ou_nao(monkeypatch):
    _cliente_ok = _cliente_falso()
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente_ok)
    _res1 = auth_service.solicitar_recuperacao_senha("existe@b.com")

    for _k in list(st.session_state.keys()):
        del st.session_state[_k]
    _cliente_erro = _cliente_falso()
    _cliente_erro.auth.reset_password_for_email.side_effect = Exception("not found")
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente_erro)
    _res2 = auth_service.solicitar_recuperacao_senha("naoexiste@b.com")

    assert _res1.ok and _res2.ok
    assert _res1.mensagem == _res2.mensagem


def test_solicitar_recuperacao_rate_limit_apos_3_pedidos(monkeypatch):
    _cliente = _cliente_falso()
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)
    for _ in range(3):
        auth_service.solicitar_recuperacao_senha("a@b.com")
    _res = auth_service.solicitar_recuperacao_senha("a@b.com")
    assert not _res.ok
    assert "muitos pedidos" in _res.mensagem.lower()


def test_verificar_codigo_recuperacao_sucesso(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.verify_otp.return_value = SimpleNamespace(
        session=SimpleNamespace(access_token="tok-a", refresh_token="tok-r"))
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.verificar_codigo_recuperacao("a@b.com", "123456")
    assert _res.ok
    _args, _ = _cliente.auth.verify_otp.call_args
    assert _args[0] == {"email": "a@b.com", "token": "123456", "type": "recovery"}


def test_verificar_codigo_recuperacao_codigo_errado(monkeypatch):
    _cliente = _cliente_falso()
    _cliente.auth.verify_otp.return_value = SimpleNamespace(session=None)
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.verificar_codigo_recuperacao("a@b.com", "000000")
    assert not _res.ok


def test_redefinir_senha_sucesso(monkeypatch):
    _cliente = _cliente_falso()
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.redefinir_senha("NovaSenhaForte1!", "tok-a", "tok-r")
    assert _res.ok
    _cliente.auth.set_session.assert_called_once_with("tok-a", "tok-r")
    _cliente.auth.update_user.assert_called_once_with({"password": "NovaSenhaForte1!"})


# ==============================================================================
# Perfil
# ==============================================================================

def test_obter_perfil_sucesso(monkeypatch):
    _cliente = _cliente_falso()
    _query = _cliente.table.return_value.select.return_value.eq.return_value.limit.return_value
    _query.execute.return_value = SimpleNamespace(data=[{"id": "uid-1", "nome_completo": "Fulano"}])
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _perfil = auth_service.obter_perfil("uid-1")
    assert _perfil == {"id": "uid-1", "nome_completo": "Fulano"}


def test_obter_perfil_aplica_sessao_do_usuario_para_rls(monkeypatch):
    """A leitura do perfil DEVE aplicar a sessão do usuário (set_session com os tokens) antes
    de consultar — senão a RLS (auth.uid() = id) bloqueia e o perfil 'some'. Regressão do bug
    'Não foi possível carregar seu perfil' no login social."""
    _cliente = _cliente_falso()
    _query = _cliente.table.return_value.select.return_value.eq.return_value.limit.return_value
    _query.execute.return_value = SimpleNamespace(data=[{"id": "uid-1", "nome_completo": "Fulano"}])
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _perfil = auth_service.obter_perfil("uid-1", access_token="AT", refresh_token="RT")
    assert _perfil == {"id": "uid-1", "nome_completo": "Fulano"}
    _cliente.auth.set_session.assert_called_once_with("AT", "RT")


def test_obter_perfil_nao_encontrado_e_none(monkeypatch):
    _cliente = _cliente_falso()
    _query = _cliente.table.return_value.select.return_value.eq.return_value.limit.return_value
    _query.execute.return_value = SimpleNamespace(data=[])
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    assert auth_service.obter_perfil("uid-inexistente") is None


def test_obter_perfil_sem_user_id_e_none(monkeypatch):
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente_falso())
    assert auth_service.obter_perfil("") is None


def test_atualizar_perfil_remove_campos_perigosos(monkeypatch):
    _cliente = _cliente_falso()
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    auth_service.atualizar_perfil("uid-1", {"nome_completo": "Novo Nome", "email": "outro@b.com",
                                            "id": "uid-2", "telefone": "+5511900000000"})
    _args, _ = _cliente.table.return_value.update.call_args
    _campos_enviados = _args[0]
    assert "email" not in _campos_enviados
    assert "id" not in _campos_enviados
    assert _campos_enviados["nome_completo"] == "Novo Nome"
    assert _campos_enviados["telefone"] == "+5511900000000"


def test_atualizar_perfil_sem_campos_validos_nao_chama_update(monkeypatch):
    _cliente = _cliente_falso()
    monkeypatch.setattr(auth_service, "obter_cliente", lambda: _cliente)

    _res = auth_service.atualizar_perfil("uid-1", {"email": "outro@b.com", "id": "x"})
    assert not _res.ok
    _cliente.table.return_value.update.assert_not_called()
