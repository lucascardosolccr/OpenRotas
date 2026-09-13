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
