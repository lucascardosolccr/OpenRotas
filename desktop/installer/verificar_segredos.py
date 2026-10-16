# -*- coding: utf-8 -*-
"""OpenRotas Desktop — VARREDURA DE SEGREDOS (trava de segurança §SEC).

Garante que nenhuma CHAVE SECRETA entre no repositório/bundle. A regra do projeto é absoluta:
só a chave `anon`/`sb_publishable` pode aparecer no cliente; chaves de servidor
(`service_role`, `sb_secret`, `SUPABASE_SERVICE_ROLE`) JAMAIS podem ser commitadas — elas vivem
apenas em GitHub Secrets. Este scanner roda no CI (workflow verificar-segredos.yml) e falha o
build se encontrar um marcador de chave secreta em qualquer arquivo de texto versionado.

Projetado para NÃO se auto-detectar: os marcadores são montados a partir de fragmentos, e os
diretórios de teste e este próprio arquivo são ignorados por padrão.
"""
from __future__ import annotations

import os
import re
import sys
import base64
from pathlib import Path

# IMPORTANTE: detectamos o VALOR de uma chave secreta real — não a mera MENÇÃO da palavra
# "service_role" (que aparece, de propósito, no código de VALIDAÇÃO que PROÍBE essa chave).
# Caçar a palavra solta daria falso positivo justamente nas travas de segurança do projeto.
#   (1) sb_secret_<material> → novo formato de chave SECRETA do Supabase (prefixo + material).
#   (2) JWT (eyJ...eyJ...sig) cujo PAYLOAD decodificado contém "role":"service_role".
_PREFIXO_SECRET = "sb" + "_secret_"      # montado por partes p/ o scanner não se auto-detectar
_RE_SB_SECRET = re.compile(re.escape(_PREFIXO_SECRET) + r"[A-Za-z0-9]{16,}")
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}")
_ROLE_SERVIDOR = "service" + "_role"


def _jwt_e_de_servidor(token: str) -> bool:
    """True se o PAYLOAD do JWT indicar role de servidor (service_role). Decodifica o 2º segmento
    (base64url). Nunca levanta."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        dec = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8", "ignore")
        return _ROLE_SERVIDOR in dec
    except Exception:
        return False

# Extensões de texto que valem a pena varrer (binários e mídia são ignorados).
_EXT_TEXTO = {".py", ".txt", ".md", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg",
              ".env", ".ps1", ".bat", ".sh", ".js", ".ts", ".html", ".css", ".spec"}

# Diretórios sempre ignorados (ruído / contêm os marcadores de propósito).
_DIRS_IGNORADOS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                   "tests", "test", ".pytest_cache"}


def _e_texto(p: Path) -> bool:
    if p.suffix.lower() in _EXT_TEXTO:
        return True
    return p.name.lower() in ("dockerfile", ".gitignore", ".env")


def escanear_segredos(roots, ignorar=None) -> list:
    """Varre `roots` e devolve uma lista de achados {arquivo, linha, marcador}. Ignora os
    diretórios de _DIRS_IGNORADOS, este próprio arquivo e quaisquer caminhos cujo nome esteja em
    `ignorar`. Nunca levanta — um arquivo ilegível é pulado."""
    achados = []
    ignorar = set(ignorar or ())
    eu = Path(__file__).resolve()
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        arquivos = [base] if base.is_file() else base.rglob("*")
        for p in arquivos:
            try:
                if p.is_dir():
                    continue
                if any(part in _DIRS_IGNORADOS for part in p.parts):
                    continue
                if p.resolve() == eu or p.name in ignorar:
                    continue
                if not _e_texto(p):
                    continue
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for i, linha in enumerate(f, 1):
                        if _RE_SB_SECRET.search(linha):
                            achados.append({"arquivo": str(p), "linha": i,
                                            "marcador": "sb_secret key"})
                        for tok in _RE_JWT.findall(linha):
                            if _jwt_e_de_servidor(tok):
                                achados.append({"arquivo": str(p), "linha": i,
                                                "marcador": "service_role JWT"})
            except Exception:
                continue
    return achados


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    roots = argv or ["."]
    achados = escanear_segredos(roots)
    if not achados:
        print("VARREDURA DE SEGREDOS: OK — nenhum marcador de chave secreta encontrado.")
        return 0
    print("VARREDURA DE SEGREDOS: FALHOU — possível chave SECRETA versionada:")
    for a in achados:
        print("  x %s:%s  (marcador: %s)" % (a["arquivo"], a["linha"], a["marcador"]))
    print("\nChaves de servidor (service_role/sb_secret) NÃO podem ser commitadas — use GitHub "
          "Secrets. Só a chave anon/sb_publishable pode ir ao cliente.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
