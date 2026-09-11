# -*- coding: utf-8 -*-
"""Camada de serviço de autenticação — único ponto que fala com o Supabase Auth.

Design deliberado: a senha do usuário NUNCA é hasheada, comparada ou armazenada por este
módulo — isso é delegado inteiramente ao Supabase Auth (bcrypt internamente, já auditado em
produção por terceiros), evitando reimplementar a parte mais sensível do sistema. Este
módulo só traduz chamadas da aplicação em chamadas ao SDK, e respostas do SDK em mensagens
seguras para o usuário — nunca vaza detalhe interno (stack trace, existência de e-mail,
etc.) na mensagem de erro devolvida.

Cada função devolve um `AuthResult` (nunca lança) — quem chama sempre trata `ok`/`erro`,
nunca precisa de try/except ao redor de uma chamada deste módulo.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import streamlit as st

from auth.supabase_client import obter_cliente

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    ok: bool
    mensagem: str = ""
    dados: dict = field(default_factory=dict)


# ==============================================================================
# [RATE-LIMIT - proteção contra brute force / abuso] Throttle POR SESSÃO DE NAVEGADOR —
# mesmo padrão já usado em streamlit_app.py para o envio de tickets (_smtp_tickets_enviados).
# Isto é defesa em profundidade, NÃO o mecanismo principal: o Supabase Auth já aplica rate
# limiting no lado do servidor para os endpoints de autenticação (login, envio de OTP) —
# ver a documentação de "Rate Limits" do projeto Supabase para os limiares atuais, que podem
# mudar sem aviso deste código. Este throttle client-side cobre o caso de um mesmo navegador
# insistindo repetidamente ANTES de bater no limite do servidor, e funciona mesmo se o
# Supabase não estiver configurado (modo demonstração).
# ==============================================================================

def _rate_limit_excedido(chave: str, max_tentativas: int, janela_segundos: int) -> bool:
    try:
        _agora = time.time()
        _hist_key = f"_auth_rl_{chave}"
        _hist = [t for t in st.session_state.get(_hist_key, []) if _agora - t < janela_segundos]
        if len(_hist) >= max_tentativas:
            st.session_state[_hist_key] = _hist
            return True
        _hist.append(_agora)
        st.session_state[_hist_key] = _hist
        return False
    except Exception:
        return False  # fail-open no throttle client-side; o servidor continua protegendo


def _mensagem_login_generica() -> str:
    # [ANTI-ENUMERATION - §19] nunca diz qual dos dois (e-mail ou senha) está errado, nem
    # se o e-mail existe — uma mensagem específica demais vira um oráculo de enumeração.
    return "E-mail ou senha incorretos."


# ==============================================================================
# Cadastro
# ==============================================================================

def cadastrar(email: str, senha: str, nome_completo: str, telefone: str) -> AuthResult:
    """Cria a conta no Supabase Auth (que já hasheia e armazena a senha com segurança) com
    nome/telefone como metadados do usuário — um TRIGGER no banco (ver auth/schema.sql)
    cria a linha correspondente em `public.profiles` automaticamente, então este módulo
    NUNCA insere diretamente na tabela de perfis (evita uma segunda fonte de verdade
    divergente do que o Supabase realmente autenticou)."""
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Autenticação indisponível no momento — tente novamente em instantes.")
    if _rate_limit_excedido("cadastro", max_tentativas=5, janela_segundos=600):
        return AuthResult(False, "Muitas tentativas de cadastro nesta sessão — aguarde alguns minutos.")
    try:
        _resp = _cliente.auth.sign_up({
            "email": email,
            "password": senha,
            "options": {"data": {"nome_completo": nome_completo, "telefone": telefone}},
        })
        if _resp.user is None:
            return AuthResult(False, "Não foi possível concluir o cadastro — confira os dados e tente novamente.")
        return AuthResult(True, "Cadastro realizado com sucesso.",
                          {"user_id": _resp.user.id, "email": _resp.user.email})
    except Exception as _e:
        _msg = str(_e).lower()
        if "already registered" in _msg or "already exists" in _msg or "user already" in _msg:
            # [ANTI-ENUMERATION] Aqui é aceitável ser explícito: é a PRÓPRIA pessoa tentando
            # cadastrar, o e-mail já é dela quem digitou — diferente de "esqueci minha senha"
            # (onde um ATACANTE poderia estar testando e-mails alheios).
            return AuthResult(False, "Este e-mail já possui uma conta — tente fazer login.")
        logger.error("[AUTH] Falha no cadastro.", exc_info=True)
        return AuthResult(False, "Não foi possível concluir o cadastro no momento — tente novamente mais tarde.")


# ==============================================================================
# Login / Logout
# ==============================================================================

def fazer_login(email: str, senha: str) -> AuthResult:
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Autenticação indisponível no momento — tente novamente em instantes.")
    if _rate_limit_excedido(f"login_{email}", max_tentativas=8, janela_segundos=300):
        return AuthResult(False, "Muitas tentativas de login — aguarde alguns minutos antes de tentar de novo.")
    try:
        _resp = _cliente.auth.sign_in_with_password({"email": email, "password": senha})
        if _resp.user is None or _resp.session is None:
            return AuthResult(False, _mensagem_login_generica())
        return AuthResult(True, "Login realizado.", {
            "user_id": _resp.user.id, "email": _resp.user.email,
            "access_token": _resp.session.access_token, "refresh_token": _resp.session.refresh_token,
        })
    except Exception:
        logger.error("[AUTH] Falha no login.", exc_info=True)
        return AuthResult(False, _mensagem_login_generica())


def fazer_logout() -> AuthResult:
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(True, "Sessão local encerrada.")  # nada a invalidar no servidor
    try:
        _cliente.auth.sign_out()
    except Exception:
        logger.debug("[AUTH] Falha ao invalidar sessão no servidor (sessão local será limpa de qualquer forma).",
                     exc_info=True)
    return AuthResult(True, "Você saiu da sua conta.")


# ==============================================================================
# Recuperação de senha (código de 6 dígitos por e-mail, via OTP nativo do Supabase)
# ==============================================================================

def solicitar_recuperacao_senha(email: str) -> AuthResult:
    """Dispara o e-mail com o código de recuperação. SEMPRE devolve a mesma mensagem de
    sucesso, exista ou não uma conta com esse e-mail — é assim que o próprio Supabase se
    comporta (nunca revela via API se um e-mail está cadastrado), e replicar esse
    comportamento aqui evita reintroduzir a brecha de enumeração que o backend já evita."""
    _cliente = obter_cliente()
    _msg_padrao = ("Se este e-mail estiver cadastrado, você receberá um código de "
                   "recuperação em instantes.")
    if _cliente is None:
        return AuthResult(False, "Recuperação de senha indisponível no momento.")
    if _rate_limit_excedido(f"recuperacao_{email}", max_tentativas=3, janela_segundos=900):
        # Aqui SIM é seguro ser específico (a mensagem não revela nada sobre a CONTA, só
        # sobre a taxa de pedidos desta sessão) — protege contra "password reset abuse" (§19).
        return AuthResult(False, "Muitos pedidos de recuperação — aguarde alguns minutos.")
    try:
        _cliente.auth.reset_password_for_email(email)
    except Exception:
        logger.debug("[AUTH] reset_password_for_email retornou erro (não exposto ao usuário).", exc_info=True)
    return AuthResult(True, _msg_padrao)


def verificar_codigo_recuperacao(email: str, codigo: str) -> AuthResult:
    """Valida o código de 6 dígitos recebido por e-mail. Em caso de sucesso, o Supabase já
    abre uma sessão de recuperação (usada em seguida por `redefinir_senha`) — não
    precisamos gerar/armazenar nenhum token nós mesmos."""
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Recuperação de senha indisponível no momento.")
    if _rate_limit_excedido(f"verificar_otp_{email}", max_tentativas=5, janela_segundos=600):
        return AuthResult(False, "Muitas tentativas de código incorreto — solicite um novo código.")
    try:
        _resp = _cliente.auth.verify_otp({"email": email, "token": codigo, "type": "recovery"})
        if _resp.session is None:
            return AuthResult(False, "Código inválido ou expirado — solicite um novo.")
        return AuthResult(True, "Código válido.", {
            "access_token": _resp.session.access_token, "refresh_token": _resp.session.refresh_token,
        })
    except Exception:
        logger.debug("[AUTH] verify_otp falhou (código incorreto/expirado).", exc_info=True)
        return AuthResult(False, "Código inválido ou expirado — solicite um novo.")


def redefinir_senha(nova_senha: str, access_token: str, refresh_token: str) -> AuthResult:
    """Define a nova senha. Requer a sessão de recuperação aberta por
    `verificar_codigo_recuperacao` (os tokens são passados explicitamente, não lidos de
    st.session_state aqui, para manter esta função pura em relação ao Streamlit)."""
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Redefinição de senha indisponível no momento.")
    try:
        _cliente.auth.set_session(access_token, refresh_token)
        _cliente.auth.update_user({"password": nova_senha})
        return AuthResult(True, "Senha redefinida com sucesso — faça login com a nova senha.")
    except Exception:
        logger.error("[AUTH] Falha ao redefinir senha.", exc_info=True)
        return AuthResult(False, "Não foi possível redefinir a senha — o código pode ter expirado.")


# ==============================================================================
# Perfil
# ==============================================================================

def obter_perfil(user_id: str) -> Optional[dict]:
    """Lê a linha de `public.profiles` deste usuário (criada automaticamente pelo trigger
    no cadastro — ver auth/schema.sql). None (nunca lança) se indisponível/não encontrado."""
    _cliente = obter_cliente()
    if _cliente is None or not user_id:
        return None
    try:
        _resp = _cliente.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        _linhas = _resp.data or []
        return _linhas[0] if _linhas else None
    except Exception:
        logger.error("[AUTH] Falha ao ler perfil.", exc_info=True)
        return None


def atualizar_perfil(user_id: str, campos: dict) -> AuthResult:
    """Atualiza campos do perfil (nome/telefone/endereço) — NUNCA aceita alterar `id` ou
    `email` por aqui (e-mail tem fluxo próprio, com confirmação — ver §10 da missão)."""
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Atualização de perfil indisponível no momento.")
    _campos_seguros = {k: v for k, v in (campos or {}).items() if k not in ("id", "email", "user_id")}
    if not _campos_seguros:
        return AuthResult(False, "Nenhum campo válido para atualizar.")
    try:
        _cliente.table("profiles").update(_campos_seguros).eq("id", user_id).execute()
        return AuthResult(True, "Perfil atualizado com sucesso.")
    except Exception:
        logger.error("[AUTH] Falha ao atualizar perfil.", exc_info=True)
        return AuthResult(False, "Não foi possível atualizar o perfil no momento.")


def solicitar_alteracao_email(novo_email: str) -> AuthResult:
    """[§10] Alteração de e-mail com tratamento especial: dispara a confirmação do
    Supabase para o NOVO endereço — só é efetivada depois que o usuário clicar no link de
    confirmação recebido lá (nunca troca o e-mail imediatamente)."""
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Alteração de e-mail indisponível no momento.")
    if _rate_limit_excedido("alterar_email", max_tentativas=3, janela_segundos=900):
        return AuthResult(False, "Muitos pedidos de alteração de e-mail — aguarde alguns minutos.")
    try:
        _cliente.auth.update_user({"email": novo_email})
        return AuthResult(True, "Enviamos um e-mail de confirmação para o novo endereço — "
                                "a alteração só entra em vigor depois que você confirmar por lá.")
    except Exception:
        logger.error("[AUTH] Falha ao solicitar alteração de e-mail.", exc_info=True)
        return AuthResult(False, "Não foi possível iniciar a alteração de e-mail no momento.")
