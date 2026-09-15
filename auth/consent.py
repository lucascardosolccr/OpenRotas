# -*- coding: utf-8 -*-
"""[LGPD · CONSENTIMENTO DE ARMAZENAMENTO] Consentimento informado, opt-in e revogável para a
PERSISTÊNCIA DE SESSÃO no navegador (o token guardado na sessionStorage que mantém o login ao
recarregar a página). Cumpre a Lei 13.709/2018 (LGPD):

  • Base legal: CONSENTIMENTO do titular (Art. 7, I) — a persistência é OPT-IN; nada é guardado
    até o usuário aceitar. Cookies estritamente necessários do Streamlit (sessão técnica) seguem
    o Art. 7 (execução do serviço) e são apenas informados, não bloqueados.
  • Informação clara (Art. 9): o banner diz O QUÊ se guarda, PARA QUÊ, POR QUANTO TEMPO e como
    revogar, sem juridiquês.
  • Revogável a qualquer tempo (Art. 8, §5): controle no Perfil.
  • Sem rastreamento/publicidade e sem compartilhamento com terceiros.

Implementação: a DECISÃO fica num cookie próprio (`openrotas_consent_v1` = "sim"/"nao", 12 meses),
lido NATIVAMENTE por `st.context.cookies` (sem round-trip) e gravado uma vez via `set_cookie` do
componente. A decisão também é espelhada no `st.session_state` para valer NA HORA (sem corrida com
o round-trip do cookie). Tudo fail-open: sem o componente/JS, o recurso simplesmente não aparece e
o app volta ao comportamento sem persistência."""
import logging

logger = logging.getLogger(__name__)

_COOKIE = "openrotas_consent_v1"
_DURACAO_DIAS = 365
_CACHE_SESSAO = "_consent_persistir_sessao"

try:
    import streamlit as st
    from streamlit_js_eval import set_cookie as _set_cookie
    _OK = True
except Exception:  # pragma: no cover
    _OK = False


def disponivel() -> bool:
    """True se o mecanismo de persistência (e portanto o consentimento) está disponível. Reusa o
    mesmo kill-switch da persistência: PERSISTIR_SESSAO_NAVEGADOR='false' desliga tudo."""
    if not _OK:
        return False
    try:
        _v = str(st.secrets.get("PERSISTIR_SESSAO_NAVEGADOR", "true")).strip().lower()
        return _v not in ("false", "0", "no", "off", "nao", "não")
    except Exception:
        return True


def _interpretar(valor) -> "bool | None":
    """'sim'->True, 'nao'->False, qualquer outra coisa (inclusive ausência) -> None. PURO."""
    _v = str(valor if valor is not None else "").strip().lower()
    if _v in ("sim", "true", "1", "aceito", "yes", "y"):
        return True
    if _v in ("nao", "não", "false", "0", "recusado", "no", "n"):
        return False
    return None


def decisao() -> "bool | None":
    """Decisão de consentimento: True (aceitou persistir), False (recusou) ou None (ainda não
    decidiu). Preferimos o espelho em session_state (vale na hora nesta sessão) e caímos no cookie
    (persistido entre sessões do navegador). Fail-open -> None."""
    if not _OK:
        return None
    try:
        _cache = st.session_state.get(_CACHE_SESSAO)
        if _cache is not None:
            return bool(_cache)
        return _interpretar(st.context.cookies.get(_COOKIE))
    except Exception:
        return None


def registrar(aceito: bool) -> None:
    """Grava a decisão: espelho imediato no session_state + cookie de 12 meses (para lembrar entre
    sessões do navegador). Fail-open."""
    if not _OK:
        return
    try:
        st.session_state[_CACHE_SESSAO] = bool(aceito)
    except Exception:
        pass
    try:
        _set_cookie(_COOKIE, "sim" if aceito else "nao", _DURACAO_DIAS,
                    component_key=f"or_consent_set_{'sim' if aceito else 'nao'}")
    except Exception:
        logger.debug("[CONSENT] Falha ao gravar cookie de consentimento (ignorada).", exc_info=True)


_TEXTO_DETALHE = (
    "**O que guardamos e por quê.** Ao aceitar, guardamos no **seu próprio navegador** "
    "(`sessionStorage`, que some ao fechar a aba) um identificador da sua sessão para **manter você "
    "conectado ao recarregar a página** — assim um F5 ou uma reconexão não exigem novo login. Um "
    "**cookie** guarda **apenas a sua escolha** aqui (sim/não), por 12 meses, para não perguntarmos "
    "de novo.\n\n"
    "**Base legal (LGPD).** Consentimento (Art. 7, I) para essa conveniência de manter a sessão. Os "
    "cookies técnicos do Streamlit (sessão da aplicação) são estritamente necessários para o serviço "
    "funcionar e não dependem desta escolha.\n\n"
    "**Não fazemos rastreamento** nem publicidade, e **não compartilhamos** nada com terceiros. Você "
    "pode **revogar quando quiser** no seu **Perfil → Privacidade**."
)


def banner() -> bool:
    """Renderiza o banner de consentimento (não bloqueante) e grava a decisão. Deve ser chamado só
    quando `decisao() is None` e o usuário está autenticado. Devolve True se o usuário acabou de
    decidir agora (o clique já dispara o rerun natural do Streamlit)."""
    if not _OK:
        return False
    try:
        with st.container(border=True):
            st.markdown("🍪 **Cookies e sua sessão** — Podemos **manter você conectado neste "
                        "navegador** (some ao fechar a aba) para você não precisar relogar a cada "
                        "recarregamento. É **opcional** e você decide agora:")
            with st.expander("Como usamos seus dados (LGPD)"):
                st.markdown(_TEXTO_DETALHE)
            _c1, _c2, _sp = st.columns([1.2, 1.2, 2])
            _sim = _c1.button("Aceitar e manter conectado", type="primary",
                              key="or_consent_aceitar", use_container_width=True)
            _nao = _c2.button("Somente o essencial", key="or_consent_recusar",
                              use_container_width=True,
                              help="Não guarda a sessão; você faz login a cada recarregamento.")
        if _sim:
            registrar(True)
            return True
        if _nao:
            registrar(False)
            return True
        return False
    except Exception:
        logger.debug("[CONSENT] Falha ao renderizar o banner (ignorada).", exc_info=True)
        return False


def controle_preferencias(ao_revogar=None) -> None:
    """Controle de preferências de privacidade para o Perfil: mostra a escolha atual e permite
    alterá-la a qualquer momento (Art. 8, §5 da LGPD). `ao_revogar` é chamado quando o usuário
    passa a NÃO permitir (para o chamador apagar a sessão já guardada no navegador). Fail-open."""
    if not disponivel():
        return
    try:
        _atual = decisao()
        st.markdown("#### 🔒 Privacidade e cookies")
        _rotulo = {True: "✅ Permitido — sua sessão é mantida neste navegador (some ao fechar a aba).",
                   False: "🚫 Não permitido — você faz login a cada recarregamento.",
                   None: "❔ Ainda não definido."}[_atual]
        st.caption(f"Manter a sessão no navegador: **{_rotulo}**")
        with st.expander("Como usamos seus dados (LGPD)"):
            st.markdown(_TEXTO_DETALHE)
        _c1, _c2 = st.columns(2)
        if _atual is not True and _c1.button("Permitir manter a sessão", key="or_consent_pref_sim",
                                             use_container_width=True):
            registrar(True)
            st.rerun()
        if _atual is not False and _c2.button("Não permitir / revogar", key="or_consent_pref_nao",
                                              use_container_width=True):
            registrar(False)
            if callable(ao_revogar):
                try:
                    ao_revogar()
                except Exception:
                    pass
            st.rerun()
    except Exception:
        logger.debug("[CONSENT] Falha no controle de preferências (ignorada).", exc_info=True)
