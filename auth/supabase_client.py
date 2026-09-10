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
    try:
        return create_client(_url, _key)
    except Exception:
        logger.error("[AUTH] Falha ao criar o cliente Supabase.", exc_info=True)
        return None


def credenciais_configuradas() -> bool:
    """Checagem rápida e read-only para a UI decidir se mostra o modo 'autenticação
    indisponível' (sem tentar conectar) — nunca lança."""
    try:
        return bool(str(st.secrets.get("SUPABASE_URL", "") or "").strip()
                    and str(st.secrets.get("SUPABASE_ANON_KEY", "") or "").strip())
    except Exception:
        return False
