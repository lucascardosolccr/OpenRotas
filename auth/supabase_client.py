# -*- coding: utf-8 -*-
"""Cliente Supabase compartilhado pela aplicação — um único ponto de criação, cacheado por
processo (mesmo padrão de `st.cache_resource` já usado em outras integrações desta app).

Requer, em `st.secrets` (arquivo `.streamlit/secrets.toml` local, ou "Secrets" no painel do
Streamlit Cloud em produção — nunca commitado):

    SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
    SUPABASE_ANON_KEY = "sua-chave-anon-publica"

A "anon key" é a chave PÚBLICA do projeto (segura para expor em um cliente — o Supabase a
usa como identificador do projeto, não como segredo de administrador; a segurança real vem
das políticas de Row Level Security no banco, configuradas em `auth/schema.sql`). NUNCA use
a "service_role key" aqui — essa sim é um segredo de administrador que ignora RLS e nunca
deve rodar num cliente Streamlit.
"""
import logging

import streamlit as st

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    _SUPABASE_SDK_DISPONIVEL = True
except Exception:
    _SUPABASE_SDK_DISPONIVEL = False
    Client = None  # type: ignore


def sdk_disponivel() -> bool:
    """True se o pacote `supabase` está instalado (requirements.txt). Falso só indica um
    ambiente onde a dependência não foi instalada — nunca um erro de configuração."""
    return _SUPABASE_SDK_DISPONIVEL


@st.cache_resource(show_spinner=False)
def obter_cliente():
    """Cliente Supabase compartilhado por processo. None (nunca lança) quando o SDK não
    está instalado ou as credenciais não foram configuradas em st.secrets — quem chama
    trata None como 'autenticação indisponível', nunca tenta adivinhar uma credencial."""
    if not _SUPABASE_SDK_DISPONIVEL:
        logger.error("[AUTH] Pacote 'supabase' não instalado — ver requirements.txt.")
        return None
    try:
        _url = str(st.secrets.get("SUPABASE_URL", "") or "").strip()
        _key = str(st.secrets.get("SUPABASE_ANON_KEY", "") or "").strip()
    except Exception:
        _url, _key = "", ""
    if not _url or not _key:
        logger.error("[AUTH] SUPABASE_URL/SUPABASE_ANON_KEY ausentes em st.secrets.")
        return None
    # [REFRESH ÚNICO] Desliga o auto-refresh em thread de fundo do supabase-py neste cliente.
    # Motivo: cada set_session/refresh_session dispara internamente um threading.Timer
    # (_start_auto_refresh_token) que, perto do vencimento, RENOVA o token numa thread de
    # fundo. Como o refresh_token do Supabase é ROTATIVO (cada renovação invalida o anterior),
    # esse refresher de fundo rotaciona o token e grava o novo SÓ na sessão em memória do
    # cliente — nunca de volta no st.session_state. Num estudo longo, a thread principal fica
    # ocupada, o timer dispara, rotaciona o token e o próximo rerun apresenta o token já
    # invalidado -> 400 Bad Request -> logout forçado no meio do processamento.
    # A app JÁ tem seu próprio refresh, explícito e que PERSISTE os tokens novos no
    # st.session_state (session_manager._sessao_expirada_no_servidor, a cada rerun). Desligando
    # o auto-refresh do SDK, esse passa a ser o ÚNICO renovador — fim da corrida de rotação.
    # persist_session=False: este singleton é @st.cache_resource (compartilhado por TODO o
    # processo); não deve guardar a sessão de um usuário no seu storage interno — cada operação
    # já reaplica a sessão via set_session. Zero mudança de comportamento para a app, que nunca
    # dependeu do refresher de fundo nem do storage interno do SDK. Segurança inalterada: segue
    # usando só a anon key e a RLS. Fallback sem opções se o ClientOptions não aceitar os campos.
    try:
        try:
            # create_client (síncrono) espera SyncClientOptions; a base ClientOptions não
            # carrega 'storage' nesta versão. Importa a síncrona e cai para a base se preciso.
            from supabase.lib.client_options import SyncClientOptions as _ClientOptions
        except Exception:
            from supabase.lib.client_options import ClientOptions as _ClientOptions
        return create_client(_url, _key, options=_ClientOptions(
            auto_refresh_token=False, persist_session=False))
    except Exception:
        logger.debug("[AUTH] ClientOptions indisponível; criando cliente com padrões.", exc_info=True)
    try:
        return create_client(_url, _key)
    except Exception:
        logger.error("[AUTH] Falha ao criar o cliente Supabase.", exc_info=True)
        return None


def obter_cliente_oauth():
    """Cliente Supabase dedicado ao fluxo de LOGIN SOCIAL (Google/Microsoft), guardado em
    st.session_state para persistir DENTRO da mesma sessão do navegador.

    Por quê separado: o OAuth PKCE gera um 'code_verifier' no início (sign_in_with_oauth) que
    precisa estar disponível no RETORNO (exchange_code_for_session), depois do usuário ir ao
    Google/Microsoft e voltar. O supabase-py guarda esse verifier na memória do PRÓPRIO cliente,
    e nesta versão não dá para injetar um storage custom via ClientOptions. Então reutilizamos a
    MESMA instância do cliente (cacheada na sessão) nos dois momentos — como o Streamlit reconecta
    o navegador à mesma sessão após o redirect, o verifier sobrevive. flow_type='pkce' explícito.
    None (nunca lança) quando indisponível."""
    if not _SUPABASE_SDK_DISPONIVEL:
        return None
    _cache = st.session_state.get("_sb_oauth_client")
    if _cache is not None:
        return _cache
    try:
        _url = str(st.secrets.get("SUPABASE_URL", "") or "").strip()
        _key = str(st.secrets.get("SUPABASE_ANON_KEY", "") or "").strip()
    except Exception:
        _url, _key = "", ""
    if not _url or not _key:
        return None
    try:
        from supabase.lib.client_options import ClientOptions
        _cli = create_client(_url, _key, options=ClientOptions(flow_type="pkce"))
    except Exception:
        try:
            _cli = create_client(_url, _key)  # fallback: sem opções (flow padrão)
        except Exception:
            logger.error("[AUTH] Falha ao criar cliente OAuth.", exc_info=True)
            return None
    st.session_state["_sb_oauth_client"] = _cli
    return _cli


def credenciais_configuradas() -> bool:
    """Checagem rápida e read-only para a UI decidir se mostra o modo 'autenticação
    indisponível' (sem tentar conectar) — nunca lança."""
    try:
        return bool(str(st.secrets.get("SUPABASE_URL", "") or "").strip()
                    and str(st.secrets.get("SUPABASE_ANON_KEY", "") or "").strip())
    except Exception:
        return False
