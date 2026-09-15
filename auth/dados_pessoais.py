# -*- coding: utf-8 -*-
"""[LGPD · DIREITOS DO TITULAR] Portabilidade dos dados pessoais (Lei 13.709/2018, Art. 18, IV e V):
permite ao usuário BAIXAR uma cópia completa e legível de tudo que ele forneceu ou gerou nesta
aplicação — perfil, estudos salvos, anotações e compartilhamentos — num arquivo JSON.

Só lê os DADOS DO PRÓPRIO usuário, via os mesmos caminhos com RLS (chave anônima + sessão do
titular) usados pelo resto do app — nunca `service_role`. O núcleo (montagem/serialização) é PURO e
testável; a coleta na rede é um envelope fail-open (cada parte que faltar vira vazia)."""
import json
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

# chaves que NUNCA devem sair num export, por higiene (o export é dado pessoal, não credencial)
_CHAVES_SENSIVEIS = ("token", "senha", "password", "secret", "hash", "api_key", "apikey")

_AVISO = ("Este arquivo contém os dados pessoais que você forneceu ou gerou nesta aplicação, "
          "exportados a seu pedido (LGPD, Lei 13.709/2018, Art. 18 — portabilidade e acesso). "
          "NÃO inclui tokens de sessão, senhas ou segredos. Guarde-o com cuidado: qualquer pessoa "
          "com este arquivo vê os dados aqui contidos.")


def _sensivel(chave) -> bool:
    _k = str(chave).lower()
    return any(_s in _k for _s in _CHAVES_SENSIVEIS)


def _sanear(obj):
    """Converte recursivamente para algo serializável em JSON e REMOVE chaves sensíveis de qualquer
    dicionário (defesa em profundidade — o perfil não deveria ter tokens, mas garantimos). PURO."""
    if isinstance(obj, dict):
        return {k: _sanear(v) for k, v in obj.items() if not _sensivel(k)}
    if isinstance(obj, (list, tuple)):
        return [_sanear(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)  # Decimal, UUID, etc. -> texto legível


def montar_pacote(user: dict, perfil, anotacoes, estudos, recebidos, gerado_em=None) -> dict:
    """Monta o pacote de portabilidade (dict pronto para virar JSON). PURO/defensivo — aceita None
    em qualquer parte e devolve estrutura estável, sempre com o mesmo formato."""
    _user = user or {}
    _perfil = _sanear(perfil) if isinstance(perfil, dict) else {}
    _anot = _sanear(anotacoes) if isinstance(anotacoes, (list, tuple)) else []
    _est = _sanear(estudos) if isinstance(estudos, (list, tuple)) else []
    _rec = _sanear(recebidos) if isinstance(recebidos, (list, tuple)) else []
    _ts = gerado_em or datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "aplicacao": "OpenRotas — Motor Nacional de Inteligência Logística para Exames",
        "gerado_em": _ts,
        "aviso_lgpd": _AVISO,
        "titular": {"user_id": str(_user.get("user_id", "") or ""),
                    "email": str(_user.get("email", "") or "")},
        "perfil": _perfil,
        "estudos_salvos": _est,
        "anotacoes": _anot,
        "estudos_recebidos": _rec,
        "resumo": {"estudos_salvos": len(_est), "anotacoes": len(_anot),
                   "estudos_recebidos": len(_rec)},
    }


def serializar_json(pacote: dict) -> bytes:
    """Serializa o pacote em JSON legível (UTF-8, indentado, acentos preservados). PURO — nunca
    levanta (em falha, devolve um JSON mínimo com a mensagem de erro)."""
    try:
        return json.dumps(pacote, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    except Exception:
        logger.debug("[LGPD-EXPORT] Falha ao serializar (fallback mínimo).", exc_info=True)
        return json.dumps({"erro": "não foi possível serializar os dados"},
                          ensure_ascii=False).encode("utf-8")


def coletar(user: dict, access_token: str = "", refresh_token: str = "") -> dict:
    """Envelope de REDE (fail-open): lê perfil, estudos, anotações e recebidos do PRÓPRIO usuário via
    auth_service (RLS) e devolve o pacote montado. Cada parte que falhar vira vazia — o export sempre
    sai, mesmo que parcial."""
    from auth import auth_service
    _uid = str((user or {}).get("user_id", "") or "")
    _email = str((user or {}).get("email", "") or "")

    def _seguro(fn, *a):
        try:
            return fn(*a)
        except Exception:
            logger.debug("[LGPD-EXPORT] parte do export falhou (ignorada).", exc_info=True)
            return None
    _perfil = _seguro(auth_service.obter_perfil, _uid, access_token, refresh_token)
    _est = _seguro(auth_service.listar_estudos, _uid, access_token, refresh_token)
    _anot = _seguro(auth_service.listar_anotacoes, _uid, access_token, refresh_token)
    _rec = _seguro(auth_service.listar_estudos_recebidos, _email, access_token, refresh_token)
    return montar_pacote(user, _perfil, _est, _anot, _rec)
