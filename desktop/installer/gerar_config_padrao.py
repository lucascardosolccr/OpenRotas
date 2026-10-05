# -*- coding: utf-8 -*-
"""OpenRotas Desktop — gera a CONFIG PADRÃO EMBUTIDA (instalador turnkey).

Roda NO BUILD (CI). Lê as chaves de VARIÁVEIS DE AMBIENTE (alimentadas por SECRETS do
GitHub — nunca do código) e grava um blob OFUSCADO em desktop/config/_config_padrao.ork,
que o PyInstaller embute. Em runtime, desktop_config._defaults_embutidos() o lê e usa como
padrão (o desktop.json do usuário, se tiver valores reais, continua tendo prioridade).

Segurança (honesta): a chave anon/publishable é PÚBLICA por natureza; a ofuscação só evita
texto puro no disco — não é criptografia inquebrável. A proteção real dos dados é o RLS do
Supabase. A service_role JAMAIS deve ser passada aqui.

Sem as variáveis de ambiente (build comum, sem turnkey), NÃO gera nada e sai 0 — o app
segue dependendo do desktop.json do usuário, como antes.

Uso (no workflow):  python desktop/installer/gerar_config_padrao.py
Variáveis lidas:    ORK_SUPABASE_URL, ORK_SUPABASE_ANON_KEY, ORK_APP_URL (opcional),
                    ORK_GOOGLE_MAPS_API_KEY (opcional)
"""
from __future__ import annotations

import os
import sys
import json
import base64
import hashlib
from pathlib import Path

# DEVE casar com desktop/app/desktop_config.py (_OFUSCA_SALT / _desofuscar).
_OFUSCA_SALT = b"OpenRotas-Desktop-config-v1"

# Mapeia VARIÁVEL DE AMBIENTE -> chave da config. Só chaves PÚBLICAS/não-sensíveis.
_MAPA = {
    "ORK_SUPABASE_URL": "SUPABASE_URL",
    "ORK_SUPABASE_ANON_KEY": "SUPABASE_ANON_KEY",
    "ORK_APP_URL": "APP_URL",
    "ORK_GOOGLE_MAPS_API_KEY": "GOOGLE_MAPS_API_KEY",
}

# Trava de segurança: nunca embutir uma service_role / secret key.
_PROIBIDO = ("service_role", "sb_secret_", "supabase_service")


def _ofuscar(texto: str) -> bytes:
    raw = texto.encode("utf-8")
    chave = hashlib.sha256(_OFUSCA_SALT).digest()
    emb = bytes(b ^ chave[i % len(chave)] for i, b in enumerate(raw))
    return base64.b64encode(emb)


def main() -> int:
    dados = {}
    for env_nome, cfg_nome in _MAPA.items():
        val = (os.environ.get(env_nome) or "").strip()
        if val:
            dados[cfg_nome] = val

    if not dados.get("SUPABASE_URL") or not dados.get("SUPABASE_ANON_KEY"):
        print("[config-padrao] Sem ORK_SUPABASE_URL/ORK_SUPABASE_ANON_KEY — build sem turnkey "
              "(o app usará o desktop.json do usuário). Nada gerado.")
        return 0

    # Trava: aborta se alguém tentar embutir uma chave secreta.
    for k, v in dados.items():
        if any(p in str(v).lower() for p in _PROIBIDO):
            print("[config-padrao] ERRO: valor proibido (parece service_role/secret) em %s. "
                  "NÃO embuta chaves secretas no cliente. Abortando." % k, file=sys.stderr)
            return 2

    destino = Path(__file__).resolve().parents[1] / "config" / "_config_padrao.ork"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(_ofuscar(json.dumps(dados, ensure_ascii=False)))
    print("[config-padrao] Config padrão embutida gerada (%d chave(s): %s) em %s"
          % (len(dados), ", ".join(sorted(dados)), destino))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
