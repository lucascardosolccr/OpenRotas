# -*- coding: utf-8 -*-
"""Gerenciamento de sessão e PORTÃO de autenticação da aplicação.

`exigir_autenticacao()` é a função central: chamada uma única vez, bem no início de
`streamlit_app.py` (depois do `st.set_page_config`/CSS, antes de qualquer conteúdo real),
ela renderiza a tela de login/cadastro/recuperação e chama `st.stop()` enquanto não houver
uma sessão válida — nenhum código abaixo dela roda para um visitante não autenticado. Isso
é proteção REAL (nada executa), não ocultação visual de menu.

PERSISTÊNCIA ENQUANTO O NAVEGADOR ESTÁ ABERTO: a sessão vive em `st.session_state` (por
aba/conexão) e é renovada silenciosamente pelo `refresh_token` — o access_token é um JWT de
vida curta (~1h) e expirar é normal. A revalidação periódica (`_sessao_expirada_no_servidor`)
NUNCA derruba o usuário por um soluço de rede: só encerra a sessão quando a renovação é
REJEITADA DE FORMA DEFINITIVA (refresh token revogado/expirado/já usado). Uma falha TRANSIENTE
(rede caiu, servidor 5xx, timeout, SSL) mantém a sessão e agenda nova tentativa em ~45 s. Assim
o login permanece ativo enquanto o navegador continuar aberto, encerrando apenas no logout
intencional ou numa revogação real do lado do servidor.

LIMITAÇÃO CONHECIDA (documentada, não escondida): fechar e reabrir o navegador — ou um F5 que o
Streamlit trate como conexão nova — perde o `session_state` e exige novo login. Persistência
entre sessões de navegador (tipo "lembrar-me") exigiria guardar os tokens no navegador via um
componente de cookies/armazenamento dedicado (ex.: streamlit-cookies-manager) — nova dependência
com implicações de segurança (token acessível a XSS), candidata a rodada própria com o schema/UX
combinados."""
import logging
import time

import streamlit as st

from auth import auth_service, browser_session, email_service, validators
from auth.supabase_client import credenciais_configuradas, obter_cliente

logger = logging.getLogger(__name__)

_SESSION_KEYS = ("auth_user_id", "auth_email", "auth_access_token", "auth_refresh_token",
                 "auth_login_ts")


def esta_autenticado() -> bool:
    return bool(st.session_state.get("auth_user_id") and st.session_state.get("auth_access_token"))


def usuario_atual() -> dict | None:
    if not esta_autenticado():
        return None
    return {
        "user_id": st.session_state.get("auth_user_id"),
        "email": st.session_state.get("auth_email"),
    }


def _tokens_sessao() -> tuple[str, str]:
    """(access_token, refresh_token) da sessão atual — necessários para as operações que
    passam por RLS (perfil, estudos, anotações, avatar). ('','') se não autenticado."""
    return (st.session_state.get("auth_access_token", "") or "",
            st.session_state.get("auth_refresh_token", "") or "")


def badge_estudos_recebidos() -> int:
    """[COMPARTILHAR - 448ª geração] Nº de estudos recebidos AINDA NÃO VISTOS (para o badge do menu).
    Cacheado por sessão com validade curta (evita bater na rede a cada rerun da sidebar). 0 se não logado."""
    _u = usuario_atual()
    if not _u:
        return 0
    try:
        _agora = time.time()
        _ult = st.session_state.get("_badge_recebidos_ts", 0.0)
        if "_badge_recebidos" not in st.session_state or (_agora - _ult) > 60:
            _at, _rt = _tokens_sessao()
            st.session_state["_badge_recebidos"] = auth_service.contar_estudos_recebidos_novos(
                _u.get("user_id", ""), _u.get("email", ""), _at, _rt)
            st.session_state["_badge_recebidos_ts"] = _agora
        return int(st.session_state.get("_badge_recebidos", 0) or 0)
    except Exception:
        return 0


def _iniciar_sessao(user_id: str, email: str, access_token: str, refresh_token: str):
    st.session_state["auth_user_id"] = user_id
    st.session_state["auth_email"] = email
    st.session_state["auth_access_token"] = access_token
    st.session_state["auth_refresh_token"] = refresh_token
    st.session_state["auth_login_ts"] = time.time()
    # [COMPARTILHAR - 448ª] invalida o cache do badge de recebidos: a contagem deve refletir a conta
    # que ACABOU de entrar (evita herdar a contagem/estado de uma sessão anterior neste navegador).
    st.session_state.pop("_badge_recebidos", None)
    st.session_state.pop("_badge_recebidos_ts", None)


def encerrar_sessao():
    auth_service.fazer_logout()
    # [PERSISTÊNCIA NO NAVEGADOR] apaga também a sessão guardada na sessionStorage — sair é sair
    # em qualquer aba/rerun; não deixamos token órfão no navegador. Fail-open (no-op se indisponível).
    browser_session.limpar()
    for _k in _SESSION_KEYS:
        st.session_state.pop(_k, None)
    st.session_state.pop("_ultimo_token_persistido", None)
    # [COMPARTILHAR - 448ª] zera o cache do badge de recebidos ao sair (não vazar contagem entre contas).
    st.session_state.pop("_badge_recebidos", None)
    st.session_state.pop("_badge_recebidos_ts", None)
    # [§24 - SESSÃO EXPIRADA] limpa também qualquer estado de aplicação sensível ao usuário
    # anterior, mas preserva chaves que não começam com "auth_"/dados de formulário em
    # edição não é objetivo aqui — o logout intencional pode perder rascunhos, é esperado.


def _sessao_expirada_no_servidor() -> bool:
    """[§24, revisado para PERSISTÊNCIA DE SESSÃO] Verifica, sem derrubar a app em caso de
    falha de rede, se o token ainda é válido no Supabase. Fail-open (assume válida) quando
    o cliente está indisponível — a validação real de autorização continua sendo feita pelo
    próprio Supabase a cada chamada (nunca confiamos só nesta checagem local, ver §34 da
    missão).

    O access_token é um JWT de vida curta (~1h por padrão do Supabase) — expirar é normal e
    NÃO deve derrubar quem está com o navegador aberto. Antes de considerar a sessão
    realmente expirada, tenta renová-la silenciosamente com o refresh_token (vida bem mais
    longa); só quando o próprio refresh_token não é mais aceito (revogado, ou expirado de
    verdade) é que a sessão termina — assim o login permanece ativo enquanto o navegador
    continuar aberto, encerrando apenas quando o usuário sai ou fecha o navegador."""
    _cliente = obter_cliente()
    if _cliente is None:
        return False
    try:
        _resp = _cliente.auth.get_user(st.session_state.get("auth_access_token"))
        if _resp is not None and _resp.user is not None:
            st.session_state["_auth_recheck_curto"] = False  # tudo certo -> volta ao ritmo normal
            return False
    except Exception:
        pass  # access_token expirado/inválido -> tenta renovar com o refresh_token abaixo

    _renov = auth_service.renovar_sessao(st.session_state.get("auth_refresh_token"))
    if _renov.ok:
        st.session_state["auth_access_token"] = _renov.dados["access_token"]
        st.session_state["auth_refresh_token"] = _renov.dados["refresh_token"]
        st.session_state["_auth_recheck_curto"] = False
        return False
    # A renovação falhou. Só encerramos a sessão DE VERDADE quando a rejeição é DEFINITIVA
    # (refresh token revogado/expirado/já usado). Uma falha TRANSIENTE (rede caiu, servidor 5xx,
    # timeout, SSL) NÃO derruba o usuário: o navegador segue aberto e a sessão continua — e marcamos
    # para revalidar EM BREVE (não daqui a 5 min), recuperando assim que a rede voltar. Fail-open:
    # na dúvida, mantém logado. (default: transiente)
    if _renov.dados.get("transiente", True):
        st.session_state["_auth_recheck_curto"] = True
        return False
    return True


# ==============================================================================
# Telas
# ==============================================================================

def _tela_login():
    st.markdown("### Entrar")
    # [Login UX] Após criar a conta, o e-mail recém-cadastrado é pré-preenchido e uma
    # confirmação única é exibida — o usuário não redigita o que acabou de informar.
    _email_pos = st.session_state.pop("_auth_email_pos_cadastro", None)
    if _email_pos:
        st.session_state.setdefault("login_email", _email_pos)
        st.success("✅ Conta criada! Entre abaixo com seu e-mail e senha.")
    with st.form("form_login", clear_on_submit=False):
        _email = st.text_input("E-mail", key="login_email", placeholder="voce@exemplo.com")
        _senha = st.text_input("Senha", type="password", key="login_senha")
        _enviar = st.form_submit_button("Entrar", use_container_width=True, type="primary")
    if _enviar:
        _ok_email, _email_norm, _erro_email = validators.validar_email(_email)
        if not _ok_email or not _senha:
            st.error("Informe um e-mail válido e a senha.")
        else:
            with st.spinner("Entrando..."):
                _res = auth_service.fazer_login(_email_norm, _senha)
            if _res.ok:
                _iniciar_sessao(_res.dados["user_id"], _res.dados["email"],
                               _res.dados["access_token"], _res.dados["refresh_token"])
                st.rerun()
            else:
                st.error(_res.mensagem)

    # [LOGIN SOCIAL] Entrar com Google / Microsoft (OAuth do Supabase). Fluxo em 2 passos por
    # robustez no Streamlit: o botão gera a URL do provedor; um link "Continuar" leva o usuário
    # até lá. No retorno (?code=...), _renderizar_tela_autenticacao troca o code por sessão.
    st.markdown("<div style='text-align:center;color:var(--tx-3,#9CA3AF);margin:10px 0 6px'>ou entre com</div>",
                unsafe_allow_html=True)
    _redir = ""
    try:
        _redir = str(st.secrets.get("APP_URL", "") or "").strip()
    except Exception:
        _redir = ""
    _sc1, _sc2 = st.columns(2)
    _prov_click = None
    if _sc1.button("🔵 Google", use_container_width=True, key="oauth_google"):
        _prov_click = ("google", "Google")
    if _sc2.button("🟦 Microsoft", use_container_width=True, key="oauth_microsoft"):
        _prov_click = ("microsoft", "Microsoft")
    if _prov_click:
        _res = auth_service.iniciar_login_social(_prov_click[0], _redir or "")
        if _res.ok:
            st.session_state["_oauth_url"] = _res.dados["url"]
            st.session_state["_oauth_prov_nome"] = _prov_click[1]
            st.rerun()
        else:
            st.error(_res.mensagem)
    if st.session_state.get("_oauth_url"):
        st.link_button(f"Continuar para o {st.session_state.get('_oauth_prov_nome','provedor')} →",
                       st.session_state["_oauth_url"], use_container_width=True, type="primary")
        st.caption("Você será levado à tela de login do provedor e voltará já conectado.")

    _c1, _c2 = st.columns(2)
    with _c1:
        if st.button("Esqueci minha senha", use_container_width=True):
            st.session_state["_auth_tela"] = "recuperar"
            st.rerun()
    with _c2:
        if st.button("Criar uma conta", use_container_width=True):
            st.session_state["_auth_tela"] = "cadastro"
            st.rerun()


def _tela_cadastro():
    st.markdown("### Criar conta")
    with st.form("form_cadastro"):
        _nome = st.text_input("Nome completo*")
        _email = st.text_input("E-mail*")
        _telefone = st.text_input("Telefone (com DDD)*", placeholder="(11) 98765-4321")
        st.caption("Endereço")
        _cc1, _cc2 = st.columns([3, 1])
        _logradouro = _cc1.text_input("Logradouro*")
        _numero = _cc2.text_input("Número*")
        _cc3, _cc4 = st.columns(2)
        _complemento = _cc3.text_input("Complemento")
        _bairro = _cc4.text_input("Bairro*")
        _cc5, _cc6, _cc7 = st.columns([2, 2, 1])
        _cidade = _cc5.text_input("Cidade*")
        _cep = _cc6.text_input("CEP*", placeholder="00000-000")
        _uf = _cc7.text_input("UF*", max_chars=2, placeholder="GO")
        st.caption("Senha")
        _senha = st.text_input("Senha*", type="password",
                               help="Mínimo 8 caracteres, combinando ao menos 3 de: maiúscula, minúscula, número, símbolo.")
        _senha2 = st.text_input("Confirmar senha*", type="password")
        _enviar = st.form_submit_button("Cadastrar", use_container_width=True, type="primary")

    if _enviar:
        _erros = []
        _ok_nome, _nome_norm, _erro_nome = validators.validar_nome(_nome)
        if not _ok_nome:
            _erros.append(_erro_nome)
        _ok_email, _email_norm, _erro_email = validators.validar_email(_email)
        if not _ok_email:
            _erros.append(_erro_email)
        _ok_tel, _tel_norm, _erro_tel = validators.validar_telefone(_telefone)
        if not _ok_tel:
            _erros.append(_erro_tel)
        _ok_end, _end_norm, _erros_end = validators.validar_endereco(
            _logradouro, _numero, _bairro, _cidade, _uf, _cep, _complemento)
        _erros.extend(_erros_end)
        if not validators.senhas_conferem(_senha, _senha2):
            _erros.append("As senhas não conferem.")
        _ok_senha, _erro_senha, _ = validators.validar_forca_senha(_senha, _email_norm, _nome_norm)
        if not _ok_senha:
            _erros.append(_erro_senha)

        if _erros:
            for _e in _erros:
                st.error(_e)
        else:
            with st.spinner("Criando sua conta..."):
                _res = auth_service.cadastrar(_email_norm, _senha, _nome_norm, _tel_norm)
            if _res.ok:
                # [ENDEREÇO] gravado no perfil logo após o cadastro (o trigger do banco já
                # criou a linha com nome/telefone/e-mail; aqui só completamos o endereço).
                try:
                    auth_service.atualizar_perfil(
                        _res.dados["user_id"], _end_norm,
                        _res.dados.get("access_token", ""), _res.dados.get("refresh_token", ""))
                except Exception:
                    logger.debug("[AUTH] Falha ao gravar endereço logo após o cadastro (não bloqueia o fluxo).",
                                exc_info=True)
                try:
                    email_service.enviar_boas_vindas(_email_norm, _nome_norm)
                except Exception:
                    logger.debug("[AUTH] Falha ao enviar e-mail de boas-vindas (não bloqueia o fluxo).",
                                exc_info=True)
                st.success("✅ " + _res.mensagem + " Você já pode entrar com seu e-mail e senha.")
                st.session_state["_auth_tela"] = "login"
                st.session_state["_auth_email_pos_cadastro"] = _email_norm
                time.sleep(1.2)
                st.rerun()
            else:
                st.error(_res.mensagem)

    if st.button("← Já tenho conta, entrar"):
        st.session_state["_auth_tela"] = "login"
        st.rerun()


def _tela_recuperar():
    st.markdown("### Esqueci minha senha")
    _etapa = st.session_state.get("_auth_recuperacao_etapa", "email")

    if _etapa == "email":
        st.caption("Informe seu e-mail — vamos enviar um código de 6 dígitos para redefinir sua senha.")
        with st.form("form_recuperar_email"):
            _email = st.text_input("E-mail")
            _enviar = st.form_submit_button("Enviar código", type="primary", use_container_width=True)
        if _enviar:
            _ok_email, _email_norm, _erro = validators.validar_email(_email)
            if not _ok_email:
                st.error(_erro)
            else:
                with st.spinner("Enviando código..."):
                    _res = auth_service.solicitar_recuperacao_senha(_email_norm)
                st.session_state["_auth_recuperacao_email"] = _email_norm
                st.session_state["_auth_recuperacao_etapa"] = "codigo"
                st.info(_res.mensagem)
                st.rerun()

    elif _etapa == "codigo":
        _email_rec = st.session_state.get("_auth_recuperacao_email", "")
        st.caption(f"Digite o código de 6 dígitos enviado para **{_email_rec}**.")
        with st.form("form_recuperar_codigo"):
            _codigo = st.text_input("Código de 6 dígitos", max_chars=6)
            _confirmar = st.form_submit_button("Confirmar código", type="primary", use_container_width=True)
        if _confirmar:
            _ok_fmt, _codigo_norm, _erro_fmt = validators.validar_formato_otp(_codigo)
            if not _ok_fmt:
                st.error(_erro_fmt)
            else:
                with st.spinner("Verificando..."):
                    _res = auth_service.verificar_codigo_recuperacao(_email_rec, _codigo_norm)
                if _res.ok:
                    st.session_state["_auth_recuperacao_tokens"] = _res.dados
                    st.session_state["_auth_recuperacao_etapa"] = "nova_senha"
                    st.rerun()
                else:
                    st.error(_res.mensagem)
        if st.button("← Não recebi / usar outro e-mail"):
            st.session_state["_auth_recuperacao_etapa"] = "email"
            st.rerun()

    elif _etapa == "nova_senha":
        st.caption("Código confirmado — defina sua nova senha.")
        with st.form("form_nova_senha"):
            _nova = st.text_input("Nova senha", type="password")
            _nova2 = st.text_input("Confirmar nova senha", type="password")
            _redefinir = st.form_submit_button("Redefinir senha", type="primary", use_container_width=True)
        if _redefinir:
            _erros = []
            if not validators.senhas_conferem(_nova, _nova2):
                _erros.append("As senhas não conferem.")
            _ok_senha, _erro_senha, _ = validators.validar_forca_senha(
                _nova, st.session_state.get("_auth_recuperacao_email", ""))
            if not _ok_senha:
                _erros.append(_erro_senha)
            if _erros:
                for _e in _erros:
                    st.error(_e)
            else:
                _tokens = st.session_state.get("_auth_recuperacao_tokens", {})
                with st.spinner("Redefinindo..."):
                    _res = auth_service.redefinir_senha(
                        _nova, _tokens.get("access_token", ""), _tokens.get("refresh_token", ""))
                if _res.ok:
                    st.success("✅ " + _res.mensagem)
                    for _k in ("_auth_recuperacao_etapa", "_auth_recuperacao_email", "_auth_recuperacao_tokens"):
                        st.session_state.pop(_k, None)
                    st.session_state["_auth_tela"] = "login"
                    time.sleep(1.2)
                    st.rerun()
                else:
                    st.error(_res.mensagem)

    if st.button("← Voltar para o login"):
        for _k in ("_auth_recuperacao_etapa", "_auth_recuperacao_email", "_auth_recuperacao_tokens"):
            st.session_state.pop(_k, None)
        st.session_state["_auth_tela"] = "login"
        st.rerun()


def _tela_perfil():
    """[§9/§10 da missão] Perfil do usuário logado: ver/editar nome/telefone/endereço e
    solicitar troca de e-mail. A troca de e-mail NUNCA é imediata — `atualizar_perfil` recusa
    a chave 'email' (ver auth_service), e a troca real passa por `solicitar_alteracao_email`,
    que só é efetivada quando o usuário confirma o novo endereço pelo link que o Supabase
    envia (nenhum código deste módulo decide quando a troca vale — delegado ao Supabase Auth,
    mesma disciplina de nunca reimplementar o que o backend de auth já resolve com segurança)."""
    st.markdown("### 👤 Meu perfil")
    _user = usuario_atual()
    if not _user:
        st.session_state["_mostrar_perfil"] = False
        st.rerun()
        return

    _at, _rt = _tokens_sessao()
    with st.spinner("Carregando perfil..."):
        _perfil = auth_service.obter_perfil(_user["user_id"], _at, _rt)

    if _perfil is None:
        st.error("Não foi possível carregar seu perfil no momento — tente novamente em instantes.")
    else:
        # [Perfil UX] Cartão-resumo da conta: identidade num relance (iniciais, nome, e-mail,
        # membro desde, última atualização) — dados REAIS do perfil, formatação defensiva e
        # tudo escapado (o conteúdo é do próprio usuário, mas escapamos por higiene de HTML).
        import html as _html
        from datetime import datetime as _dt
        _nome_disp = (_perfil.get("nome_completo") or "").strip() or "—"
        _iniciais = ("".join(p[0] for p in _nome_disp.split()[:2]).upper()
                     if _nome_disp != "—" else "👤") or "👤"

        def _fmt_data(_v):
            try:
                return _dt.fromisoformat(str(_v).replace("Z", "+00:00")).strftime("%d/%m/%Y")
            except Exception:
                return None
        _desde = _fmt_data(_perfil.get("created_at"))
        _atual = _fmt_data(_perfil.get("updated_at"))
        _meta_bits = ([f"Membro desde {_desde}"] if _desde else []) + ([f"Atualizado em {_atual}"] if _atual else [])
        _meta_html = _html.escape(" · ".join(_meta_bits))
        # [Perfil] Avatar: usa a FOTO enviada (avatar_url) quando existir; senão, as iniciais.
        _avatar_url = (_perfil.get("avatar_url") or "").strip()
        if _avatar_url:
            _av_html = ("<img src='" + _html.escape(_avatar_url) + "' alt='avatar' "
                        "style='flex:0 0 auto;width:56px;height:56px;border-radius:50%;object-fit:cover;"
                        "border:2px solid var(--brand,#3B82F6)'/>")
        else:
            _av_html = ("<div style='flex:0 0 auto;width:56px;height:56px;border-radius:50%;background:var(--brand,#3B82F6);"
                        "color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.25rem;font-weight:700'>"
                        + _html.escape(_iniciais) + "</div>")
        st.markdown(
            "<div style='display:flex;align-items:center;gap:16px;background:var(--sf-2,#1E232F);"
            "border:1px solid var(--sf-3,#2D3342);border-radius:14px;padding:16px 18px;margin-bottom:10px'>"
            + _av_html +
            "<div style='min-width:0'>"
            "<div style='color:var(--tx-1,#F9FAFB);font-weight:700;font-size:1.05rem'>" + _html.escape(_nome_disp) + "</div>"
            "<div style='color:var(--tx-3,#9CA3AF);font-size:.85rem'>✉️ " + _html.escape(_user['email'] or '—') + "</div>"
            + ("<div style='color:var(--tx-4,#6B7280);font-size:.78rem;margin-top:2px'>" + _meta_html + "</div>" if _meta_html else "")
            + "</div></div>", unsafe_allow_html=True)

        # [Perfil] Foto de perfil — enviar/atualizar/remover (Supabase Storage, bucket 'avatars').
        with st.expander("🖼️ Foto de perfil", expanded=False):
            _at = st.session_state.get("auth_access_token", "")
            _rt = st.session_state.get("auth_refresh_token", "")
            _foto = st.file_uploader("Escolha uma imagem (PNG, JPG, WEBP ou GIF, até ~3 MB)",
                                     type=["png", "jpg", "jpeg", "webp", "gif"], key="perfil_avatar_up")
            _fc1, _fc2 = st.columns(2)
            if _fc1.button("Enviar foto", use_container_width=True, disabled=_foto is None):
                if _foto is not None:
                    _bytes = _foto.getvalue()
                    if len(_bytes) > 3 * 1024 * 1024:
                        st.error("Imagem muito grande (máx. ~3 MB). Reduza e tente novamente.")
                    else:
                        with st.spinner("Enviando foto..."):
                            _res = auth_service.enviar_avatar(_user["user_id"], _bytes,
                                                              _foto.type or "image/png", _at, _rt)
                        if _res.ok:
                            st.success("✅ " + _res.mensagem)
                            time.sleep(0.8)
                            st.rerun()
                        else:
                            st.error(_res.mensagem)
            if _avatar_url and _fc2.button("Remover foto", use_container_width=True):
                with st.spinner("Removendo..."):
                    _res = auth_service.remover_avatar(_user["user_id"], _at, _rt)
                (st.success if _res.ok else st.error)(("✅ " if _res.ok else "") + _res.mensagem)
                if _res.ok:
                    time.sleep(0.8)
                    st.rerun()
        with st.form("form_editar_perfil"):
            _nome = st.text_input("Nome completo*", value=_perfil.get("nome_completo") or "")
            _telefone = st.text_input("Telefone (com DDD)*", value=_perfil.get("telefone") or "",
                                      placeholder="(11) 98765-4321")
            st.caption("Endereço")
            _cc1, _cc2 = st.columns([3, 1])
            _logradouro = _cc1.text_input("Logradouro*", value=_perfil.get("logradouro") or "")
            _numero = _cc2.text_input("Número*", value=_perfil.get("numero") or "")
            _cc3, _cc4 = st.columns(2)
            _complemento = _cc3.text_input("Complemento", value=_perfil.get("complemento") or "")
            _bairro = _cc4.text_input("Bairro*", value=_perfil.get("bairro") or "")
            _cc5, _cc6, _cc7 = st.columns([2, 2, 1])
            _cidade = _cc5.text_input("Cidade*", value=_perfil.get("cidade") or "")
            _cep = _cc6.text_input("CEP*", value=_perfil.get("cep") or "", placeholder="00000-000")
            _uf = _cc7.text_input("UF*", value=_perfil.get("uf") or "", max_chars=2)
            _salvar = st.form_submit_button("Salvar alterações", type="primary", use_container_width=True)
        if _salvar:
            _erros = []
            _ok_nome, _nome_norm, _erro_nome = validators.validar_nome(_nome)
            if not _ok_nome:
                _erros.append(_erro_nome)
            _ok_tel, _tel_norm, _erro_tel = validators.validar_telefone(_telefone)
            if not _ok_tel:
                _erros.append(_erro_tel)
            _ok_end, _end_norm, _erros_end = validators.validar_endereco(
                _logradouro, _numero, _bairro, _cidade, _uf, _cep, _complemento)
            _erros.extend(_erros_end)
            if _erros:
                for _e in _erros:
                    st.error(_e)
            else:
                _campos = dict(_end_norm)
                _campos["nome_completo"] = _nome_norm
                _campos["telefone"] = _tel_norm
                _at, _rt = _tokens_sessao()
                with st.spinner("Salvando..."):
                    _res = auth_service.atualizar_perfil(_user["user_id"], _campos, _at, _rt)
                if _res.ok:
                    st.success("✅ " + _res.mensagem)
                    time.sleep(1.0)
                    st.rerun()
                else:
                    st.error(_res.mensagem)

    st.markdown("---")
    st.markdown("#### 🔒 Alterar senha")
    st.caption("Por segurança, confirme a senha atual antes de definir uma nova.")
    with st.form("form_trocar_senha", clear_on_submit=True):
        _senha_atual = st.text_input("Senha atual", type="password")
        _nova_senha = st.text_input("Nova senha", type="password",
                                    help="Mínimo 8 caracteres, combinando ao menos 3 de: maiúscula, minúscula, número, símbolo.")
        _nova_senha2 = st.text_input("Confirmar nova senha", type="password")
        _trocar_senha = st.form_submit_button("Alterar senha")
    if _trocar_senha:
        _erros_s = []
        if not _senha_atual:
            _erros_s.append("Informe a senha atual.")
        if not validators.senhas_conferem(_nova_senha, _nova_senha2):
            _erros_s.append("A nova senha e a confirmação não conferem.")
        _ok_forca, _erro_forca, _ = validators.validar_forca_senha(
            _nova_senha, (_user or {}).get("email", ""))
        if not _ok_forca:
            _erros_s.append(_erro_forca)
        if _senha_atual and _nova_senha and _senha_atual == _nova_senha:
            _erros_s.append("A nova senha deve ser diferente da atual.")
        if _erros_s:
            for _e in _erros_s:
                st.error(_e)
        else:
            with st.spinner("Alterando senha..."):
                _res = auth_service.alterar_senha_logado(_user["email"], _senha_atual, _nova_senha)
            if _res.ok:
                st.success("✅ " + _res.mensagem)
            else:
                st.error(_res.mensagem)

    st.markdown("---")
    st.markdown("#### ✉️ Alterar e-mail")
    st.caption("Você continua conectado com o e-mail atual até confirmar o novo endereço — "
               "a alteração NUNCA entra em vigor antes dessa confirmação.")
    with st.form("form_trocar_email"):
        _novo_email = st.text_input("Novo e-mail")
        _pedir = st.form_submit_button("Solicitar alteração de e-mail")
    if _pedir:
        _ok_email, _email_norm, _erro_email = validators.validar_email(_novo_email)
        if not _ok_email:
            st.error(_erro_email)
        elif _email_norm == (_user.get("email") or "").strip().lower():
            st.warning("Esse já é o seu e-mail atual.")
        else:
            with st.spinner("Enviando confirmação..."):
                _res = auth_service.solicitar_alteracao_email(_email_norm)
            if _res.ok:
                st.info(_res.mensagem)
            else:
                st.error(_res.mensagem)

    st.markdown("---")
    # [Perfil] MINHAS ANOTAÇÕES — CRUD salvo na conta (tabela public.anotacoes, RLS por usuário).
    st.markdown("#### 📝 Minhas anotações")
    _at = st.session_state.get("auth_access_token", "")
    _rt = st.session_state.get("auth_refresh_token", "")
    with st.form("form_nova_anotacao", clear_on_submit=True):
        _an_titulo = st.text_input("Título", placeholder="Ex.: Observações do estudo de setembro")
        _an_conteudo = st.text_area("Anotação", height=90, placeholder="Escreva sua anotação...")
        _an_salvar = st.form_submit_button("Salvar anotação", type="primary")
    if _an_salvar:
        with st.spinner("Salvando..."):
            _res = auth_service.criar_anotacao(_user["user_id"], _an_titulo, _an_conteudo, _at, _rt)
        if _res.ok:
            st.success("✅ " + _res.mensagem)
            time.sleep(0.6)
            st.rerun()
        else:
            st.error(_res.mensagem)
    try:
        _anotacoes = auth_service.listar_anotacoes(_user["user_id"], _at, _rt)
    except Exception:
        _anotacoes = []
    if _anotacoes:
        st.caption(f"{len(_anotacoes)} anotação(ões) salva(s).")
        for _an in _anotacoes:
            _an_id = _an.get("id")
            _tit = (_an.get("titulo") or "").strip() or "(sem título)"
            with st.expander(f"📝 {_tit}", expanded=False):
                _e_tit = st.text_input("Título", value=_an.get("titulo") or "", key=f"an_tit_{_an_id}")
                _e_con = st.text_area("Anotação", value=_an.get("conteudo") or "", height=90, key=f"an_con_{_an_id}")
                _ac1, _ac2 = st.columns(2)
                if _ac1.button("💾 Atualizar", key=f"an_upd_{_an_id}", use_container_width=True):
                    _r = auth_service.atualizar_anotacao(_user["user_id"], _an_id, _e_tit, _e_con, _at, _rt)
                    (st.success if _r.ok else st.error)(("✅ " if _r.ok else "") + _r.mensagem)
                    if _r.ok:
                        time.sleep(0.6); st.rerun()
                if _ac2.button("🗑️ Excluir", key=f"an_del_{_an_id}", use_container_width=True):
                    _r = auth_service.excluir_anotacao(_user["user_id"], _an_id, _at, _rt)
                    (st.success if _r.ok else st.error)(("✅ " if _r.ok else "") + _r.mensagem)
                    if _r.ok:
                        time.sleep(0.6); st.rerun()
    else:
        st.caption("Você ainda não tem anotações salvas.")

    st.markdown("---")
    # [Perfil] ESTUDOS SALVOS — salva na conta o estudo/processamento que está em memória
    # (o último lote rodado) e permite restaurá-lo depois. Tabela public.estudos_salvos (RLS).
    st.markdown("#### 💾 Estudos salvos")
    st.caption("Seus estudos ficam guardados **na sua conta** (não no navegador) — você os "
               "encontra aqui sempre que entrar, mesmo depois de sair, fechar o navegador ou "
               "usar outro dispositivo.")
    import pandas as _pd
    import json as _json
    _df_mem = st.session_state.get("df_processado")
    _tem_estudo = _df_mem is not None and hasattr(_df_mem, "empty") and not _df_mem.empty
    if _tem_estudo:
        st.caption(f"Há um estudo/processamento em memória agora: **{len(_df_mem):,}** linha(s)."
                   .replace(",", "."))
        with st.form("form_salvar_estudo", clear_on_submit=True):
            _est_nome = st.text_input("Nome para este estudo",
                                      placeholder="Ex.: ENEM 2026 — lote nacional")
            _salvar_est = st.form_submit_button("💾 Salvar o estudo atual na minha conta", type="primary")
        if _salvar_est:
            _MAX = 8000  # limite de segurança do tamanho do JSON por registro
            _trunc = len(_df_mem) > _MAX
            try:
                _df_ser = _df_mem.head(_MAX)
                _dados = _json.loads(_df_ser.to_json(orient="records", date_format="iso"))
            except Exception:
                logger.error("[PERFIL] Falha ao serializar estudo para salvar.", exc_info=True)
                _dados = None
            if _dados is None:
                st.error("Não foi possível preparar este estudo para salvar.")
            else:
                _resumo = {"linhas_total": int(len(_df_mem)), "linhas_salvas": int(min(len(_df_mem), _MAX)),
                           "colunas": [str(c) for c in list(_df_mem.columns)[:80]], "truncado": bool(_trunc)}
                with st.spinner("Salvando estudo na sua conta..."):
                    _r = auth_service.salvar_estudo(_user["user_id"], _est_nome or "Estudo sem nome",
                                                    "lote", _resumo, _dados, _at, _rt)
                if _r.ok:
                    _msg = _r.mensagem + (f" (salvamos as primeiras {_MAX:,} de {len(_df_mem):,} linhas)".replace(",", ".") if _trunc else "")
                    st.success("✅ " + _msg)
                    time.sleep(0.8); st.rerun()
                else:
                    st.error(_r.mensagem)
    else:
        st.caption("Nenhum estudo em memória agora. Rode um **⚙️ Estudo em Lote** e volte aqui "
                   "para salvá-lo — ou restaure um estudo salvo abaixo.")
    try:
        _estudos = auth_service.listar_estudos(_user["user_id"], _at, _rt)
    except Exception:
        _estudos = []
    if _estudos:
        st.caption(f"{len(_estudos)} estudo(s) salvo(s).")
        for _es in _estudos:
            _es_id = _es.get("id")
            _es_res = _es.get("resumo") or {}
            _es_nome = (_es.get("nome") or "Estudo").strip()
            _es_quando = _fmt_data(_es.get("created_at")) or ""
            _es_linhas = _es_res.get("linhas_total", _es_res.get("linhas_salvas", "?"))
            with st.expander(f"💾 {_es_nome} — {_es_linhas} linha(s) · {_es_quando}", expanded=False):
                _rc1, _rc2 = st.columns(2)
                if _rc1.button("♻️ Restaurar", key=f"es_load_{_es_id}", use_container_width=True):
                    with st.spinner("Restaurando estudo..."):
                        _full = auth_service.carregar_estudo(_user["user_id"], _es_id, _at, _rt)
                    _es_dados = (_full or {}).get("dados")
                    if _es_dados:
                        try:
                            st.session_state["df_processado"] = _pd.DataFrame(_es_dados)
                            st.session_state["_mostrar_perfil"] = False
                            st.success("✅ Estudo restaurado — abrindo na aplicação...")
                            time.sleep(0.9); st.rerun()
                        except Exception:
                            logger.error("[PERFIL] Falha ao reconstruir estudo restaurado.", exc_info=True)
                            st.error("Não foi possível reconstruir este estudo.")
                    else:
                        st.error("Este estudo não tem dados salvos para restaurar.")
                if _rc2.button("🗑️ Excluir", key=f"es_del_{_es_id}", use_container_width=True):
                    _r = auth_service.excluir_estudo(_user["user_id"], _es_id, _at, _rt)
                    (st.success if _r.ok else st.error)(("✅ " if _r.ok else "") + _r.mensagem)
                    if _r.ok:
                        time.sleep(0.6); st.rerun()
                # [COMPARTILHAR - 448ª] Compartilhar este estudo com outro perfil (por e-mail).
                st.markdown("**🔗 Compartilhar com outro perfil**")
                with st.form(f"form_compartilhar_{_es_id}", clear_on_submit=True):
                    _dest = st.text_input("E-mail de quem vai receber", key=f"es_share_mail_{_es_id}",
                                          placeholder="colega@exemplo.com")
                    _msg_sh = st.text_input("Mensagem (opcional)", key=f"es_share_msg_{_es_id}",
                                            placeholder="Ex.: segue o estudo do ENEM para conferência")
                    if st.form_submit_button("🔗 Compartilhar", use_container_width=True):
                        _rem_nome = (_perfil.get("nome_completo") if isinstance(_perfil, dict) else "") or ""
                        _r = auth_service.compartilhar_estudo(
                            _user["user_id"], _es_id, _dest, _msg_sh, _at, _rt,
                            remetente_nome=_rem_nome, remetente_email=_user.get("email", ""))
                        (st.success if _r.ok else st.error)(("✅ " if _r.ok else "") + _r.mensagem)
                        if _r.ok:
                            time.sleep(0.8); st.rerun()
                try:
                    _shs = auth_service.listar_compartilhamentos_do_estudo(_user["user_id"], _es_id, _at, _rt)
                except Exception:
                    _shs = []
                if _shs:
                    st.caption("Compartilhado com:")
                    for _sh in _shs:
                        _cs1, _cs2 = st.columns([78, 22])
                        _cs1.caption(f"✉️ {_sh.get('destinatario_email', '—')} · {_fmt_data(_sh.get('created_at')) or ''}")
                        if _cs2.button("Revogar", key=f"es_revk_{_sh.get('id')}", use_container_width=True):
                            _rr = auth_service.revogar_compartilhamento(_user["user_id"], _sh.get("id"), _at, _rt)
                            (st.success if _rr.ok else st.error)(("✅ " if _rr.ok else "") + _rr.mensagem)
                            if _rr.ok:
                                time.sleep(0.5); st.rerun()
    else:
        st.caption("Você ainda não salvou nenhum estudo.")

    # [COMPARTILHAR - 448ª] ESTUDOS RECEBIDOS — estudos que outros perfis compartilharam comigo.
    st.markdown("#### 📥 Estudos recebidos")
    st.caption("Estudos que outros perfis compartilharam com o seu e-mail. Você pode abrir na "
               "aplicação (restaurar) ou baixar a planilha.")
    try:
        _recebidos = auth_service.listar_estudos_recebidos(_user.get("email", ""), _at, _rt)
    except Exception:
        _recebidos = []
    # [COMPARTILHAR - 448ª] o usuário abriu esta seção → marca os recebidos como VISTOS (zera o badge).
    try:
        auth_service.marcar_recebidos_como_vistos(_user["user_id"], _at, _rt)
        st.session_state["_badge_recebidos"] = 0
        st.session_state["_badge_recebidos_ts"] = time.time()
    except Exception:
        pass
    if _recebidos:
        st.caption(f"{len(_recebidos)} estudo(s) recebido(s).")
        for _rb in _recebidos:
            _rb_id = _rb.get("estudo_id")
            _rb_nome = (_rb.get("nome") or "Estudo").strip()
            _rb_res = _rb.get("resumo") or {}
            _rb_linhas = _rb_res.get("linhas_total", _rb_res.get("linhas_salvas", "?"))
            _rb_quando = _fmt_data(_rb.get("compartilhado_em")) or ""
            with st.expander(f"📥 {_rb_nome} — {_rb_linhas} linha(s) · recebido em {_rb_quando}", expanded=False):
                if _rb.get("mensagem"):
                    st.info(f"💬 {_rb['mensagem']}")
                _rbx1, _rbx2 = st.columns(2)
                if _rbx1.button("👁️ Abrir na aplicação", key=f"rb_open_{_rb_id}", use_container_width=True):
                    with st.spinner("Carregando estudo recebido..."):
                        _full = auth_service.carregar_estudo_por_id(_rb_id, _at, _rt)
                    _rb_dados = (_full or {}).get("dados")
                    if _rb_dados:
                        try:
                            st.session_state["df_processado"] = _pd.DataFrame(_rb_dados)
                            st.session_state["_mostrar_perfil"] = False
                            st.success("✅ Estudo recebido aberto na aplicação...")
                            time.sleep(0.9); st.rerun()
                        except Exception:
                            logger.error("[PERFIL] Falha ao abrir estudo recebido.", exc_info=True)
                            st.error("Não foi possível abrir este estudo.")
                    else:
                        st.error("Este estudo não tem dados para abrir (pode ter sido excluído pelo dono).")
                # botão de download: prepara o CSV sob demanda (mantém o payload fora do rerun até clicar em Abrir)
                if _rbx2.button("⬇️ Preparar download (CSV)", key=f"rb_prep_{_rb_id}", use_container_width=True):
                    with st.spinner("Preparando arquivo..."):
                        _full = auth_service.carregar_estudo_por_id(_rb_id, _at, _rt)
                    _rb_dados = (_full or {}).get("dados")
                    if _rb_dados:
                        try:
                            st.session_state[f"_rb_csv_{_rb_id}"] = _pd.DataFrame(_rb_dados).to_csv(index=False).encode("utf-8")
                        except Exception:
                            logger.error("[PERFIL] Falha ao preparar CSV do estudo recebido.", exc_info=True)
                            st.error("Não foi possível preparar o arquivo.")
                    else:
                        st.error("Este estudo não tem dados para baixar.")
                _csv_pronto = st.session_state.get(f"_rb_csv_{_rb_id}")
                if _csv_pronto:
                    st.download_button("⬇️ Baixar CSV", data=_csv_pronto,
                                       file_name=f"{_rb_nome[:60] or 'estudo_recebido'}.csv",
                                       mime="text/csv", key=f"rb_dl_{_rb_id}", use_container_width=True)
    else:
        st.caption("Nenhum estudo foi compartilhado com você ainda.")

    st.markdown("---")
    # [Perfil UX] Sair da conta direto do perfil (além da sidebar) — bloqueio real de sessão.
    _cv1, _cv2 = st.columns(2)
    with _cv1:
        if st.button("← Voltar para a aplicação", use_container_width=True):
            st.session_state["_mostrar_perfil"] = False
            st.rerun()
    with _cv2:
        if st.button("🚪 Sair da conta", use_container_width=True):
            encerrar_sessao()
            st.session_state["_mostrar_perfil"] = False
            st.rerun()


def _processar_retorno_oauth():
    """[LOGIN SOCIAL] Se o navegador voltou do provedor com ?code=... (ou ?error=...), conclui o
    login trocando o code por uma sessão do Supabase, usando o MESMO cliente OAuth do início
    (guarda o code_verifier do PKCE). Sem retorno pendente, não faz nada. Nunca levanta."""
    try:
        _qp = st.query_params
    except Exception:
        return
    _erro = _qp.get("error_description") or _qp.get("error")
    if _erro and not esta_autenticado():
        st.error("Login social não concluído: %s" % str(_erro)[:200])
        try:
            st.query_params.clear()
        except Exception:
            pass
        return
    _code = _qp.get("code")
    if not _code or esta_autenticado():
        return
    with st.spinner("Concluindo login..."):
        _res = auth_service.finalizar_login_social(_code)
    if _res.ok:
        _iniciar_sessao(_res.dados["user_id"], _res.dados["email"],
                        _res.dados["access_token"], _res.dados["refresh_token"])
        for _k in ("_oauth_url", "_oauth_prov_nome", "_sb_oauth_client"):
            st.session_state.pop(_k, None)
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    else:
        st.error(_res.mensagem)
        try:
            st.query_params.clear()
        except Exception:
            pass


def _renderizar_tela_autenticacao():
    _processar_retorno_oauth()
    # [UI-REENGENHARIA - Rodada 17] Mission UI/UX §49 ("regra dos 5 segundos" — ao abrir, o
    # usuário deve responder em poucos segundos "para que serve a aplicação?"). Esta é a
    # PRIMEIRA tela que todo usuário vê, e ela só dizia "entre ou crie sua conta" — nenhuma
    # explicação do que a ferramenta faz. Um visitante novo não tinha como saber se valia a
    # pena criar a conta. Adicionada uma frase de propósito, com a mesma linguagem já usada no
    # cartão "Comece por aqui" (onboarding pós-login) — não inventa uma descrição nova.
    st.markdown(
        "<div style='max-width:560px;margin:40px auto 0;text-align:center'>"
        "<h1 style='margin-bottom:0;color:var(--tx-1, #F9FAFB)'>🗺️ Motor Nacional de Inteligência Logística</h1>"
        "<p style='color:var(--tx-2, #E5E7EB);margin:10px 0 2px'>Analisa quanto cada candidato "
        "precisa se deslocar até seu local de prova e ajuda a decidir onde ela deve ser "
        "aplicada.</p>"
        "<p style='color:var(--tx-3, #9CA3AF)'>Entre ou crie sua conta para continuar.</p>"
        # [Login UX] Faixa de recursos REAIS da aplicação (regra dos 5 segundos): comunica
        # valor concreto antes do cadastro, sem inventar funcionalidade. Responsiva (flex-wrap).
        "<div style='display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:18px'>"
        + "".join(
            "<div style='flex:1 1 160px;min-width:150px;background:var(--sf-2, #1E232F);"
            "border:1px solid var(--sf-3, #2D3342);border-radius:12px;padding:12px 14px;text-align:left'>"
            f"<div style='font-size:1.4rem;line-height:1'>{_ic}</div>"
            f"<div style='color:var(--tx-1, #F9FAFB);font-weight:600;margin-top:6px'>{_ti}</div>"
            f"<div style='color:var(--tx-3, #9CA3AF);font-size:.82rem;margin-top:2px'>{_de}</div>"
            "</div>"
            for _ic, _ti, _de in (
                ("🛣️", "Distância real por estrada", "Rota viária multi-motor, não linha reta."),
                ("⛴️", "Detecta balsas e barreiras", "Rios, pontes e travessias que afetam o trajeto."),
                ("📊", "Melhor local de prova", "Recomenda o polo que minimiza o deslocamento."),
            ))
        + "</div>"
        "</div>", unsafe_allow_html=True)
    _col_esq, _col_mid, _col_dir = st.columns([1, 2, 1])
    with _col_mid:
        if not credenciais_configuradas():
            st.error("⚠️ Autenticação não configurada nesta instância — faltam `SUPABASE_URL` "
                     "e `SUPABASE_ANON_KEY` em `st.secrets`. Veja `auth/README.md`.")
            st.stop()
        _tela = st.session_state.get("_auth_tela", "login")
        if _tela == "cadastro":
            _tela_cadastro()
        elif _tela == "recuperar":
            _tela_recuperar()
        else:
            _tela_login()
    st.stop()


def abrir_perfil():
    """Chamado pela sidebar (ou qualquer outro ponto da UI) para abrir a tela de perfil no
    próximo rerun — não renderiza nada aqui, só sinaliza; `exigir_autenticacao()` é quem
    efetivamente desenha a tela e para a execução, mantendo o portão como o único lugar que
    decide o que aparece no lugar do conteúdo normal da aplicação."""
    st.session_state["_mostrar_perfil"] = True


def _tentar_reidratar_sessao() -> bool:
    """[PERSISTÊNCIA NO NAVEGADOR] Reidrata a sessão a partir da sessionStorage (F5/reconexão com a
    aba aberta). Devolve True se conseguiu — o app deve rerodar já autenticado. Fail-open e À PROVA
    DE LOOP: o componente de leitura devolve None na 1ª renderização (só monta e dispara um rerun) e
    o valor na seguinte; se os tokens forem DEFINITIVAMENTE rejeitados, limpa o navegador e desiste
    (mostra login) — nunca reidrata em círculos."""
    if esta_autenticado() or st.session_state.get("_reidratacao_desistiu"):
        return False
    _rest = browser_session.tentar_restaurar()
    if not _rest:
        return False
    _iniciar_sessao(_rest["user_id"], _rest["email"], _rest["access_token"], _rest["refresh_token"])
    # valida/renova na hora: o access_token guardado pode já ter expirado (renova via refresh_token).
    st.session_state["auth_last_check_ts"] = 0.0
    if _sessao_expirada_no_servidor():
        encerrar_sessao()                                  # refresh definitivamente rejeitado -> lixo
        st.session_state["_reidratacao_desistiu"] = True   # não tenta de novo neste carregamento
        return False
    st.session_state["auth_last_check_ts"] = time.time()
    return True


def exigir_autenticacao():
    """PORTÃO da aplicação — chamar uma única vez, logo no início do script principal.
    Bloqueia (st.stop()) enquanto não houver sessão válida; nada abaixo desta chamada
    executa para quem não estiver autenticado."""
    if not esta_autenticado():
        # [PERSISTÊNCIA NO NAVEGADOR] antes de exigir novo login, tenta reidratar do navegador —
        # assim um F5 / reconexão com a aba aberta NÃO desloga. Fail-open: se não houver sessão
        # guardada (ou o recurso estiver off), cai direto na tela de login como antes.
        if _tentar_reidratar_sessao():
            st.rerun()
        _renderizar_tela_autenticacao()
        return  # inalcançável (st.stop() acima), mantido por clareza de leitura

    # [§24 - SESSÃO EXPIRADA] revalida no servidor periodicamente (não a cada rerun, para
    # não gerar uma chamada de rede extra a cada interação — só a cada 5 minutos). Se a última
    # revalidação foi mantida por uma falha TRANSIENTE (rede/servidor), reduz a janela para ~45 s,
    # recuperando a sessão assim que a conectividade voltar — sem nunca ter derrubado o usuário.
    _intervalo = 45 if st.session_state.get("_auth_recheck_curto") else 300
    _ultima_checagem = st.session_state.get("auth_last_check_ts", 0)
    if time.time() - _ultima_checagem > _intervalo:
        if _sessao_expirada_no_servidor():
            encerrar_sessao()
            st.warning("Sua sessão expirou — faça login novamente.")
            _renderizar_tela_autenticacao()
            return
        st.session_state["auth_last_check_ts"] = time.time()

    # [PERSISTÊNCIA NO NAVEGADOR] mantém a sessionStorage em dia com o token ATUAL — grava no login e
    # após cada renovação, mas SÓ quando o access_token muda (sem churn a cada rerun). Assim um F5 na
    # aba encontra sempre o par de tokens mais recente para reidratar. Fail-open (no-op se off).
    _at = st.session_state.get("auth_access_token")
    if _at and st.session_state.get("_ultimo_token_persistido") != _at:
        browser_session.salvar(st.session_state.get("auth_user_id", ""),
                               st.session_state.get("auth_email", ""),
                               _at, st.session_state.get("auth_refresh_token", ""))
        st.session_state["_ultimo_token_persistido"] = _at

    # [§9 da missão - PERFIL] mesma mecânica do portão: enquanto a flag estiver ligada, a
    # tela de perfil substitui o conteúdo normal (st.stop() ao final) — nunca é sobreposta
    # visualmente, é bloqueio real de execução, igual à tela de login.
    if st.session_state.get("_mostrar_perfil"):
        _col_esq, _col_mid, _col_dir = st.columns([1, 3, 1])
        with _col_mid:
            _tela_perfil()
        st.stop()
