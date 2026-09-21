# -*- coding: utf-8 -*-
"""[PERSISTÊNCIA DE SESSÃO NO NAVEGADOR] Mantém o login do usuário no MESMO dispositivo/navegador —
sobrevive a F5/recarregar, a reconexões do WebSocket, a reinícios da app no servidor (Streamlit Cloud
reinicia o processo por inatividade/deploy/limite de memória — cada reinício zera o `st.session_state`)
e ao fechar/reabrir a aba ou o navegador. Só termina no LOGOUT explícito, na revogação do consentimento
ou quando o próprio Supabase deixa de aceitar o refresh_token.

Por que localStorage (default), e não sessionStorage:
  • O requisito de produto é NÃO deslogar o usuário sozinho. sessionStorage morre ao fechar a aba (e é
    descartada quando o navegador do celular recicla a aba em segundo plano), então por definição NÃO
    consegue cumprir "não deslogar". localStorage persiste no dispositivo até logout/limpeza explícita.
  • Continua sendo a opção segura para este fim: ao contrário de cookie, NUNCA é enviada automaticamente
    a nenhum servidor (sem superfície de CSRF); a fronteira de segurança REAL continua no servidor
    (RLS + revalidação do refresh_token a cada janela). O token guardado (refresh_token, de vida longa
    porém REVOGÁVEL) só é útil enquanto o Supabase o aceitar; logout revoga e `limpar()` apaga o registro.
  • Escopo configurável por secret `PERSISTIR_SESSAO_ESCOPO`: "local" (default, sobrevive ao fechamento)
    ou "sessao" (comportamento antigo, some ao fechar a aba) — o dono decide a postura.

Mecânica: o componente `streamlit_js_eval` roda num iframe MESMA-ORIGEM do app (ele já usa
`window.parent.document` para detectar o tema), então alcançamos o storage do APP via
`window.parent.localStorage`/`window.parent.sessionStorage`. O valor é um JSON em base64 urlsafe — só
[A-Za-z0-9_-=], sem aspas, imune a injeção na expressão JS.

TUDO fail-open: se o componente não existir, a expressão falhar, ou o secret desligar o recurso, as
funções viram no-op e o app se comporta exatamente como antes (tela de login). Nada aqui pode derrubar
o portão de autenticação."""
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


def _store() -> str:
    """Nome do storage do navegador a usar: 'localStorage' (default — sobrevive ao fechamento do
    navegador, cumpre "não deslogar sozinho") ou 'sessionStorage' (some ao fechar a aba). Configurável
    por secret `PERSISTIR_SESSAO_ESCOPO` = 'local'|'sessao'. Fail-open -> localStorage."""
    try:
        _v = str(st.secrets.get("PERSISTIR_SESSAO_ESCOPO", "local")).strip().lower()
        if _v in ("sessao", "sessão", "session", "aba", "tab"):
            return "sessionStorage"
    except Exception:
        pass
    return "localStorage"


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
    """Grava a sessão no storage do navegador (fire-and-forget). No-op se o recurso não estiver ativo.
    A `key` é derivada do conteúdo => o componente só re-executa quando o token muda (login/renovação),
    sem churn a cada rerun."""
    if not recurso_ativo():
        return
    try:
        _b64 = _serializar({"user_id": user_id, "email": email,
                            "access_token": access_token, "refresh_token": refresh_token})
        _sig = hashlib.sha1(_b64.encode("ascii")).hexdigest()[:12]
        _js(js_expressions=f"window.parent.{_store()}.setItem('{_CHAVE}','{_b64}')",
            key=f"or_sess_save_{_sig}")
    except Exception:
        logger.debug("[BROWSER-SESSION] Falha ao salvar sessão no navegador (ignorada).", exc_info=True)


def limpar() -> None:
    """Remove a sessão persistida (chamado no logout). Apaga em AMBOS os storages para não deixar
    resíduo caso o escopo tenha mudado entre execuções. No-op/fail-open."""
    if not _JS_OK:
        return
    try:
        _js(js_expressions=(f"(function(){{try{{window.parent.localStorage.removeItem('{_CHAVE}');}}"
                            f"catch(e){{}}try{{window.parent.sessionStorage.removeItem('{_CHAVE}');}}"
                            f"catch(e){{}}return 1;}})()"),
            key="or_sess_clear")
    except Exception:
        logger.debug("[BROWSER-SESSION] Falha ao limpar sessão do navegador (ignorada).", exc_info=True)


# Sentinela retornada pelo componente ENQUANTO o iframe ainda está montando (leitura assíncrona).
# Distingue "ainda carregando" de "resolveu e não havia nada" (null -> None) — assim o portão pode
# mostrar um "restaurando sessão…" em vez de piscar a tela de login antes de reidratar.
_PENDENTE = "__or_sess_pendente__"


def _ler_raw():
    """Lê o valor cru do storage (base64) do escopo primário, caindo no secundário. Devolve:
    _PENDENTE (componente ainda montando), None (resolveu vazio) ou a string base64. Fail-open."""
    if not recurso_ativo():
        return None
    try:
        _prim = _store()
        _sec = "sessionStorage" if _prim == "localStorage" else "localStorage"
        _expr = (f"(function(){{try{{var v=window.parent.{_prim}.getItem('{_CHAVE}');"
                 f"if(v)return v;}}catch(e){{}}try{{return window.parent.{_sec}.getItem('{_CHAVE}');}}"
                 f"catch(e){{}}return null;}})()")
        return _js(js_expressions=_expr, key="or_sess_restore", default=_PENDENTE)
    except Exception:
        logger.debug("[BROWSER-SESSION] Falha ao restaurar sessão do navegador (ignorada).", exc_info=True)
        return None


def restaurar_status():
    """Como `tentar_restaurar`, mas distingue o estado do componente assíncrono. Devolve:
      • "pendente" — o iframe ainda está montando; o valor real chega no próximo rerun;
      • None       — resolveu e NÃO havia sessão guardada (ou recurso off);
      • dict        — a sessão reidratável {user_id, email, access_token, refresh_token}."""
    _raw = _ler_raw()
    if _raw == _PENDENTE:
        return "pendente"
    return _desserializar(_raw)


def tentar_restaurar() -> dict | None:
    """Lê a sessão do storage do navegador. Devolve o dict {user_id, email, access_token,
    refresh_token} ou None (inclui o estado "ainda montando", tratado como None para simplicidade).
    Procura no escopo configurado E cai no outro (localStorage<->sessionStorage). Fail-open: erro => None."""
    _r = restaurar_status()
    return _r if isinstance(_r, dict) else None
