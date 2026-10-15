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
# Nome fixo do container que ESTE app gerencia — permite parada/limpeza confiáveis e evita
# conflito de nome após um encerramento abrupto (crash/queda de energia).
CONTAINER_OSRM = "openrotas-osrm"


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
    nome: str = ""             # nome do container Docker (quando gerenciado), p/ parada confiável


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


# ---------------------------------------------------------------------------
# Motor NATIVO embarcado (SEM Docker) — osrm-routed empacotado no próprio app.
# É o caminho turnkey: o usuário clica "baixar o mapa" e o app serve o grafo
# localmente, só enquanto está aberto (encerra ao fechar). Sem servidor 24h,
# sem Docker, sem PC ligado. Se o binário/grafo faltar, cai no público.
# ---------------------------------------------------------------------------
def _nome_binario() -> str:
    return "osrm-routed.exe" if os.name == "nt" else "osrm-routed"


def _bin_osrm_routed() -> str | None:
    """Localiza o binário osrm-routed EMBARCADO no app (sem Docker). Procura, nesta ordem:
    a env OSRM_ROUTED_BIN (override), engines/bin ao lado do app empacotado e desktop/engines/bin
    (dev). Devolve o caminho ou None. Nunca levanta."""
    nome = _nome_binario()
    cands = []
    env = os.environ.get("OSRM_ROUTED_BIN")
    if env:
        cands.append(Path(env))
    try:
        import desktop_config as _dc  # type: ignore
        cands.append(_dc.app_root() / "engines" / "bin" / nome)
    except Exception:
        pass
    cands.append(Path(__file__).resolve().parent / "bin" / nome)       # dev: desktop/engines/bin
    for c in cands:
        try:
            if c and Path(c).exists():
                return str(c)
        except Exception:
            pass
    return None


def motor_nativo_disponivel() -> bool:
    """True se há um binário osrm-routed embarcado (serve o grafo local SEM Docker)."""
    return _bin_osrm_routed() is not None


def _encerrar_processo(proc) -> None:
    """Encerra um processo filho (terminate → wait → kill) de forma 100% defensiva."""
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _subir_local(cfg: dict) -> ResultadoMotor:
    """Sobe o osrm-routed EMBARCADO (sem Docker) apontando para o grafo local, e gerencia seu
    ciclo de vida (encerra ao fechar o app). Fallback seguro: se faltar binário/grafo, se a porta
    tiver outro serviço, ou se não subir a tempo, devolve inativo e o app cai no OSRM público
    (zero regressão). Nunca levanta."""
    graph = str(cfg.get("graph_path", "")).strip()
    porta = int(cfg.get("port", 5000))
    algoritmo = str(cfg.get("algorithm", "mld"))
    url = cfg.get("url") or ("http://127.0.0.1:%d" % porta)

    # O grafo é VÁLIDO se o caminho-base existir como arquivo (formatos antigos) OU se a FAMÍLIA
    # '<base>.osrm.*' estiver presente (OSRM 5.x MLD não gera um arquivo-base literal). osrm-routed
    # recebe o caminho-base (sem sufixo) e carrega a família.
    _gbase = Path(graph) if graph else None
    _grafo_ok = bool(graph) and (os.path.exists(graph)
                                 or (_gbase is not None and any(_gbase.parent.glob(_gbase.name + ".*"))))
    if not _grafo_ok:
        return ResultadoMotor(url=None, modo="local", ativo=False,
                              detalhe="grafo não encontrado em graph_path: %r" % graph)
    binario = _bin_osrm_routed()
    if not binario:
        return ResultadoMotor(url=None, modo="local", ativo=False,
                              detalhe="binário osrm-routed embarcado não encontrado")
    if _porta_ocupada("127.0.0.1", porta):
        ok = _esperar_health(url, timeout_s=8.0)
        return ResultadoMotor(url=url if ok else None, modo="local", ativo=ok, gerenciado=False,
                              detalhe="porta %d já em uso; reaproveitando" % porta)

    bin_dir = os.path.dirname(os.path.abspath(binario))
    env = dict(os.environ)
    # As DLLs de runtime (TBB/bz2 no Windows) ficam AO LADO do binário → garante que carreguem.
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    cmd = [binario, "--algorithm", algoritmo, "-i", "127.0.0.1", "-p", str(porta), graph]
    logger.info("[OSRM] subindo motor nativo embarcado (sem Docker): %s", " ".join(cmd))
    _t0 = time.perf_counter()
    try:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # sem janela de console no Windows
        proc = subprocess.Popen(cmd, cwd=bin_dir, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=creation)
    except Exception as e:
        _telemetria("local_start", ok=False, detalhe="popen falhou")
        return ResultadoMotor(url=None, modo="local", ativo=False,
                              detalhe="falha ao iniciar o motor nativo: %s" % e)
    if _esperar_health(url, timeout_s=float(cfg.get("start_timeout_s", 90))):
        _telemetria("local_start", ok=True, ms=round((time.perf_counter() - _t0) * 1000.0, 1))
        return ResultadoMotor(url=url, modo="local", ativo=True, gerenciado=True, processo=proc,
                              detalhe="motor nativo embarcado no ar (sem Docker)")
    _telemetria("local_start", ok=False, ms=round((time.perf_counter() - _t0) * 1000.0, 1),
                detalhe="health-check timeout")
    _encerrar_processo(proc)
    return ResultadoMotor(url=None, modo="local", ativo=False,
                          detalhe="motor nativo não respondeu ao health-check a tempo")


def _subir_docker(cfg: dict) -> ResultadoMotor:
    graph = str(cfg.get("graph_path", "")).strip()
    porta = int(cfg.get("port", 5000))
    imagem = str(cfg.get("docker_image", "osrm/osrm-backend"))
    algoritmo = str(cfg.get("algorithm", "mld"))
    url = cfg.get("url") or ("http://localhost:%d" % porta)

    # Grafo válido = caminho-base existe OU a família '<base>.osrm.*' está presente (ver _subir_local).
    _gbase = Path(graph) if graph else None
    _grafo_ok = bool(graph) and (os.path.exists(graph)
                                 or (_gbase is not None and any(_gbase.parent.glob(_gbase.name + ".*"))))
    if not _grafo_ok:
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

    # Remove um container órfão nosso de uma execução anterior (crash/queda) para não dar
    # "name already in use" nem segurar a porta. Best-effort.
    _remover_container(CONTAINER_OSRM)

    graph_dir = os.path.dirname(os.path.abspath(graph))
    graph_base = os.path.basename(graph)
    # -v <dir>:/data  → referencia /data/<arquivo>.osrm dentro do container. --name p/ parada
    # confiável depois (docker stop <nome>), e --rm para o container sumir ao parar.
    cmd = ["docker", "run", "--rm", "--name", CONTAINER_OSRM, "-p", "%d:5000" % porta,
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
                              nome=CONTAINER_OSRM, detalhe="OSRM local no ar (gerenciado)")
    _telemetria("docker_start", ok=False, ms=round((time.perf_counter() - _t0) * 1000.0, 1),
                detalhe="health-check timeout")
    # Não respondeu a tempo — para o container (confiável) e deixa cair no público.
    _remover_container(CONTAINER_OSRM)
    try:
        proc.terminate()
    except Exception:
        pass
    return ResultadoMotor(url=None, modo="docker", ativo=False,
                          detalhe="OSRM não respondeu ao health-check a tempo")


def _remover_container(nome: str) -> bool:
    """Para/remove um container Docker pelo nome, se existir. Best-effort; nunca levanta.
    Devolve True se o comando docker executou com sucesso (returncode 0)."""
    if not nome:
        return False
    try:
        p = subprocess.run(["docker", "rm", "-f", nome], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
        return p.returncode == 0
    except Exception:
        return False


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

    if modo == "local":
        return _subir_local(cfg)

    if modo == "docker":
        return _subir_docker(cfg)

    if modo == "auto":
        # O modo MAIS INTELIGENTE (turnkey, sem configuração): tenta primeiro o motor NATIVO
        # embarcado (sem Docker); se não houver binário/não subir, tenta Docker; senão, cai no
        # OSRM público. Assim o usuário só precisa baixar o mapa — o resto é automático.
        if _bin_osrm_routed():
            r = _subir_local(cfg)
            if r.ativo:
                return r
        if _docker_disponivel():
            r = _subir_docker(cfg)
            if r.ativo:
                return r
        return ResultadoMotor(url=None, modo="auto", ativo=False,
                              detalhe="nenhum motor local disponível (nativo/Docker); usando OSRM público")

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


def _emitir(progresso, **campos) -> None:
    """Chama o callback de progresso (se houver) de forma 100% defensiva — um progresso que
    levanta NUNCA pode abortar/corromper um download de vários GB."""
    if progresso is None:
        return
    try:
        progresso(dict(campos))
    except Exception:
        pass


def _ctx_ssl():
    """Contexto TLS com CA bundle confiável (certifi) — mesmo do downloader. Evita que o probe
    falhe por verificação de certificado no app empacotado. None em último caso."""
    try:
        try:
            from resources import downloader as _dl
        except Exception:
            import downloader as _dl
        return _dl.contexto_ssl()
    except Exception:
        return None


def _parte_existe(url: str, timeout: int = 30) -> bool:
    """Probe barato: a parte existe? (pede 1 byte via Range). False em 403/404/416 (fim das
    partes); True se respondeu 200/206. Em erro transitório, assume que EXISTE (não trata fim)."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenRotas-Desktop/1.0",
            "Range": "bytes=0-0"})
        _ctx = _ctx_ssl()
        with (urllib.request.urlopen(req, timeout=timeout, context=_ctx) if _ctx
              else urllib.request.urlopen(req, timeout=timeout)):
            return True
    except Exception as e:
        if _parte_ausente(e):
            return False
        return True


def _tamanhos_esperados(url: str) -> dict:
    """Consulta a API do GitHub os TAMANHOS REAIS (bytes) dos assets da Release, para conferir a
    integridade de cada parte baixada. Uma parte adulterada no caminho (conexão/antivírus) fica
    com tamanho != o publicado — é assim que detectamos corrupção sem precisar de sha256 externo.
    Best-effort: devolve {} se não der (então o download segue sem a conferência, como antes)."""
    try:
        import json as _json, re as _re
        m = _re.match(r"https?://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/", url)
        if not m:
            return {}
        owner, repo, tag = m.group(1), m.group(2), m.group(3)
        api = "https://api.github.com/repos/%s/%s/releases/tags/%s" % (owner, repo, tag)
        req = urllib.request.Request(api, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenRotas-Desktop/1.0",
            "Accept": "application/vnd.github+json"})
        _ctx = _ctx_ssl()
        with (urllib.request.urlopen(req, timeout=30, context=_ctx) if _ctx
              else urllib.request.urlopen(req, timeout=30)) as r:
            dados = _json.loads(r.read().decode("utf-8", "replace"))
        return {a.get("name"): int(a.get("size") or 0) for a in (dados.get("assets") or [])}
    except Exception:
        logger.info("[OSRM] não consegui obter os tamanhos esperados das partes (seguindo sem conferência).",
                    exc_info=True)
        return {}


def _baixar_partes(url: str, destino_tar, progresso=None, sha256: str = "") -> bool:
    """Baixa as partes sequenciais (…part00, …part01, …) e as concatena em `destino_tar`
    (Release publica o grafo em partes). Cada parte usa o DOWNLOADER ROBUSTO (retomada por Range,
    velocidade/ETA, retry com backoff) — se a conexão cair, retoma de onde parou. Para quando a
    PRÓXIMA parte não existe (fim normal, detectado por probe). Com `sha256`, valida o tar
    concatenado ao final (§20). True só se concatenou ao menos uma parte íntegra. Nunca levanta."""
    base = _base_partes(url)
    destino_tar = Path(destino_tar)
    parts_tmp = []
    abortou = False
    try:
        import sys as _sys
        _res = str(Path(__file__).resolve().parents[1] / "resources")
        if _res not in _sys.path:
            _sys.path.insert(0, _res)
        import downloader
    except Exception:
        downloader = None
    try:
        for i in range(0, 1000):
            parte_url = "%s%02d" % (base, i)
            tmp_i = destino_tar.with_suffix(destino_tar.suffix + (".p%02d" % i))

            # RETOMADA ENTRE CLIQUES: o downloader só renomeia para o nome FINAL da parte quando a
            # transferência fecha por completo (ver a checagem de EOF precoce no downloader), então
            # uma parte já presente é íntegra — reaproveita em vez de rebaixar ~2 GB. Assim um
            # download de ~5 GB numa conexão instável conclui ao longo de vários cliques.
            if tmp_i.exists() and tmp_i.stat().st_size > 0:
                parts_tmp.append(tmp_i)
                _emitir(progresso, fase="baixando", parte=i, parte_concluida=True)
                logger.info("[OSRM] parte %02d já baixada — reaproveitando.", i)
                continue

            def _prog(ev, _i=i):
                _emitir(progresso, fase="baixando", parte=_i, bytes=ev.get("baixado"),
                        total_parte=ev.get("total"), velocidade_bps=ev.get("velocidade_bps"),
                        eta_s=ev.get("eta_s"), pct_parte=ev.get("pct"))

            if downloader is not None:
                r = downloader.baixar(parte_url, tmp_i, progresso=_prog, tentativas=4, timeout=120)
                if not r.get("ok"):
                    _motivo = r.get("detalhe") or ("falha ao baixar a parte %02d" % i)
                    # fim normal (parte inexistente) ou falha real?
                    if not _parte_existe(parte_url):
                        # 'parte inexistente' é fim normal SÓ se já baixamos alguma. Se NEM a 1ª
                        # parte existe, NÃO é fim: a origem está inacessível (HTTP 403/404 — proxy,
                        # firewall, antivírus ou rate-limit do GitHub bloqueando o download). Surface.
                        if not parts_tmp:
                            _emitir(progresso, fase="erro", parte=i,
                                    detalhe=("a 1ª parte do mapa não ficou acessível (HTTP 403/404): "
                                             "rede/proxy/firewall/antivírus pode estar bloqueando o "
                                             "download do GitHub. Detalhe: %s" % _motivo))
                            abortou = True
                        break
                    logger.warning("[OSRM] parte %02d falhou de modo persistente: %s", i, _motivo)
                    # Surfacing: manda o MOTIVO REAL para a UI (status da Central de Dados) em vez da
                    # mensagem genérica — sem isso, rede/TLS/antivírus viram só "verifique conexão".
                    _emitir(progresso, fase="erro", parte=i, detalhe=_motivo)
                    abortou = True
                    break
            else:
                # fallback stdlib (sem retomada) — mantém o comportamento mínimo.
                try:
                    req = urllib.request.Request(parte_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenRotas-Desktop/1.0"})
                    _ctx = _ctx_ssl()
                    _abre = (urllib.request.urlopen(req, timeout=120, context=_ctx) if _ctx
                             else urllib.request.urlopen(req, timeout=120))
                    with _abre as resp, open(tmp_i, "wb") as out:
                        while True:
                            b = resp.read(1024 * 256)
                            if not b:
                                break
                            out.write(b)
                except Exception as e:
                    if _parte_ausente(e):
                        if not parts_tmp:
                            _emitir(progresso, fase="erro", parte=i,
                                    detalhe=("a 1ª parte do mapa não ficou acessível (HTTP 403/404): "
                                             "rede/proxy/firewall/antivírus pode estar bloqueando o "
                                             "download do GitHub. Detalhe: %s: %s" % (type(e).__name__, e)))
                            abortou = True
                        break
                    _emitir(progresso, fase="erro", parte=i, detalhe="%s: %s" % (type(e).__name__, e))
                    abortou = True
                    break
            parts_tmp.append(tmp_i)
            _emitir(progresso, fase="baixando", parte=i, parte_concluida=True)
            logger.info("[OSRM] parte %02d do grafo pronta.", i)
        # INTEGRIDADE POR PARTE (correção do "pacote sem .osrm"): confere o TAMANHO de cada parte
        # contra o tamanho REAL publicado no GitHub. Uma parte adulterada no caminho
        # (conexão/antivírus) tem tamanho != esperado — antes passava em silêncio e corrompia o
        # grafo. Agora apaga a parte ruim (mantém as boas para retomar) e aborta com causa precisa.
        if not abortou and parts_tmp:
            esperados = _tamanhos_esperados(url)
            if esperados:
                base_nome = base.rsplit("/", 1)[-1]        # ex.: brazil-osrm-mld.tar.gz.part
                for idx, tmp_i in enumerate(parts_tmp):
                    nome = "%s%02d" % (base_nome, idx)
                    exp = esperados.get(nome)
                    try:
                        real = tmp_i.stat().st_size
                    except Exception:
                        real = -1
                    if exp and real != exp:
                        logger.warning("[OSRM] parte %02d corrompida: %s de %s bytes — descartando.",
                                       idx, real, exp)
                        try:
                            tmp_i.unlink()
                        except Exception:
                            pass
                        _emitir(progresso, fase="erro", parte=idx,
                                detalhe=("parte %02d veio corrompida (%s de %s bytes): a conexão/antivírus "
                                         "alterou o download. Clique em 'Baixar o mapa' de novo para rebaixar "
                                         "só essa parte; se repetir, use 'Importar mapa de uma pasta…' (baixe "
                                         "as partes pelo navegador)." % (idx, real, exp)))
                        abortou = True
                        break
        if not abortou and parts_tmp:
            _emitir(progresso, fase="concatenando", partes=len(parts_tmp))
            with open(destino_tar, "wb") as out:
                for tmp_i in parts_tmp:
                    with open(tmp_i, "rb") as f:
                        while True:
                            b = f.read(1024 * 1024)
                            if not b:
                                break
                            out.write(b)
            if sha256:
                import hashlib
                h = hashlib.sha256()
                with open(destino_tar, "rb") as f:
                    for b in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(b)
                if h.hexdigest().lower() != str(sha256).lower():
                    logger.warning("[OSRM] sha256 do grafo concatenado não confere — descartando.")
                    _emitir(progresso, fase="erro", detalhe="verificação de integridade (sha256) falhou")
                    abortou = True
    except Exception as e:
        logger.warning("[OSRM] falha ao baixar/concatenar partes do grafo.", exc_info=True)
        _emitir(progresso, fase="erro", detalhe="%s: %s" % (type(e).__name__, e))
        abortou = True
    if abortou or not parts_tmp:
        # NÃO apaga as partes já baixadas: ficam em disco para o PRÓXIMO clique RETOMAR de onde
        # parou (só o .tar.gz concatenado, que ficou incompleto, é descartado).
        try:
            destino_tar.unlink()
        except Exception:
            pass
        return False
    # Sucesso: o tar concatenado está completo → agora sim libera as partes p/ recuperar espaço.
    for tmp_i in parts_tmp:
        try:
            tmp_i.unlink()
        except Exception:
            pass
    return True


def _base_osrm_em(pasta) -> "Path | None":
    """Caminho-BASE do grafo OSRM dentro de `pasta` (ex.: <pasta>/brazil-latest.osrm), ou None.

    CAUSA RAIZ do 'pacote do grafo sem arquivo .osrm': o OSRM 5.x (MLD) NÃO cria um arquivo
    chamado exatamente '<base>.osrm' — gera só a FAMÍLIA '<base>.osrm.cells', '.mldgr',
    '.partition', '.cell_metrics', '.geometry', etc. O osrm-routed recebe o caminho-BASE
    (sem sufixo) e carrega a família. Procurar um '*.osrm' literal falhava em TODO download,
    mesmo íntegro. Aqui aceitamos tanto um '*.osrm' avulso (compat com formatos antigos que o
    geram) quanto a família '*.osrm.*', e devolvemos o caminho-base derivado. Nunca levanta."""
    try:
        base = Path(pasta)
        if not base.is_dir():
            return None
        avulso = next(base.rglob("*.osrm"), None)       # compat: formatos que geram o arquivo-base
        if avulso is not None:
            return avulso
        fam = next(base.rglob("*.osrm.*"), None)         # OSRM 5.x MLD: só a família '<base>.osrm.*'
        if fam is not None:
            nome = fam.name
            corte = nome.find(".osrm")
            if corte >= 0:
                return fam.parent / nome[:corte + len(".osrm")]
    except Exception:
        pass
    return None


def autoligar_se_tem_grafo(modo, *pastas) -> str:
    """Decisão TURNKEY do modo OSRM no boot. Se `modo` está DESLIGADO ('off'/vazio/'none') mas há
    um grafo presente em ALGUMA das `pastas` (perfil do usuário e/ou bundle embarcado), devolve
    'auto' — liga o roteamento LOCAL automaticamente. Senão, devolve o modo recebido inalterado.
    Assim um mapa já baixado nunca fica ocioso com as rotas indo para o OSRM público. Nunca levanta."""
    m = str(modo or "").lower().strip()
    if m in ("", "off", "none"):
        for p in pastas:
            try:
                if p is not None and _base_osrm_em(p) is not None:
                    return "auto"
            except Exception:
                pass
    return m or "off"


def garantir_grafo(cfg_osrm: dict | None, destino_dir, progresso=None) -> str | None:
    """[GRAFO COMO PRODUTO] Garante que o grafo OSRM do Brasil exista localmente e devolve o
    caminho do arquivo .osrm base. Ordem:
      1. se graph_path já existe → usa;
      2. se já foi provisionado antes em destino_dir → usa;
      3. se há graph_url (ex.: Release do GitHub) → BAIXA o .tar.gz UMA VEZ e extrai em destino_dir.
    É assim que o grafo "vem com o produto" sem inchar o instalador: um download único no 1º uso,
    guardado no perfil do usuário (sobrevive a atualizações do app). `progresso` (opcional):
    callback de andamento repassado ao downloader e às fases de extração — a Central de Dados o
    usa para a barra de progresso. Defensivo: nunca levanta — em falha devolve o graph_path
    (possivelmente ausente) e o app cai no OSRM público. Download grande é esperado (vários GB);
    é feito só uma vez."""
    cfg = dict(cfg_osrm or {})
    gp = str(cfg.get("graph_path", "")).strip()
    if gp and os.path.exists(gp):
        _emitir(progresso, fase="pronto", caminho=gp)
        return gp
    try:
        destino = Path(destino_dir)
        destino.mkdir(parents=True, exist_ok=True)
        ja = _base_osrm_em(destino)                    # já provisionado antes? (base ou família)
        if ja is not None:
            _emitir(progresso, fase="pronto", caminho=str(ja))
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
                _sha = str(cfg.get("graph_sha256", "") or "").strip()
                if not _baixar_partes(url, tmp, progresso=progresso, sha256=_sha):
                    return gp or None
            else:
                logger.info("[OSRM] provisionando grafo (download único) de %s", url)
                _emitir(progresso, fase="baixando", bytes=0)
                _req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpenRotas-Desktop/1.0"})
                _ctx = _ctx_ssl()
                _abre = (urllib.request.urlopen(_req, timeout=120, context=_ctx) if _ctx
                         else urllib.request.urlopen(_req, timeout=120))
                with _abre as _resp, open(tmp, "wb") as _out:
                    while True:
                        _b = _resp.read(1024 * 256)
                        if not _b:
                            break
                        _out.write(_b)
            _emitir(progresso, fase="extraindo")
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
            cand = _base_osrm_em(staging)
            if cand is None:
                logger.warning("[OSRM] grafo OSRM (arquivos .osrm/.osrm.*) não encontrado no pacote; descartando.")
                _emitir(progresso, fase="erro",
                        detalhe="pacote do grafo não contém os arquivos do grafo OSRM (.osrm.*)")
                return gp or None
            # move todos os artefatos do grafo para o destino final. O padrão é DERIVADO do
            # arquivo base encontrado (cand.name == "<base>.osrm") — não um nome fixo — para
            # funcionar se o grafo for publicado com outro nome-base.
            for f in cand.parent.glob(cand.name + "*"):
                destino_f = destino / f.name
                if destino_f.exists():
                    destino_f.unlink()
                shutil.move(str(f), str(destino_f))
            final = _base_osrm_em(destino)
            return str(final) if final else (gp or None)
        finally:
            for p in (tmp,):
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            shutil.rmtree(staging, ignore_errors=True)
    except Exception as e:
        logger.warning("[OSRM] falha ao provisionar o grafo.", exc_info=True)
        _emitir(progresso, fase="erro", detalhe="%s: %s" % (type(e).__name__, e))
        return gp or None


def instalar_grafo_de_partes_locais(pasta, destino_dir, progresso=None) -> str | None:
    """INSTALAÇÃO OFFLINE a partir de arquivos JÁ BAIXADOS (pelo navegador, p.ex.). Procura em
    `pasta` os pedaços 'brazil-osrm-mld.tar.gz.part*' (ou um '.tar.gz' único), concatena na ordem,
    extrai e promove para `destino_dir` — SEM rede. É o caminho garantido quando o download dentro
    do app falha mas o navegador baixa normal. Devolve o caminho do .osrm, ou None. Não levanta."""
    import tarfile, shutil
    try:
        p = Path(pasta)
        if not p.is_dir():
            _emitir(progresso, fase="erro", detalhe="pasta inválida: %s" % pasta)
            return None
        partes = sorted(p.glob("brazil-osrm-mld.tar.gz.part*"))
        unico = sorted(p.glob("*.tar.gz"))
        if not partes and not unico:
            _emitir(progresso, fase="erro",
                    detalhe=("nenhum arquivo do mapa encontrado na pasta (esperado "
                             "'brazil-osrm-mld.tar.gz.part00', 'part01', ... ou um '.tar.gz')"))
            return None
        destino = Path(destino_dir)
        destino.mkdir(parents=True, exist_ok=True)
        tmp = destino / "_grafo_local.tar.gz"
        staging = destino / "_staging"
        try:
            if partes:
                _emitir(progresso, fase="concatenando", partes=len(partes))
                with open(tmp, "wb") as out:
                    for parte in partes:
                        with open(parte, "rb") as f:
                            while True:
                                b = f.read(1024 * 1024)
                                if not b:
                                    break
                                out.write(b)
                origem_tar = tmp
            else:
                origem_tar = unico[0]
            _emitir(progresso, fase="extraindo")
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            with tarfile.open(origem_tar, "r:gz") as t:
                try:
                    t.extractall(staging, filter="data")
                except TypeError:
                    t.extractall(staging)
            cand = _base_osrm_em(staging)
            if cand is None:
                _emitir(progresso, fase="erro",
                        detalhe="os arquivos não formam um grafo OSRM válido (nenhum .osrm.* encontrado); "
                                "confira se baixou TODAS as partes (part00, part01, part02).")
                return None
            for f in cand.parent.glob(cand.name + "*"):
                destino_f = destino / f.name
                if destino_f.exists():
                    destino_f.unlink()
                shutil.move(str(f), str(destino_f))
            final = _base_osrm_em(destino)
            if final:
                _emitir(progresso, fase="pronto", caminho=str(final))
            return str(final) if final else None
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            shutil.rmtree(staging, ignore_errors=True)
    except Exception as e:
        logger.warning("[OSRM] falha ao instalar grafo de partes locais.", exc_info=True)
        _emitir(progresso, fase="erro", detalhe="%s: %s" % (type(e).__name__, e))
        return None


def encerrar(res: ResultadoMotor) -> None:
    """Encerra o OSRM que ESTE processo subiu. No-op caso contrário (não gerenciado). Dois casos:
      • motor NATIVO embarcado (sem container, res.nome vazio) → encerra o processo filho;
      • modo docker → para/remove o CONTAINER pelo nome (confiável) e encerra o cliente."""
    if not (res and res.gerenciado):
        return
    if res.nome:                                    # modo docker gerenciado
        parou = _remover_container(res.nome)        # docker rm -f <nome> (para + remove)
        _encerrar_processo(res.processo)
        if parou:
            logger.info("[OSRM] motor local (Docker) encerrado.")
        else:
            logger.warning("[OSRM] não foi possível confirmar a parada do container %s — "
                           "verifique com 'docker ps'.", res.nome)
    else:                                           # motor nativo embarcado (sem Docker)
        _encerrar_processo(res.processo)
        logger.info("[OSRM] motor nativo local encerrado.")
