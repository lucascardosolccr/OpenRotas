# -*- coding: utf-8 -*-
"""OpenRotas Desktop — GERENTE do motor OSRM local (Etapa 3).

O desktop pode ter seu próprio motor de rotas, tornando o roteamento rápido e OFFLINE.
Em vez de reescrever o cliente de rotas (o app já fala OSRM por HTTP via OSRM_URL), este
módulo apenas GARANTE que exista um OSRM local no ar e devolve a URL dele — que o launcher
injeta como OSRM_URL. Assim o MESMO caminho de produção passa a usar o motor local.

Três modos (config em desktop.json → bloco "osrm"):
  • "off"      → não gerencia nada; usa o OSRM público/online (comportamento padrão).
  • "external" → assume que VOCÊ já subiu um OSRM em osrm.url (ex.: Docker rodando). Só valida.
  • "docker"   → o próprio desktop SOBE o OSRM via Docker, apontando para o grafo local
                 (osrm.graph_path), e o encerra ao fechar o app.

Decisão de engenharia (ver README, §9): usamos OSRM (C++), não um roteador em processo
(NetworkX/OSMnx), porque para a malha do Brasil inteiro o OSRM é ordens de grandeza mais
rápido e correto (turn restrictions, snapping, alternativas) — o benchmark comprova. Este
módulo é a integração "de 1ª classe": o software gerencia o ciclo de vida do seu motor.

Puro/defensivo: NUNCA levanta para o chamador; em qualquer falha, devolve status e deixa o
app cair no OSRM público (zero regressão). Stdlib apenas (sem dependências novas)."""
from __future__ import annotations

import os
import time
import socket
import logging
import subprocess
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger("openrotas.desktop.osrm")

URL_PADRAO = "http://localhost:5000"


@dataclass
class ResultadoMotor:
    url: str | None            # URL a usar como OSRM_URL (None → mantém o atual/público)
    modo: str                  # off | external | docker
    ativo: bool                # motor local respondeu ao health-check?
    gerenciado: bool = False   # True se ESTE processo subiu o OSRM (precisa encerrar depois)
    processo: object = field(default=None, repr=False)
    detalhe: str = ""


# ---------------------------------------------------------------------------
# Health-check — uma rota curtíssima deve voltar {"code":"Ok"}.
# ---------------------------------------------------------------------------
def health(url: str, timeout: float = 4.0) -> bool:
    if not url:
        return False
    try:
        teste = url.rstrip("/") + "/route/v1/driving/-47.88,-15.79;-47.90,-15.80?overview=false"
        with urllib.request.urlopen(teste, timeout=timeout) as r:
            return b'"Ok"' in r.read(400)
    except Exception:
        return False


def _porta_ocupada(host: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, porta)) == 0


def _esperar_health(url: str, timeout_s: float = 60.0) -> bool:
    ini = time.time()
    while time.time() - ini < timeout_s:
        if health(url, timeout=3.0):
            return True
        time.sleep(1.0)
    return False


# ---------------------------------------------------------------------------
# Docker — sobe o osrm-routed apontando para o grafo local.
# ---------------------------------------------------------------------------
def _docker_disponivel() -> bool:
    try:
        p = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, timeout=8)
        return p.returncode == 0
    except Exception:
        return False


def _subir_docker(cfg: dict) -> ResultadoMotor:
    graph = str(cfg.get("graph_path", "")).strip()
    porta = int(cfg.get("port", 5000))
    imagem = str(cfg.get("docker_image", "osrm/osrm-backend"))
    algoritmo = str(cfg.get("algorithm", "mld"))
    url = cfg.get("url") or ("http://localhost:%d" % porta)

    if not graph or not os.path.exists(graph):
        return ResultadoMotor(url=None, modo="docker", ativo=False,
                              detalhe="grafo não encontrado em graph_path: %r" % graph)
    if not _docker_disponivel():
        return ResultadoMotor(url=None, modo="docker", ativo=False,
                              detalhe="Docker não está disponível/rodando")
    if _porta_ocupada("localhost", porta):
        # Já tem algo na porta — provavelmente um OSRM que você já subiu. Reaproveita.
        ok = _esperar_health(url, timeout_s=8.0)
        return ResultadoMotor(url=url if ok else None, modo="docker", ativo=ok, gerenciado=False,
                              detalhe="porta %d já em uso; reaproveitando" % porta)

    graph_dir = os.path.dirname(os.path.abspath(graph))
    graph_base = os.path.basename(graph)
    # -v <dir>:/data  → referencia /data/<arquivo>.osrm dentro do container.
    cmd = ["docker", "run", "--rm", "-p", "%d:5000" % porta,
           "-v", "%s:/data" % graph_dir, imagem,
           "osrm-routed", "--algorithm", algoritmo, "-i", "0.0.0.0", "-p", "5000",
           "/data/%s" % graph_base]
    logger.info("[OSRM] subindo via Docker: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return ResultadoMotor(url=None, modo="docker", ativo=False,
                              detalhe="falha ao iniciar o Docker: %s" % e)
    if _esperar_health(url, timeout_s=float(cfg.get("start_timeout_s", 90))):
        return ResultadoMotor(url=url, modo="docker", ativo=True, gerenciado=True, processo=proc,
                              detalhe="OSRM local no ar (gerenciado)")
    # Não respondeu a tempo — encerra o que subimos e deixa cair no público.
    try:
        proc.terminate()
    except Exception:
        pass
    return ResultadoMotor(url=None, modo="docker", ativo=False,
                          detalhe="OSRM não respondeu ao health-check a tempo")


# ---------------------------------------------------------------------------
# API pública do módulo.
# ---------------------------------------------------------------------------
def resolver(cfg_osrm: dict | None, osrm_url_legado: str = "") -> ResultadoMotor:
    """Resolve qual URL de OSRM usar, conforme a config do desktop.
    `cfg_osrm` = bloco "osrm" do desktop.json (pode ser None).
    `osrm_url_legado` = valor plano "OSRM_URL" (compatibilidade — tratado como external)."""
    cfg = dict(cfg_osrm or {})
    modo = str(cfg.get("mode", "")).lower().strip()

    # Compat: OSRM_URL plano sem bloco "osrm" → external apontando pra ele.
    if not modo and osrm_url_legado:
        modo, cfg["url"] = "external", osrm_url_legado

    if modo in ("", "off", "none"):
        return ResultadoMotor(url=None, modo="off", ativo=False, detalhe="usando OSRM público/online")

    if modo == "external":
        url = cfg.get("url") or URL_PADRAO
        ok = health(url)
        return ResultadoMotor(url=url if ok else None, modo="external", ativo=ok,
                              detalhe="OSRM externo %s" % ("respondeu" if ok else "NÃO respondeu"))

    if modo == "docker":
        return _subir_docker(cfg)

    return ResultadoMotor(url=None, modo=modo, ativo=False, detalhe="modo desconhecido: %r" % modo)


def encerrar(res: ResultadoMotor) -> None:
    """Encerra o OSRM que ESTE processo subiu (modo docker gerenciado). No-op caso contrário."""
    if res and res.gerenciado and res.processo is not None:
        try:
            res.processo.terminate()
            logger.info("[OSRM] motor local gerenciado encerrado.")
        except Exception:
            logger.warning("[OSRM] falha ao encerrar o motor local.", exc_info=True)
