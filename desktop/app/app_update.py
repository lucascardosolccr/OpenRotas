# -*- coding: utf-8 -*-
"""OpenRotas Desktop — VERIFICAÇÃO DE ATUALIZAÇÃO DO APLICATIVO (§19).

Consulta as Releases do repositório no GitHub (API pública, sem token, sem cartão) e descobre
se há uma versão do software mais nova que a instalada. NÃO instala sozinho: baixar e trocar o
executável em execução é arriscado — em vez disso, SURFACE a informação (nova versão + link do
instalador) para o usuário decidir, e, se pedido, baixa o instalador para o perfil do usuário
(download verificado) para ele rodar.

  • versao_atual()    — a versão instalada (desktop_config.APP_VERSION, fonte única);
  • consultar_release() — a última Release do app no GitHub (tag + nome + URL do Setup.exe);
  • verificar()       — compara e diz se há atualização, sem levantar;
  • baixar_instalador() — (opcional) baixa o .exe para o perfil do usuário.

Defensivo: offline / API fora do ar / repо privado → devolve 'indisponível', nunca derruba o app.
Stdlib pura (urllib/json)."""
from __future__ import annotations

import os
import sys
import json
import logging
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desktop_config as cfg  # noqa: E402

logger = logging.getLogger("openrotas.desktop.update")

# Repositório oficial e tag da Release que carrega o instalador do app. Sobrescrevíveis por
# ambiente para quem publica num fork.
REPO = os.environ.get("OPENROTAS_REPO", "lucascardosolccr/OpenRotas")
APP_RELEASE_TAG = os.environ.get("OPENROTAS_APP_RELEASE_TAG", "app-latest")


def versao_atual() -> str:
    return str(getattr(cfg, "APP_VERSION", "0.0.0"))


def _versao_tupla(v: str):
    """('1.2.3' | 'v1.2.3' | '2026.10') → tupla de inteiros p/ comparação. None se não-numérico."""
    v = str(v or "").strip().lstrip("vV")
    partes = v.replace("-", ".").split(".")
    try:
        return tuple(int(x) for x in partes if x != "")
    except Exception:
        return None


def ha_atualizacao(atual: str, remota: str) -> bool:
    """True se `remota` for estritamente mais nova que `atual`. Compara por campo numérico;
    degrada para comparação textual se alguma não for numérica."""
    ta, tr = _versao_tupla(atual), _versao_tupla(remota)
    if ta is not None and tr is not None:
        n = max(len(ta), len(tr))
        ta = ta + (0,) * (n - len(ta))
        tr = tr + (0,) * (n - len(tr))
        return tr > ta
    return str(remota or "").lstrip("vV") > str(atual or "").lstrip("vV")


def consultar_release(repo: str = REPO, tag: str = APP_RELEASE_TAG, timeout: int = 8) -> dict:
    """Busca UMA Release do app no GitHub (a `tag`, ou a 'latest' se tag vazia) e extrai a versão
    e o link do instalador (.exe). Devolve {ok, versao, tag, url_instalador, publicado_em, nome}.
    {ok: False, ...} em qualquer falha (offline/privado/404) — nunca levanta."""
    try:
        if tag:
            api = "https://api.github.com/repos/%s/releases/tags/%s" % (repo, tag)
        else:
            api = "https://api.github.com/repos/%s/releases/latest" % repo
        req = urllib.request.Request(api, headers={
            "User-Agent": "OpenRotas-Desktop",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8", "replace"))
        # Versão: do campo 'name' ou da própria tag (ex. 'v0.2.0' → '0.2.0').
        versao = str(dados.get("name") or dados.get("tag_name") or "").strip().lstrip("vV")
        # procura o primeiro asset .exe (o instalador)
        url_exe = None
        for a in dados.get("assets", []) or []:
            nome = str(a.get("name", "")).lower()
            if nome.endswith(".exe"):
                url_exe = a.get("browser_download_url")
                break
        return {"ok": True, "versao": versao or dados.get("tag_name", ""),
                "tag": dados.get("tag_name", tag), "url_instalador": url_exe,
                "publicado_em": dados.get("published_at", ""), "nome": dados.get("name", "")}
    except Exception as e:
        logger.info("[UPDATE] consulta de release indisponível: %s", e)
        return {"ok": False, "versao": "", "tag": tag, "url_instalador": None,
                "publicado_em": "", "nome": "", "erro": str(e)}


def verificar(repo: str = REPO, tag: str = APP_RELEASE_TAG, timeout: int = 8) -> dict:
    """Decisão final para a UI/diagnóstico: compara a versão instalada com a da Release.
    {atual, remota, ha_atualizacao, url_instalador, disponivel, detalhe}. Nunca levanta."""
    atual = versao_atual()
    rel = consultar_release(repo, tag, timeout)
    if not rel["ok"]:
        return {"atual": atual, "remota": None, "ha_atualizacao": False, "url_instalador": None,
                "disponivel": False, "detalhe": "verificação indisponível (offline ou sem Release publicada)"}
    remota = rel["versao"]
    nova = ha_atualizacao(atual, remota)
    return {"atual": atual, "remota": remota, "ha_atualizacao": bool(nova),
            "url_instalador": rel["url_instalador"], "disponivel": True,
            "detalhe": ("atualização %s disponível" % remota) if nova else "você está na versão mais recente"}


def baixar_instalador(url: str, destino: Path | None = None, timeout: int = 120) -> dict:
    """Baixa o instalador para o perfil do usuário (download atômico via resource_manager, que já
    grava .part e troca atômica). O usuário roda o .exe manualmente. {ok, caminho, detalhe}."""
    if not url:
        return {"ok": False, "caminho": None, "detalhe": "sem URL de instalador"}
    try:
        if destino is None:
            destino = cfg.user_data_dir() / "updates" / os.path.basename(url.split("?")[0])
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))
        import resource_manager as rm
        r = rm.baixar_e_verificar(url, Path(destino), sha256="", timeout=timeout)
        return {"ok": r["ok"], "caminho": r.get("caminho"), "detalhe": r.get("detalhe", "")}
    except Exception as e:
        logger.warning("[UPDATE] download do instalador falhou.", exc_info=True)
        return {"ok": False, "caminho": None, "detalhe": "erro: %s" % e}


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    v = verificar()
    print("OpenRotas — atualização do aplicativo")
    print("  versão instalada: %s" % v["atual"])
    if not v["disponivel"]:
        print("  %s" % v["detalhe"])
        return 0
    print("  versão publicada: %s" % v["remota"])
    print("  %s" % v["detalhe"])
    if v["ha_atualizacao"] and v["url_instalador"]:
        print("  baixar: %s" % v["url_instalador"])
        if argv and argv[0] == "--baixar":
            r = baixar_instalador(v["url_instalador"])
            print("  %s" % ("baixado em %s" % r["caminho"] if r["ok"] else "falha: %s" % r["detalhe"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
