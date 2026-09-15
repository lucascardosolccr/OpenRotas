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


def renovar_sessao(refresh_token: str) -> AuthResult:
    """[PERSISTÊNCIA DE SESSÃO] Troca um refresh_token ainda válido por um novo par de
    tokens, sem exigir novo login. O access_token do Supabase é um JWT de vida curta
    (~1h por padrão) — isso é normal e esperado, não uma sessão "expirada" de verdade; é
    o refresh_token (vida bem mais longa) quem garante que o usuário continue logado
    enquanto o navegador permanecer aberto. Usado por `session_manager` na revalidação
    periódica, para renovar silenciosamente em vez de derrubar a sessão."""
    _cliente = obter_cliente()
    if _cliente is None or not refresh_token:
        return AuthResult(False, "Não foi possível renovar a sessão no momento.")
    try:
        _resp = _cliente.auth.refresh_session(refresh_token)
        if _resp.session is None or _resp.user is None:
            return AuthResult(False, "Sessão não pôde ser renovada — faça login novamente.")
        return AuthResult(True, "Sessão renovada.", {
            "user_id": _resp.user.id, "email": _resp.user.email,
            "access_token": _resp.session.access_token, "refresh_token": _resp.session.refresh_token,
        })
    except Exception:
        logger.debug("[AUTH] Falha ao renovar sessão via refresh_token.", exc_info=True)
        return AuthResult(False, "Sessão não pôde ser renovada — faça login novamente.")


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


def alterar_senha_logado(email: str, senha_atual: str, nova_senha: str) -> AuthResult:
    """[Perfil] Troca de senha para um usuário JÁ AUTENTICADO. Por segurança, RE-VERIFICA a
    senha atual antes de trocar (impede que alguém troque a senha numa sessão deixada aberta):
    faz um sign_in_with_password com a senha atual — se falhar, aborta; se passar, o próprio
    cliente fica autenticado com a sessão recém-aberta e então `update_user` aplica a nova
    senha. Delegado 100% ao Supabase Auth (nunca reimplementamos hashing/validação de senha).
    O rate-limit protege contra tentativa de adivinhação da senha atual."""
    _cliente = obter_cliente()
    if _cliente is None:
        return AuthResult(False, "Alteração de senha indisponível no momento.")
    if _rate_limit_excedido(f"trocar_senha_{email}", max_tentativas=5, janela_segundos=900):
        return AuthResult(False, "Muitas tentativas — aguarde alguns minutos antes de tentar de novo.")
    try:
        _resp = _cliente.auth.sign_in_with_password({"email": email, "password": senha_atual})
        if _resp is None or _resp.user is None or _resp.session is None:
            return AuthResult(False, "Senha atual incorreta.")
    except Exception:
        logger.debug("[AUTH] Re-verificação da senha atual falhou na troca de senha.", exc_info=True)
        return AuthResult(False, "Senha atual incorreta.")
    try:
        _cliente.auth.update_user({"password": nova_senha})
        return AuthResult(True, "Senha alterada com sucesso.")
    except Exception:
        logger.error("[AUTH] Falha ao aplicar a nova senha (usuário logado).", exc_info=True)
        return AuthResult(False, "Não foi possível alterar a senha no momento — tente novamente em instantes.")


# ==============================================================================
# Perfil
# ==============================================================================

def obter_perfil(user_id: str, access_token: str = "", refresh_token: str = "") -> Optional[dict]:
    """Lê a linha de `public.profiles` deste usuário (criada automaticamente pelo trigger
    no cadastro — ver auth/schema.sql). None (nunca lança) se indisponível/não encontrado.

    A tabela `profiles` tem RLS (select: auth.uid() = id), então é OBRIGATÓRIO aplicar a
    sessão do usuário (tokens) antes de ler — com o cliente anônimo, auth.uid() é nulo e a
    consulta volta vazia. Serve tanto login por e-mail quanto login social (Google)."""
    _cliente = _cliente_do_usuario(access_token, refresh_token)
    if _cliente is None or not user_id:
        return None
    try:
        _resp = _cliente.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        _linhas = _resp.data or []
        return _linhas[0] if _linhas else None
    except Exception:
        logger.error("[AUTH] Falha ao ler perfil.", exc_info=True)
        return None


def atualizar_perfil(user_id: str, campos: dict,
                     access_token: str = "", refresh_token: str = "") -> AuthResult:
    """Atualiza campos do perfil (nome/telefone/endereço) — NUNCA aceita alterar `id` ou
    `email` por aqui (e-mail tem fluxo próprio, com confirmação — ver §10 da missão).
    Aplica a sessão do usuário (RLS: update exige auth.uid() = id)."""
    _cliente = _cliente_do_usuario(access_token, refresh_token)
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


# ==============================================================================
# Login social (Google / Microsoft) — OAuth PKCE do Supabase, tocado À MÃO
# ------------------------------------------------------------------------------
# Mantém UM só tipo de usuário: quem entra com Google/Microsoft vira um usuário
# comum do Supabase (mesmo auth.users / mesmo user_id), então perfil, foto e
# estudos salvos funcionam igual ao login por e-mail/senha. 'microsoft' mapeia
# para o provider 'azure' do Supabase.
#
# POR QUE À MÃO (e não pelo SDK): o fluxo PKCE gera um segredo `code_verifier` no
# INÍCIO (ao clicar "Google") que precisa existir de novo no RETORNO (troca do
# `code` por sessão). O SDK guarda esse verifier na memória do PRÓPRIO cliente
# Supabase. Só que, ao voltar do Google, o navegador RECARREGA a página inteira e
# o Streamlit abre uma sessão NOVA — o `st.session_state` (e o cliente cacheado
# nele) é descartado, então o verifier some e a troca falha ("tente novamente").
# Solução: geramos o PKCE nós mesmos e guardamos o verifier em memória DE PROCESSO
# (módulo, não sessão), que sobrevive ao redirect. A troca do code é um POST HTTP
# direto ao endpoint /auth/v1/token?grant_type=pkce do Supabase (mesmo contrato
# que o SDK usa por baixo).
# ==============================================================================
import base64 as _base64
import hashlib as _hashlib
import secrets as _secrets
import threading as _threading
from urllib.parse import urlencode as _urlencode

import requests as _requests  # já em requirements.txt (usado por outras integrações)

_OAUTH_PROVIDERS = {"google": "google", "microsoft": "azure", "azure": "azure"}

# Guarda o code_verifier PENDENTE entre a ida ao provedor e a volta. É memória de
# PROCESSO (compartilhada por todas as sessões do mesmo servidor Streamlit), porque
# o retorno do OAuth recria a sessão do navegador. Guardamos só o pendente mais
# recente + carimbo de tempo (TTL curto) — simples e suficiente para a escala do app.
_PKCE_TTL_SEG = 600
_PKCE_LOCK = _threading.Lock()
_PKCE_PENDENTE: dict = {}  # {"verifier": str, "ts": float}


def _config_supabase():
    """(url, anon_key) de st.secrets — sem barra final na url. ('','') se ausente."""
    try:
        _url = str(st.secrets.get("SUPABASE_URL", "") or "").strip().rstrip("/")
        _key = str(st.secrets.get("SUPABASE_ANON_KEY", "") or "").strip()
    except Exception:
        _url, _key = "", ""
    return _url, _key


def _gerar_par_pkce():
    """(code_verifier, code_challenge) no formato exigido pelo PKCE (S256, base64url sem '=')."""
    _verifier = _base64.urlsafe_b64encode(_secrets.token_bytes(64)).decode("ascii").rstrip("=")
    _challenge = _base64.urlsafe_b64encode(
        _hashlib.sha256(_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return _verifier, _challenge


def iniciar_login_social(provedor: str, redirect_to: str = "", cliente=None) -> AuthResult:
    """Monta a URL de autorização do provedor (para a UI abrir num link) e guarda o
    code_verifier do PKCE em memória de processo, pronto para o retorno. `cliente` é ignorado
    (mantido só por compatibilidade de assinatura)."""
    _prov = _OAUTH_PROVIDERS.get((provedor or "").lower())
    if not _prov:
        return AuthResult(False, "Provedor de login não suportado.")
    _url, _key = _config_supabase()
    if not _url or not _key:
        return AuthResult(False, "Login social indisponível no momento (Supabase não configurado).")
    try:
        _verifier, _challenge = _gerar_par_pkce()
        _params = {
            "provider": _prov,
            "code_challenge": _challenge,
            "code_challenge_method": "s256",
        }
        if redirect_to:
            _params["redirect_to"] = redirect_to
        _auth_url = "%s/auth/v1/authorize?%s" % (_url, _urlencode(_params))
        with _PKCE_LOCK:
            _PKCE_PENDENTE["verifier"] = _verifier
            _PKCE_PENDENTE["ts"] = time.time()
        return AuthResult(True, "URL de login gerada.", {"url": _auth_url})
    except Exception:
        logger.error("[AUTH] Falha ao iniciar login social (%s).", _prov, exc_info=True)
        return AuthResult(False, "Não foi possível iniciar o login social — o provedor já está "
                                 "habilitado no painel do Supabase?")


def finalizar_login_social(code: str, cliente=None) -> AuthResult:
    """Troca o 'code' recebido no retorno por uma sessão do Supabase (POST PKCE), usando o
    code_verifier guardado em memória de processo no início. `cliente` é ignorado."""
    if not code:
        return AuthResult(False, "Código de autorização ausente.")
    _url, _key = _config_supabase()
    if not _url or not _key:
        return AuthResult(False, "Login social indisponível no momento (Supabase não configurado).")
    with _PKCE_LOCK:
        _pend = dict(_PKCE_PENDENTE)
    _verifier = _pend.get("verifier")
    _vencido = (not _verifier) or (time.time() - _pend.get("ts", 0) > _PKCE_TTL_SEG)
    if _vencido:
        return AuthResult(False, "A sessão de login expirou. Volte e clique em Google de novo.")
    try:
        _resp = _requests.post(
            "%s/auth/v1/token?grant_type=pkce" % _url,
            headers={"apikey": _key, "Authorization": "Bearer %s" % _key,
                     "Content-Type": "application/json"},
            json={"auth_code": code, "code_verifier": _verifier},
            timeout=20,
        )
        _dados = _resp.json() if _resp.content else {}
        _access = _dados.get("access_token")
        _refresh = _dados.get("refresh_token")
        _usuario = _dados.get("user") or {}
        if not _access or not _refresh or not _usuario.get("id"):
            _msg = str(_dados.get("error_description") or _dados.get("msg")
                       or _dados.get("error") or "")[:200]
            logger.error("[AUTH] Troca PKCE não retornou sessão (HTTP %s): %s",
                         getattr(_resp, "status_code", "?"), _msg or _dados)
            return AuthResult(False, "Não foi possível concluir o login social — tente novamente.")
        with _PKCE_LOCK:
            _PKCE_PENDENTE.clear()  # verifier é de uso único
        return AuthResult(True, "Login realizado.", {
            "user_id": _usuario.get("id"), "email": _usuario.get("email"),
            "access_token": _access, "refresh_token": _refresh,
        })
    except Exception:
        logger.error("[AUTH] Falha ao finalizar login social (troca de code).", exc_info=True)
        return AuthResult(False, "Não foi possível concluir o login social — tente novamente.")


# ==============================================================================
# [RECURSOS DO USUÁRIO] Anotações, estudos salvos e foto de perfil
# ------------------------------------------------------------------------------
# Estas operações mexem em tabelas protegidas por Row Level Security (auth.uid()
# = user_id). Como obter_cliente() devolve um cliente ANÔNIMO sem sessão, é
# obrigatório aplicar a sessão do usuário (set_session com os tokens guardados no
# app) ANTES de ler/gravar — senão auth.uid() é nulo e a RLS bloqueia tudo. Todas
# as funções são defensivas: nunca levantam, degradam com AuthResult/valor vazio.
# ==============================================================================

def _cliente_do_usuario(access_token: str = "", refresh_token: str = ""):
    """Cliente Supabase com a SESSÃO do usuário aplicada (para respeitar a RLS).
    None quando indisponível. Nunca levanta.

    [PERSISTÊNCIA] Os dados do usuário (estudos/anotações/avatar) vivem no BANCO,
    atrelados ao user_id — não à sessão do navegador. Ao logar de novo, os tokens
    são NOVOS; esta função aplica essa sessão e, se o access_token estiver vencido
    (comum após ficar tempo fora), tenta renová-lo pelo refresh_token antes de
    desistir — assim a leitura dos dados salvos funciona de forma confiável mesmo
    depois de fechar o navegador e voltar."""
    _c = obter_cliente()
    if _c is None:
        return None
    if not (access_token and refresh_token):
        return _c
    try:
        _c.auth.set_session(access_token, refresh_token)
        return _c
    except Exception:
        logger.debug("[AUTH] set_session falhou; tentando refresh_session.", exc_info=True)
    # access_token provavelmente vencido -> renova com o refresh_token (vida longa)
    try:
        _c.auth.refresh_session(refresh_token)
    except Exception:
        logger.debug("[AUTH] refresh_session também falhou ao preparar cliente do usuário.", exc_info=True)
    return _c


# ---- Anotações ---------------------------------------------------------------
def listar_anotacoes(user_id: str, access_token: str = "", refresh_token: str = "") -> list:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None or not user_id:
        return []
    try:
        _r = (_c.table("anotacoes").select("*").eq("user_id", user_id)
              .order("updated_at", desc=True).limit(200).execute())
        return _r.data or []
    except Exception:
        logger.error("[AUTH] Falha ao listar anotações.", exc_info=True)
        return []


def criar_anotacao(user_id: str, titulo: str, conteudo: str,
                   access_token: str = "", refresh_token: str = "") -> AuthResult:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Anotações indisponíveis no momento.")
    if not (titulo or "").strip() and not (conteudo or "").strip():
        return AuthResult(False, "Escreva um título ou um conteúdo para a anotação.")
    try:
        _c.table("anotacoes").insert({
            "user_id": user_id, "titulo": (titulo or "").strip()[:200],
            "conteudo": (conteudo or "").strip()[:20000]}).execute()
        return AuthResult(True, "Anotação salva.")
    except Exception:
        logger.error("[AUTH] Falha ao criar anotação.", exc_info=True)
        return AuthResult(False, "Não foi possível salvar a anotação (a tabela 'anotacoes' já foi criada no Supabase?).")


def atualizar_anotacao(user_id: str, anotacao_id: str, titulo: str, conteudo: str,
                       access_token: str = "", refresh_token: str = "") -> AuthResult:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Anotações indisponíveis no momento.")
    try:
        (_c.table("anotacoes").update({
            "titulo": (titulo or "").strip()[:200], "conteudo": (conteudo or "").strip()[:20000]})
         .eq("id", anotacao_id).eq("user_id", user_id).execute())
        return AuthResult(True, "Anotação atualizada.")
    except Exception:
        logger.error("[AUTH] Falha ao atualizar anotação.", exc_info=True)
        return AuthResult(False, "Não foi possível atualizar a anotação.")


def excluir_anotacao(user_id: str, anotacao_id: str,
                     access_token: str = "", refresh_token: str = "") -> AuthResult:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Anotações indisponíveis no momento.")
    try:
        _c.table("anotacoes").delete().eq("id", anotacao_id).eq("user_id", user_id).execute()
        return AuthResult(True, "Anotação excluída.")
    except Exception:
        logger.error("[AUTH] Falha ao excluir anotação.", exc_info=True)
        return AuthResult(False, "Não foi possível excluir a anotação.")


# ---- Estudos salvos ----------------------------------------------------------
def listar_estudos(user_id: str, access_token: str = "", refresh_token: str = "") -> list:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None or not user_id:
        return []
    try:
        _r = (_c.table("estudos_salvos").select("id,nome,tipo,resumo,created_at")
              .eq("user_id", user_id).order("created_at", desc=True).limit(50).execute())
        return _r.data or []
    except Exception:
        logger.error("[AUTH] Falha ao listar estudos salvos.", exc_info=True)
        return []


def salvar_estudo(user_id: str, nome: str, tipo: str, resumo: dict, dados,
                  access_token: str = "", refresh_token: str = "") -> AuthResult:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Salvar estudos indisponível no momento.")
    try:
        _c.table("estudos_salvos").insert({
            "user_id": user_id, "nome": (nome or "Estudo sem nome").strip()[:200],
            "tipo": (tipo or "lote")[:40], "resumo": resumo or {}, "dados": dados}).execute()
        return AuthResult(True, "Estudo salvo na sua conta.")
    except Exception:
        logger.error("[AUTH] Falha ao salvar estudo.", exc_info=True)
        return AuthResult(False, "Não foi possível salvar o estudo (a tabela 'estudos_salvos' já foi criada no Supabase?).")


def carregar_estudo(user_id: str, estudo_id: str,
                    access_token: str = "", refresh_token: str = "") -> dict | None:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return None
    try:
        _r = (_c.table("estudos_salvos").select("*").eq("id", estudo_id)
              .eq("user_id", user_id).limit(1).execute())
        _linhas = _r.data or []
        return _linhas[0] if _linhas else None
    except Exception:
        logger.error("[AUTH] Falha ao carregar estudo salvo.", exc_info=True)
        return None


def excluir_estudo(user_id: str, estudo_id: str,
                   access_token: str = "", refresh_token: str = "") -> AuthResult:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Excluir estudos indisponível no momento.")
    try:
        _c.table("estudos_salvos").delete().eq("id", estudo_id).eq("user_id", user_id).execute()
        return AuthResult(True, "Estudo excluído.")
    except Exception:
        logger.error("[AUTH] Falha ao excluir estudo salvo.", exc_info=True)
        return AuthResult(False, "Não foi possível excluir o estudo.")


# ---- Compartilhamento de estudos entre perfis --------------------------------
# Modelo: compartilha-se por E-MAIL do destinatário (o dono NÃO consegue resolver o id de outro
# usuário — a RLS de profiles só deixa cada um ver a própria linha). A tabela public.estudos_
# compartilhados guarda (owner_id, estudo_id, destinatario_email). O destinatário passa a poder LER
# a linha de estudos_salvos correspondente graças a uma policy de SELECT adicional (ver schema.sql),
# que casa o e-mail do compartilhamento com o e-mail do próprio perfil de quem consulta. Sem
# service_role, sem vazamento: tudo continua sob RLS.
def compartilhar_estudo(user_id: str, estudo_id: str, destinatario_email: str, mensagem: str = "",
                        access_token: str = "", refresh_token: str = "",
                        remetente_nome: str = "", remetente_email: str = "") -> AuthResult:
    """Compartilha um estudo do usuário com outro perfil, identificado pelo E-MAIL. Valida o e-mail,
    impede autocompartilhamento e exige que o estudo seja do próprio usuário. Idempotente por
    (estudo_id, destinatario_email) quando o índice único existir. Após persistir, dispara (best-effort)
    um e-mail de notificação ao destinatário. Defensivo/fail-open."""
    from auth.validators import validar_email
    _ok_mail, _email_norm, _msg = validar_email(destinatario_email)
    if not _ok_mail:
        return AuthResult(False, _msg or "E-mail do destinatário inválido.")
    if not (user_id and estudo_id):
        return AuthResult(False, "Estudo inválido para compartilhar.")
    if _email_norm == (remetente_email or "").strip().lower():
        return AuthResult(False, "Você já é o dono deste estudo — informe o e-mail de OUTRO perfil.")
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Compartilhar estudos indisponível no momento.")
    try:
        # confirma a posse do estudo (também dá o nome para a mensagem)
        _dono = (_c.table("estudos_salvos").select("id,nome").eq("id", estudo_id)
                 .eq("user_id", user_id).limit(1).execute())
        _linhas_dono = _dono.data or []
        if not _linhas_dono:
            return AuthResult(False, "Só é possível compartilhar um estudo da sua própria conta.")
        _c.table("estudos_compartilhados").insert({
            "estudo_id": estudo_id, "owner_id": user_id,
            "destinatario_email": _email_norm, "mensagem": (mensagem or "").strip()[:500]}).execute()
        # notificação por e-mail (cortesia; nunca bloqueia — o compartilhamento já foi persistido)
        try:
            from auth import email_service
            email_service.enviar_notificacao_compartilhamento(
                _email_norm, remetente_nome, remetente_email,
                (_linhas_dono[0].get("nome") or "Estudo"), mensagem)
        except Exception:
            logger.warning("[AUTH] Notificação de compartilhamento por e-mail falhou (ignorado).", exc_info=True)
        return AuthResult(True, f"Estudo compartilhado com {_email_norm}.", dados={"email": _email_norm})
    except Exception as _e:
        _txt = str(_e).lower()
        if "duplicate" in _txt or "unique" in _txt:
            return AuthResult(False, f"Este estudo já está compartilhado com {_email_norm}.")
        logger.error("[AUTH] Falha ao compartilhar estudo.", exc_info=True)
        return AuthResult(False, "Não foi possível compartilhar (a tabela 'estudos_compartilhados' já foi criada no Supabase?).")


def listar_compartilhamentos_do_estudo(user_id: str, estudo_id: str,
                                       access_token: str = "", refresh_token: str = "") -> list:
    """Lista com quem um estudo do usuário está compartilhado (para exibir/revogar). [] em falha."""
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None or not (user_id and estudo_id):
        return []
    try:
        _r = (_c.table("estudos_compartilhados").select("id,destinatario_email,created_at")
              .eq("owner_id", user_id).eq("estudo_id", estudo_id)
              .order("created_at", desc=True).limit(100).execute())
        return _r.data or []
    except Exception:
        logger.error("[AUTH] Falha ao listar compartilhamentos do estudo.", exc_info=True)
        return []


def revogar_compartilhamento(user_id: str, share_id: str,
                             access_token: str = "", refresh_token: str = "") -> AuthResult:
    """Revoga (exclui) um compartilhamento que o usuário criou. Só o dono revoga (RLS + filtro)."""
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Revogar compartilhamento indisponível no momento.")
    try:
        _c.table("estudos_compartilhados").delete().eq("id", share_id).eq("owner_id", user_id).execute()
        return AuthResult(True, "Compartilhamento revogado.")
    except Exception:
        logger.error("[AUTH] Falha ao revogar compartilhamento.", exc_info=True)
        return AuthResult(False, "Não foi possível revogar o compartilhamento.")


def listar_estudos_recebidos(email: str, access_token: str = "", refresh_token: str = "") -> list:
    """Lista os estudos compartilhados COM o usuário (pelo e-mail dele). Cada item traz os metadados
    do compartilhamento e do estudo (id, nome, tipo, resumo, quem compartilhou, quando). Os dados
    completos vêm sob demanda via carregar_estudo_por_id. [] em falha/sem e-mail."""
    from auth.validators import validar_email
    _ok, _email_norm, _ = validar_email(email)
    if not _ok:
        return []
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return []
    try:
        _sh = (_c.table("estudos_compartilhados")
               .select("id,estudo_id,owner_id,mensagem,created_at")
               .eq("destinatario_email", _email_norm)
               .order("created_at", desc=True).limit(100).execute())
        _shares = _sh.data or []
        if not _shares:
            return []
        _ids = list({s.get("estudo_id") for s in _shares if s.get("estudo_id")})
        _est_por_id = {}
        try:
            _es = (_c.table("estudos_salvos").select("id,nome,tipo,resumo,created_at")
                   .in_("id", _ids).execute())
            _est_por_id = {e.get("id"): e for e in (_es.data or [])}
        except Exception:
            logger.error("[AUTH] Falha ao buscar estudos recebidos (RLS aplicada?).", exc_info=True)
        _out = []
        for _s in _shares:
            _e = _est_por_id.get(_s.get("estudo_id"))
            if not _e:
                continue   # a linha do estudo não veio (revogado, excluído, ou RLS) → omite
            _out.append({"share_id": _s.get("id"), "estudo_id": _s.get("estudo_id"),
                         "mensagem": _s.get("mensagem") or "", "compartilhado_em": _s.get("created_at"),
                         "nome": _e.get("nome"), "tipo": _e.get("tipo"), "resumo": _e.get("resumo") or {},
                         "estudo_criado_em": _e.get("created_at")})
        return _out
    except Exception:
        logger.error("[AUTH] Falha ao listar estudos recebidos.", exc_info=True)
        return []


def carregar_estudo_por_id(estudo_id: str, access_token: str = "", refresh_token: str = "") -> dict | None:
    """Carrega um estudo APENAS pelo id, deixando a RLS decidir o acesso (dono OU destinatário de um
    compartilhamento). Usado para abrir/baixar um estudo recebido. None se sem acesso/falha."""
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None or not estudo_id:
        return None
    try:
        _r = _c.table("estudos_salvos").select("*").eq("id", estudo_id).limit(1).execute()
        _linhas = _r.data or []
        return _linhas[0] if _linhas else None
    except Exception:
        logger.error("[AUTH] Falha ao carregar estudo por id.", exc_info=True)
        return None


def contar_estudos_recebidos_novos(user_id: str, email: str,
                                   access_token: str = "", refresh_token: str = "") -> int:
    """[COMPARTILHAR - 448ª geração] Conta quantos estudos foram compartilhados com o usuário DEPOIS da
    última vez que ele viu a seção "Estudos recebidos" (marca no próprio perfil). Para o badge do menu.
    0 em falha/sem e-mail. O teto de 99 evita varrer listas enormes só para um contador."""
    from auth.validators import validar_email
    _ok, _email_norm, _ = validar_email(email)
    if not _ok or not user_id:
        return 0
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return 0
    try:
        _visto = None
        try:
            _p = (_c.table("profiles").select("estudos_recebidos_vistos_em")
                  .eq("id", user_id).limit(1).execute())
            _visto = (_p.data or [{}])[0].get("estudos_recebidos_vistos_em") if (_p.data or []) else None
        except Exception:
            _visto = None
        _q = (_c.table("estudos_compartilhados").select("id,created_at")
              .eq("destinatario_email", _email_norm))
        if _visto:
            _q = _q.gt("created_at", _visto)
        _r = _q.limit(99).execute()
        return len(_r.data or [])
    except Exception:
        logger.error("[AUTH] Falha ao contar estudos recebidos novos.", exc_info=True)
        return 0


def marcar_recebidos_como_vistos(user_id: str,
                                 access_token: str = "", refresh_token: str = "") -> bool:
    """[COMPARTILHAR - 448ª geração] Marca no perfil do usuário o instante em que ele viu a seção
    "Estudos recebidos" (zera o badge). Atualiza a PRÓPRIA linha de profiles (RLS permite). Fail-open."""
    if not user_id:
        return False
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return False
    try:
        from datetime import datetime as _dt, timezone as _tz
        _c.table("profiles").update(
            {"estudos_recebidos_vistos_em": _dt.now(_tz.utc).isoformat()}).eq("id", user_id).execute()
        return True
    except Exception:
        logger.error("[AUTH] Falha ao marcar estudos recebidos como vistos.", exc_info=True)
        return False


# ---- Foto de perfil (avatar) -------------------------------------------------
def enviar_avatar(user_id: str, conteudo_bytes: bytes, content_type: str,
                  access_token: str = "", refresh_token: str = "") -> AuthResult:
    """Envia a foto ao bucket 'avatars' (caminho <user_id>/avatar.<ext>) e grava a
    URL pública em profiles.avatar_url. Requer o bucket 'avatars' público criado no
    Supabase (ver schema.sql)."""
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Envio de foto indisponível no momento.")
    _ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
            "image/webp": "webp", "image/gif": "gif"}.get((content_type or "").lower())
    if _ext is None:
        return AuthResult(False, "Formato não suportado. Use PNG, JPG, WEBP ou GIF.")
    _caminho = f"{user_id}/avatar.{_ext}"
    try:
        _c.storage.from_("avatars").upload(
            _caminho, conteudo_bytes,
            {"content-type": content_type, "upsert": "true", "cache-control": "3600"})
    except Exception:
        logger.error("[AUTH] Falha ao enviar avatar ao Storage.", exc_info=True)
        return AuthResult(False, "Não foi possível enviar a foto (o bucket 'avatars' já foi criado no Supabase?).")
    try:
        _url = _c.storage.from_("avatars").get_public_url(_caminho)
        # cache-busting para a imagem nova aparecer na hora
        import time as _t
        _url_cb = f"{_url}?v={int(_t.time())}"
        _c.table("profiles").update({"avatar_url": _url_cb}).eq("id", user_id).execute()
        return AuthResult(True, "Foto de perfil atualizada.", {"avatar_url": _url_cb})
    except Exception:
        logger.error("[AUTH] Falha ao registrar URL do avatar.", exc_info=True)
        return AuthResult(False, "A foto foi enviada, mas não foi possível registrar a URL no perfil.")


def remover_avatar(user_id: str, access_token: str = "", refresh_token: str = "") -> AuthResult:
    _c = _cliente_do_usuario(access_token, refresh_token)
    if _c is None:
        return AuthResult(False, "Operação indisponível no momento.")
    try:
        for _ext in ("png", "jpg", "webp", "gif"):
            try:
                _c.storage.from_("avatars").remove([f"{user_id}/avatar.{_ext}"])
            except Exception:
                pass
        _c.table("profiles").update({"avatar_url": None}).eq("id", user_id).execute()
        return AuthResult(True, "Foto de perfil removida.")
    except Exception:
        logger.error("[AUTH] Falha ao remover avatar.", exc_info=True)
        return AuthResult(False, "Não foi possível remover a foto.")
