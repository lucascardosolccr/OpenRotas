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
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger("openrotas.desktop.osrm")

URL_PADRAO = "http://localhost:5000"


def _telemetria(evento: str, **campos) -> None:
    """Registra um evento no perfil de execução local (§42), se o módulo estiver disponível.
    Import defensivo (telemetria é opcional): osrm_manager continua stdlib-only e nunca quebra
    por causa disso."""
    try:
        import sys as _sys
        _tel = str(Path(__file__).resolve().parents[1] / "telemetry")
        if _tel not in _sys.path:
            _sys.path.insert(0, _tel)
        import exec_profile
        exec_profile.registrar(dict(campos, evento=evento, tipo="osrm"))
    except Exception:
        pass


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
    _t0 = time.perf_counter()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        _telemetria("docker_start", ok=False, detalhe="popen falhou")
        return ResultadoMotor(url=None, modo="docker", ativo=False,
                              detalhe="falha ao iniciar o Docker: %s" % e)
    if _esperar_health(url, timeout_s=float(cfg.get("start_timeout_s", 90))):
        _telemetria("docker_start", ok=True, ms=round((time.perf_counter() - _t0) * 1000.0, 1))
        return ResultadoMotor(url=url, modo="docker", ativo=True, gerenciado=True, processo=proc,
                              detalhe="OSRM local no ar (gerenciado)")
    _telemetria("docker_start", ok=False, ms=round((time.perf_counter() - _t0) * 1000.0, 1),
                detalhe="health-check timeout")
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


def _base_partes(url: str) -> str:
    """Normaliza uma URL de parte para o PREFIXO antes do número. Aceita '…part',
    '…part0', '…part00' etc. → devolve '…part' (sem dígitos finais)."""
    import re
    return re.sub(r"\d+$", "", url)


def _parte_ausente(exc: Exception) -> bool:
    """True se a exceção significa 'esta parte não existe' (fim das partes) — e NÃO um erro
    transitório de rede. Distinguir os dois evita concatenar um tar truncado e reportar sucesso."""
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (403, 404, 416)          # Release: asset inexistente
    if isinstance(exc, urllib.error.URLError):
        return isinstance(getattr(exc, "reason", None), FileNotFoundError)   # file:// ausente
    if isinstance(exc, FileNotFoundError):
        return True
    return False


def _baixar_partes(url: str, destino_tar) -> bool:
    """Baixa as partes sequenciais (…part00, …part01, …) e as concatena em `destino_tar`
    (Release publica o grafo em partes ≤1900 MB). Para quando a PRÓXIMA parte não existe
    (fim normal). Um erro transitório de rede no meio ABORTA e descarta o arquivo parcial —
    não é confundido com fim das partes. True só se baixou ao menos uma parte com sucesso e
    sem erro transitório. Nunca levanta."""
    base = _base_partes(url)
    destino_tar = Path(destino_tar)
    baixou, abortou = 0, False
    try:
        with open(destino_tar, "wb") as out:
            for i in range(0, 1000):
                parte_url = "%s%02d" % (base, i)
                try:
                    req = urllib.request.Request(parte_url, headers={"User-Agent": "OpenRotas-Desktop"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        while True:
                            bloco = r.read(1024 * 256)
                            if not bloco:
                                break
                            out.write(bloco)
                    baixou += 1
                    logger.info("[OSRM] parte %02d do grafo baixada.", i)
                except Exception as e:
                    if _parte_ausente(e):
                        break                       # fim das partes (índice inexistente)
                    logger.warning("[OSRM] erro ao baixar a parte %02d (transitório); abortando.", i, exc_info=True)
                    abortou = True
                    break
    except Exception:
        logger.warning("[OSRM] falha ao baixar partes do grafo.", exc_info=True)
        abortou = True
    if abortou or not baixou:
        try:
            destino_tar.unlink()
        except Exception:
            pass
        return False
    return True


def garantir_grafo(cfg_osrm: dict | None, destino_dir) -> str | None:
    """[GRAFO COMO PRODUTO] Garante que o grafo OSRM do Brasil exista localmente e devolve o
    caminho do arquivo .osrm base. Ordem:
      1. se graph_path já existe → usa;
      2. se já foi provisionado antes em destino_dir → usa;
      3. se há graph_url (ex.: Release do GitHub) → BAIXA o .tar.gz UMA VEZ e extrai em destino_dir.
    É assim que o grafo "vem com o produto" sem inchar o instalador: um download único no 1º uso,
    guardado no perfil do usuário (sobrevive a atualizações do app). Defensivo: nunca levanta —
    em falha devolve o graph_path (possivelmente ausente) e o app cai no OSRM público.
    Download grande é esperado (vários GB); é feito só uma vez."""
    cfg = dict(cfg_osrm or {})
    gp = str(cfg.get("graph_path", "")).strip()
    if gp and os.path.exists(gp):
        return gp
    try:
        destino = Path(destino_dir)
        destino.mkdir(parents=True, exist_ok=True)
        ja = next(destino.glob("*.osrm"), None)       # já provisionado antes?
        if ja is not None:
            return str(ja)
        url = str(cfg.get("graph_url", "")).strip()
        if not url:
            return gp or None
        import tarfile, shutil
        tmp = destino / "_grafo_download.tar.gz"
        staging = destino / "_staging"
        try:
            if ".part" in url:
                # Grafo publicado em PARTES (Release) → baixa todas e concatena antes de extrair.
                logger.info("[OSRM] provisionando grafo em partes a partir de %s", url)
                if not _baixar_partes(url, tmp):
                    return gp or None
            else:
                logger.info("[OSRM] provisionando grafo (download único) de %s", url)
                urllib.request.urlretrieve(url, tmp)
            # Extrai numa área de STAGING; só promove ao destino se der certo — evita deixar
            # um .osrm PARCIAL que o próximo run confundiria com 'já provisionado'.
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tmp, "r:gz") as t:
                try:
                    t.extractall(staging, filter="data")   # py3.12+: extração segura
                except TypeError:
                    t.extractall(staging)                  # fallback versões antigas
            cand = next(staging.rglob("*.osrm"), None)
            if cand is None:
                logger.warning("[OSRM] arquivo .osrm não encontrado no pacote; descartando.")
                return gp or None
            # move todos os artefatos do grafo (*.osrm*) para o destino final
            for f in cand.parent.glob("brazil-latest.osrm*"):
                destino_f = destino / f.name
                if destino_f.exists():
                    destino_f.unlink()
                shutil.move(str(f), str(destino_f))
            final = next(destino.glob("*.osrm"), None)
            return str(final) if final else (gp or None)
        finally:
            for p in (tmp,):
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        logger.warning("[OSRM] falha ao provisionar o grafo.", exc_info=True)
        return gp or None


def encerrar(res: ResultadoMotor) -> None:
    """Encerra o OSRM que ESTE processo subiu (modo docker gerenciado). No-op caso contrário."""
    if res and res.gerenciado and res.processo is not None:
        try:
            res.processo.terminate()
            logger.info("[OSRM] motor local gerenciado encerrado.")
        except Exception:
            logger.warning("[OSRM] falha ao encerrar o motor local.", exc_info=True)
