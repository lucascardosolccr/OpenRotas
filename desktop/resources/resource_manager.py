# -*- coding: utf-8 -*-
"""OpenRotas Desktop — GERENCIADOR DE RECURSOS (Resource Manager) — §3/§4/§17/§18/§19/§24.

Uma única superfície que SABE, para cada recurso do software:
  • se está instalado / ausente / corrompido;
  • se é obrigatório ou opcional;
  • o tamanho, a origem e (quando aplicável) a URL para baixar;
  • qual módulo o utiliza.
E age: verificar integridade, provisionar (baixar) e reparar.

Não reimplementa nada: COMPÕE a camada de dados (local_data) e o gerente do motor (osrm_manager).
Dois tipos de recurso:
  - "embarcado": vem no instalador/bundle (bases IBGE/hidrografia). Ausente/corrompido → reparo
    = reinstalar o app (não dá para baixar avulso).
  - "provisionável": grande e opcional, baixado pelo próprio software (grafo OSRM do Brasil)
    a partir de uma URL (Release do GitHub). Reparo = (re)baixar.

Defensivo: nunca levanta para o chamador; tudo degrada com status textual. Stdlib + os módulos
do próprio desktop (que, por sua vez, usam pandas/pyarrow já presentes)."""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(_AQUI.parent / "app"))
sys.path.insert(0, str(_AQUI.parent))
sys.path.insert(0, str(_AQUI.parent / "data_local"))

logger = logging.getLogger("openrotas.desktop.resources")

# Estados possíveis (§24).
OK, AUSENTE, CORROMPIDO, OPCIONAL_AUSENTE = "instalado", "ausente", "corrompido", "opcional-ausente"


def _registry():
    import desktop_config as cfg
    import local_data
    return cfg, local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _modulo_de(chave: str) -> str:
    """Qual parte do software usa cada recurso (§4 'quais recursos são usados por cada módulo')."""
    return {
        "municipios": "Geocodificação / Decisão",
        "massas_dagua": "Inteligência hidrográfica",
        "hidrografia_nacional": "Inteligência hidrográfica",
        "rios_nomeados": "Hidrografia (rios nomeados)",
        "amazonia_fluvial": "Rede fluvial amazônica",
        "snirh_rios": "Hidrografia (SNIRH)",
        "osrm_brasil": "Roteamento local / offline",
    }.get(chave, "—")


def status(osrm_cfg: dict | None = None) -> list:
    """Lista o estado de cada recurso. osrm_cfg (bloco 'osrm' do desktop.json) informa a URL de
    provisionamento do grafo, se houver."""
    cfg, reg = _registry()
    osrm_cfg = dict(osrm_cfg or {})
    import local_data
    linhas = []
    for d in local_data.CATALOGO:
        existe = reg.existe(d.chave)
        provisionavel = (d.formato == "osrm")
        if existe:
            estado = OK
        elif d.essencial:
            estado = AUSENTE
        else:
            estado = OPCIONAL_AUSENTE
        info = {
            "chave": d.chave,
            "descricao": d.descricao,
            "modulo": _modulo_de(d.chave),
            "obrigatorio": bool(d.essencial),
            "tipo": "provisionável" if provisionavel else "embarcado",
            "instalado": bool(existe),
            "estado": estado,
            "caminho": str(reg.caminho(d.chave)),
        }
        if existe:
            a = reg.assinatura(d.chave)
            info["mb"] = round(a["bytes"] / (1024 ** 2), 1)
            info["hash12"] = a["hash12"]
        elif provisionavel:
            info["graph_url"] = str(osrm_cfg.get("graph_url", "")) or None
        linhas.append(info)
    return linhas


def verificar() -> dict:
    """Integridade dos recursos PRESENTES (hash parcial via local_data.assinatura). Também aponta
    os obrigatórios ausentes. Devolve {ok: bool, problemas: [...], faltam_obrigatorios: [...]}."""
    cfg, reg = _registry()
    problemas, faltam = [], []
    import local_data
    for d in local_data.CATALOGO:
        if reg.existe(d.chave):
            a = reg.assinatura(d.chave)
            if not a["existe"] or a["bytes"] <= 0:
                problemas.append({"chave": d.chave, "motivo": CORROMPIDO})
        elif d.essencial:
            faltam.append(d.chave)
    return {"ok": not problemas and not faltam, "problemas": problemas, "faltam_obrigatorios": faltam}


def provisionar_grafo(osrm_cfg: dict | None = None) -> dict:
    """Baixa/garante o grafo OSRM do Brasil (recurso provisionável) para o perfil do usuário,
    usando osrm_manager.garantir_grafo. Devolve {ok, caminho, detalhe}. Não levanta."""
    cfg, _ = _registry()
    try:
        from engines import osrm_manager as osrm
        destino = cfg.user_data_dir() / "data_local"
        caminho = osrm.garantir_grafo(dict(osrm_cfg or {}), destino)
        return {"ok": bool(caminho), "caminho": caminho,
                "detalhe": "grafo pronto" if caminho else "sem graph_url/graph_path — nada a baixar"}
    except Exception as e:
        logger.warning("[RECURSOS] provisionamento do grafo falhou.", exc_info=True)
        return {"ok": False, "caminho": None, "detalhe": "erro: %s" % e}


def reparar(osrm_cfg: dict | None = None) -> list:
    """Diagnóstico de reparo (§18): para cada problema, diz a AÇÃO. Reparo de provisionável =
    (re)baixar automaticamente; de embarcado ausente = reinstalar o app (não há download avulso)."""
    v = verificar()
    acoes = []
    for p in v["problemas"]:
        acoes.append({"chave": p["chave"], "problema": CORROMPIDO,
                      "acao": "reinstalar o aplicativo (recurso embarcado corrompido)"})
    for ch in v["faltam_obrigatorios"]:
        acoes.append({"chave": ch, "problema": AUSENTE,
                      "acao": "reinstalar o aplicativo (base obrigatória ausente)"})
    # grafo opcional ausente mas com URL → pode baixar
    cfg, reg = _registry()
    if not reg.existe("osrm_brasil") and str((osrm_cfg or {}).get("graph_url", "")).strip():
        r = provisionar_grafo(osrm_cfg)
        acoes.append({"chave": "osrm_brasil", "problema": OPCIONAL_AUSENTE,
                      "acao": "baixado automaticamente" if r["ok"] else "falha ao baixar: %s" % r["detalhe"]})
    return acoes


def resumo_ambiente(osrm_cfg: dict | None = None) -> str:
    """Texto estilo 'Status do ambiente' (§17/§24): ✓ instalado, ! opcional ausente, ✗ obrigatório
    ausente/corrompido. Para o diagnóstico e a futura Central de Recursos na UI."""
    linhas = ["Recursos do software:"]
    for r in status(osrm_cfg):
        if r["estado"] == OK:
            marca = "✓"
        elif r["estado"] == OPCIONAL_AUSENTE:
            marca = "○"
        else:
            marca = "✗"
        tam = (" (%s MB)" % r["mb"]) if r.get("mb") else ""
        obr = "obrigatório" if r["obrigatorio"] else "opcional"
        linhas.append("  %s %-22s %-13s %-12s %s%s" % (marca, r["chave"], r["estado"], obr, r["modulo"], tam))
    return "\n".join(linhas)


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "status"
    if cmd in ("status", "resumo"):
        print(resumo_ambiente())
        return 0
    if cmd == "verificar":
        v = verificar()
        print("integridade OK" if v["ok"] else "problemas: %s | faltam: %s" % (v["problemas"], v["faltam_obrigatorios"]))
        return 0 if v["ok"] else 1
    print("uso: resource_manager.py [status|verificar]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
