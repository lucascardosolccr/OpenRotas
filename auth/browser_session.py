# -*- coding: utf-8 -*-
"""[PERSISTÊNCIA DE SESSÃO NO NAVEGADOR] Mantém o login enquanto a ABA do navegador estiver
aberta — sobrevive a F5/recarregar e a reconexões do WebSocket, e some ao fechar a aba/navegador.

Por que sessionStorage (e não cookie/localStorage):
  • sessionStorage é EFÊMERA (apagada ao fechar a aba) — casa exatamente com "não expira enquanto o
    navegador não for fechado" e é a opção mais segura: nunca vai pro disco a longo prazo e, ao
    contrário de cookie, não é enviada automaticamente a nenhum servidor (sem superfície de CSRF).
  • O token só é ÚTIL enquanto o Supabase o aceitar — a fronteira de segurança REAL continua no
    servidor (RLS + revalidação com refresh_token). Isto aqui é só conveniência de continuidade.

Mecânica: o componente `streamlit_js_eval` roda num iframe MESMA-ORIGEM do app (ele já usa
`window.parent.document` para detectar o tema), então alcançamos a sessionStorage do APP via
`window.parent.sessionStorage`. O valor é um JSON em base64 urlsafe — só [A-Za-z0-9_-=], sem aspas,
imune a injeção na expressão JS.

TUDO fail-open: se o componente não existir, a expressão falhar, ou o secret desligar o recurso,
as funções viram no-op e o app se comporta exatamente como antes (tela de login). Nada aqui pode
derrubar o portão de autenticação."""
import base64
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

_CHAVE = "openrotas_sessao_v1"
_CAMPOS = ("user_id", "email", "access_token", "refresh_token")

try:
    import streamlit as st
    from streamlit_js_eval import streamlit_js_eval as _js
    _JS_OK = True
except Exception:  # pragma: no cover - componente ausente => recurso simplesmente desligado
    _JS_OK = False


def recurso_ativo() -> bool:
    """True se a persistência no navegador está disponível E não foi desligada por secret.
    Kill-switch: definir `PERSISTIR_SESSAO_NAVEGADOR = "false"` em st.secrets desliga na hora."""
    if not _JS_OK:
        return False
    try:
        _v = str(st.secrets.get("PERSISTIR_SESSAO_NAVEGADOR", "true")).strip().lower()
        return _v not in ("false", "0", "no", "off", "nao", "não")
    except Exception:
        return True  # sem secrets configurados => ativo por padrão


def _serializar(dados: dict) -> str:
    """dict -> JSON -> base64 urlsafe (sem aspas/again: seguro para embutir na expressão JS). PURO."""
    _bruto = json.dumps({_k: dados.get(_k, "") for _k in _CAMPOS}, separators=(",", ":"))
    return base64.urlsafe_b64encode(_bruto.encode("utf-8")).decode("ascii")


def _desserializar(blob) -> dict | None:
    """base64 -> JSON -> dict validado. Devolve None para qualquer coisa inválida/incompleta.
    PURO/defensivo — nunca levanta."""
    try:
        if not blob or not isinstance(blob, str):
            return None
        _txt = base64.urlsafe_b64decode(blob.encode("ascii")).decode("utf-8")
        _d = json.loads(_txt)
        if not isinstance(_d, dict):
            return None
        # exige o mínimo para reidratar uma sessão: id + os dois tokens
        if not (_d.get("user_id") and _d.get("access_token") and _d.get("refresh_token")):
            return None
        return {_k: str(_d.get(_k, "") or "") for _k in _CAMPOS}
    except Exception:
        return None


def salvar(user_id: str, email: str, access_token: str, refresh_token: str) -> None:
    """Grava a sessão na sessionStorage do navegador (fire-and-forget). No-op se o recurso não
    estiver ativo. A `key` é derivada do conteúdo => o componente só re-executa quando o token
    muda (login/renovação), sem churn a cada rerun."""
    if not recurso_ativo():
        return
    try:
        _b64 = _serializar({"user_id": user_id, "email": email,
                            "access_token": access_token, "refresh_token": refresh_token})
        _sig = hashlib.sha1(_b64.encode("ascii")).hexdigest()[:12]
        _js(js_expressions=f"window.parent.sessionStorage.setItem('{_CHAVE}','{_b64}')",
            key=f"or_sess_save_{_sig}")
    except Exception:
        logger.debug("[BROWSER-SESSION] Falha ao salvar sessão no navegador (ignorada).", exc_info=True)


def limpar() -> None:
    """Remove a sessão persistida (chamado no logout). No-op/fail-open."""
    if not _JS_OK:
        return
    try:
        _js(js_expressions=f"window.parent.sessionStorage.removeItem('{_CHAVE}')",
            key="or_sess_clear")
    except Exception:
        logger.debug("[BROWSER-SESSION] Falha ao limpar sessão do navegador (ignorada).", exc_info=True)


def tentar_restaurar() -> dict | None:
    """Lê a sessão da sessionStorage do navegador. Devolve o dict {user_id, email, access_token,
    refresh_token} ou None. O componente é assíncrono: na PRIMEIRA renderização devolve None (ainda
    montando) e dispara um rerun; na seguinte devolve o valor. Fail-open: qualquer erro => None."""
    if not recurso_ativo():
        return None
    try:
        _raw = _js(js_expressions=f"window.parent.sessionStorage.getItem('{_CHAVE}')",
                   key="or_sess_restore", default=None)
        return _desserializar(_raw)
    except Exception:
        logger.debug("[BROWSER-SESSION] Falha ao restaurar sessão do navegador (ignorada).", exc_info=True)
        return None
