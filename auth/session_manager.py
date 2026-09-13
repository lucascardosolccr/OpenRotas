# -*- coding: utf-8 -*-
"""Gerenciamento de sessão e PORTÃO de autenticação da aplicação.

`exigir_autenticacao()` é a função central: chamada uma única vez, bem no início de
`streamlit_app.py` (depois do `st.set_page_config`/CSS, antes de qualquer conteúdo real),
ela renderiza a tela de login/cadastro/recuperação e chama `st.stop()` enquanto não houver
uma sessão válida — nenhum código abaixo dela roda para um visitante não autenticado. Isso
é proteção REAL (nada executa), não ocultação visual de menu.

LIMITAÇÃO CONHECIDA (documentada, não escondida): a sessão vive em `st.session_state`, que
é por ABA/conexão do navegador — um F5 na mesma aba mantém a sessão (Streamlit reidrata o
mesmo `session_state` na maioria dos casos), mas fechar e reabrir o navegador exige novo
login. Uma persistência tipo "lembrar-me" entre sessões de navegador exigiria um componente
de cookies dedicado (ex.: streamlit-cookies-manager) — fora do escopo deste bloco inicial,
candidato a rodada futura."""
import logging
import time

import streamlit as st

from auth import auth_service, email_service, validators
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


def _iniciar_sessao(user_id: str, email: str, access_token: str, refresh_token: str):
    st.session_state["auth_user_id"] = user_id
    st.session_state["auth_email"] = email
    st.session_state["auth_access_token"] = access_token
    st.session_state["auth_refresh_token"] = refresh_token
    st.session_state["auth_login_ts"] = time.time()


def encerrar_sessao():
    auth_service.fazer_logout()
    for _k in _SESSION_KEYS:
        st.session_state.pop(_k, None)
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
            return False
    except Exception:
        pass  # access_token expirado/inválido -> tenta renovar com o refresh_token abaixo

    _renov = auth_service.renovar_sessao(st.session_state.get("auth_refresh_token"))
    if _renov.ok:
        st.session_state["auth_access_token"] = _renov.dados["access_token"]
        st.session_state["auth_refresh_token"] = _renov.dados["refresh_token"]
        return False
    return True  # refresh_token também inválido -> sessão realmente expirada


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
        _ok_senha, _erro_senha, _ = validators.validar_forca_senha(_senha)
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
                    auth_service.atualizar_perfil(_res.dados["user_id"], _end_norm)
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
            _ok_senha, _erro_senha, _ = validators.validar_forca_senha(_nova)
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

    with st.spinner("Carregando perfil..."):
        _perfil = auth_service.obter_perfil(_user["user_id"])

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
        st.markdown(
            "<div style='display:flex;align-items:center;gap:16px;background:var(--sf-2,#1E232F);"
            "border:1px solid var(--sf-3,#2D3342);border-radius:14px;padding:16px 18px;margin-bottom:10px'>"
            "<div style='flex:0 0 auto;width:56px;height:56px;border-radius:50%;background:var(--brand,#3B82F6);"
            "color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.25rem;font-weight:700'>"
            + _html.escape(_iniciais) + "</div>"
            "<div style='min-width:0'>"
            "<div style='color:var(--tx-1,#F9FAFB);font-weight:700;font-size:1.05rem'>" + _html.escape(_nome_disp) + "</div>"
            "<div style='color:var(--tx-3,#9CA3AF);font-size:.85rem'>✉️ " + _html.escape(_user['email'] or '—') + "</div>"
            + ("<div style='color:var(--tx-4,#6B7280);font-size:.78rem;margin-top:2px'>" + _meta_html + "</div>" if _meta_html else "")
            + "</div></div>", unsafe_allow_html=True)
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
                with st.spinner("Salvando..."):
                    _res = auth_service.atualizar_perfil(_user["user_id"], _campos)
                if _res.ok:
                    st.success("✅ " + _res.mensagem)
                    time.sleep(1.0)
                    st.rerun()
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


def _renderizar_tela_autenticacao():
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


def exigir_autenticacao():
    """PORTÃO da aplicação — chamar uma única vez, logo no início do script principal.
    Bloqueia (st.stop()) enquanto não houver sessão válida; nada abaixo desta chamada
    executa para quem não estiver autenticado."""
    if not esta_autenticado():
        _renderizar_tela_autenticacao()
        return  # inalcançável (st.stop() acima), mantido por clareza de leitura

    # [§24 - SESSÃO EXPIRADA] revalida no servidor periodicamente (não a cada rerun, para
    # não gerar uma chamada de rede extra a cada interação — só a cada 5 minutos).
    _ultima_checagem = st.session_state.get("auth_last_check_ts", 0)
    if time.time() - _ultima_checagem > 300:
        if _sessao_expirada_no_servidor():
            encerrar_sessao()
            st.warning("Sua sessão expirou — faça login novamente.")
            _renderizar_tela_autenticacao()
            return
        st.session_state["auth_last_check_ts"] = time.time()

    # [§9 da missão - PERFIL] mesma mecânica do portão: enquanto a flag estiver ligada, a
    # tela de perfil substitui o conteúdo normal (st.stop() ao final) — nunca é sobreposta
    # visualmente, é bloqueio real de execução, igual à tela de login.
    if st.session_state.get("_mostrar_perfil"):
        _col_esq, _col_mid, _col_dir = st.columns([1, 3, 1])
        with _col_mid:
            _tela_perfil()
        st.stop()
