# -*- coding: utf-8 -*-
"""OpenRotas Desktop — AUTODIAGNÓSTICO de recursos (§17/§18).

Verifica, sem levantar, se os recursos que a edição desktop precisa estão presentes e
íntegros: bases geográficas embarcadas, diretórios persistentes do usuário e (opcional)
o motor de rotas local. Imprime um relatório ✓/✗ e devolve um código de saída (0 = tudo
essencial OK). Usado pelo instalador (teste de integridade) e por um atalho "Diagnóstico".
"""
from __future__ import annotations

import os
import sys
import socket
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desktop_config as cfg  # noqa: E402

# Bases ESSENCIAIS embarcadas no projeto (relativas à raiz do app). Se faltar, a geocodificação
# local / inteligência hidrográfica degradam — por isso são checadas.
BASES_ESSENCIAIS = [
    "data/brasil/ibge/derivadas/municipios.parquet",
    "data/brasil/ibge/derivadas/massas_dagua.parquet",
    "hidrografia_nacional.pkl.gz",
    "streamlit_app.py",
]
BASES_OPCIONAIS = [
    "data/brasil/ibge/derivadas/rios_nomeados_index.parquet",
    "amazonia_fluvial.pkl.gz",
    "snirh_rios.csv",
]


def _existe(rel: str):
    p = cfg.app_root() / rel
    try:
        if p.exists():
            return True, round(p.stat().st_size / (1024 ** 2), 1)
    except Exception:
        pass
    return False, 0.0


def _osrm_ok(url: str) -> bool:
    """Ping leve no motor local: uma rota curtíssima deve responder 'Ok'."""
    try:
        teste = url.rstrip("/") + "/route/v1/driving/-47.88,-15.79;-47.9,-15.8?overview=false"
        with urllib.request.urlopen(teste, timeout=5) as r:
            return b'"Ok"' in r.read(400)
    except Exception:
        return False


def executar(verbose: bool = True) -> int:
    paths = cfg.ensure_user_dirs()
    hw = cfg.detectar_hardware()
    conf = cfg.carregar_config_usuario()
    linhas, essenciais_ok = [], True

    linhas.append("OpenRotas Desktop — Diagnóstico")
    linhas.append("=" * 48)
    linhas.append("Hardware: %s núcleos, %s GB RAM, perfil '%s'" % (hw["cpus"], hw["ram_gb"], hw["perfil"]))
    linhas.append("Dados do usuário: %s" % cfg.user_data_dir())
    linhas.append("")
    linhas.append("Bases essenciais:")
    for rel in BASES_ESSENCIAIS:
        ok, mb = _existe(rel)
        essenciais_ok = essenciais_ok and ok
        linhas.append("  %s %s %s" % ("OK " if ok else "FALTA", rel, ("(%s MB)" % mb) if ok else ""))
    linhas.append("Bases opcionais:")
    for rel in BASES_OPCIONAIS:
        ok, mb = _existe(rel)
        linhas.append("  %s %s %s" % ("OK " if ok else " - ", rel, ("(%s MB)" % mb) if ok else ""))

    # Motor de rotas local (se configurado).
    osrm = conf.get("OSRM_URL")
    linhas.append("")
    if osrm:
        linhas.append("Motor de rotas local (OSRM_URL=%s): %s" % (osrm, "OK" if _osrm_ok(osrm) else "SEM RESPOSTA"))
    else:
        linhas.append("Motor de rotas local: não configurado (usa OSRM público/online).")

    # Diretórios persistentes graváveis.
    grav_ok = os.access(str(paths["cache"]), os.W_OK)
    linhas.append("Cache persistente gravável: %s (%s)" % ("OK" if grav_ok else "FALHA", paths["cache"]))

    linhas.append("")
    linhas.append("RESULTADO: %s" % ("tudo essencial OK ✓" if essenciais_ok and grav_ok
                                      else "há itens essenciais faltando ✗"))
    if verbose:
        print("\n".join(linhas))
    return 0 if (essenciais_ok and grav_ok) else 1


if __name__ == "__main__":
    raise SystemExit(executar())
