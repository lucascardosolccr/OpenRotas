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
import json
import hashlib
import logging
import tempfile
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


# ============================================================================
#  MANIFESTO — REPARO/ATUALIZAÇÃO SEM REINSTALAR (§18/§19/§45)
# ----------------------------------------------------------------------------
#  O manifesto EMBARCADO (resources/manifest.json) descreve a versão e o
#  nome-de-arquivo de cada recurso. Comparando-o com o manifesto REMOTO da
#  Release de dados, o software sabe o que mudou e baixa só isso (§19 —
#  "atualizar só o que mudou"), gravando a cópia nova no diretório de OVERRIDE
#  no perfil do usuário (data_local.override_dir), que VENCE o bundle read-only.
#  Nada é reinstalado: uma base corrompida/desatualizada vira um download
#  verificado por hash (§18 — "reparar sem reinstalar").
# ============================================================================

MANIFESTO_PATH = _AQUI / "manifest.json"


def _manifesto_local_path() -> Path | None:
    """Manifesto GRAVÁVEL no perfil do usuário, que registra as versões já instaladas via
    atualização (o embarcado é read-only em Program Files). É o que torna a atualização
    IDEMPOTENTE (§19): sem ele, cada run reportaria tudo como pendente para sempre."""
    try:
        import desktop_config as cfg
        return cfg.user_data_dir() / "manifest.local.json"
    except Exception:
        return None


def _ler_json(p) -> dict:
    try:
        with open(p, "r", encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


def carregar_manifesto(caminho: Path | None = None) -> dict:
    """Manifesto EFETIVO de versões instaladas. Com `caminho`, lê só esse arquivo. Sem ele,
    parte do embarcado e SOBREPÕE as versões registradas no manifesto local do usuário
    (recursos já atualizados) — assim verificar_atualizacoes não reporta o mesmo para sempre.
    {} em falha; nunca levanta."""
    if caminho is not None:
        m = _ler_json(caminho)
        if not m:
            logger.warning("[RECURSOS] não foi possível ler o manifesto %s", caminho)
        return m
    base = _ler_json(MANIFESTO_PATH)
    lp = _manifesto_local_path()
    local = _ler_json(lp) if lp and Path(lp).exists() else {}
    if local.get("recursos"):
        rec = dict(base.get("recursos", {}))
        for chave, r in local["recursos"].items():
            if chave in rec and isinstance(r, dict) and r.get("versao"):
                rec[chave] = dict(rec[chave], versao=r["versao"])  # versão instalada vence
        base["recursos"] = rec
    return base


def _registrar_versao_local(chave: str, versao: str) -> None:
    """Persiste no manifesto local do usuário a versão recém-instalada de um recurso (§19)."""
    lp = _manifesto_local_path()
    if not lp:
        return
    try:
        Path(lp).parent.mkdir(parents=True, exist_ok=True)
        m = _ler_json(lp)
        rec = m.get("recursos", {}) if isinstance(m.get("recursos"), dict) else {}
        rec[chave] = {"versao": str(versao)}
        m["recursos"] = rec
        m.setdefault("schema", 1)
        with open(lp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("[RECURSOS] não foi possível registrar a versão local de %s", chave, exc_info=True)


def carregar_manifesto_remoto(base_url: str, timeout: int = 15) -> dict:
    """Baixa o manifest.json da Release de dados (base_url termina na pasta …/download/<tag>/).
    {} em falha — nunca levanta. Usado para descobrir atualizações sem baixar as bases inteiras."""
    import urllib.request
    try:
        url = base_url.rstrip("/") + "/manifest.json"
        req = urllib.request.Request(url, headers={"User-Agent": "OpenRotas-Desktop"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            m = json.loads(r.read().decode("utf-8", "replace"))
        return m if isinstance(m, dict) else {}
    except Exception:
        logger.info("[RECURSOS] manifesto remoto indisponível (%s).", base_url)
        return {}


def _versao_maior(remota: str, local: str) -> bool:
    """True se 'remota' > 'local' comparando campos numéricos (ex. '2026.11' > '2026.10').
    Degrada para comparação textual se não for numérico."""
    def _tup(v):
        partes = str(v).replace("-", ".").split(".")
        try:
            return tuple(int(x) for x in partes)
        except Exception:
            return None
    tr, tl = _tup(remota), _tup(local)
    if tr is not None and tl is not None:
        # normaliza o comprimento preenchendo com zeros à direita
        n = max(len(tr), len(tl))
        tr = tr + (0,) * (n - len(tr))
        tl = tl + (0,) * (n - len(tl))
        return tr > tl
    return str(remota) > str(local)


def verificar_atualizacoes(manifesto_remoto: dict, manifesto_local: dict | None = None) -> list:
    """Compara o manifesto REMOTO com o LOCAL (embarcado) e devolve a lista do que atualizar:
    [{chave, versao_local, versao_remota, arquivo, sha256, obrigatorio}]. Um recurso entra se a
    versão remota for maior OU se existir remotamente e não localmente. Nunca levanta → [] em falha."""
    try:
        loc = manifesto_local if manifesto_local is not None else carregar_manifesto()
        r_rec = (manifesto_remoto or {}).get("recursos", {}) or {}
        l_rec = (loc or {}).get("recursos", {}) or {}
        pendentes = []
        for chave, r in r_rec.items():
            if not isinstance(r, dict):
                continue
            v_rem = str(r.get("versao", ""))
            l = l_rec.get(chave) or {}
            v_loc = str(l.get("versao", ""))
            if (not v_loc) or _versao_maior(v_rem, v_loc):
                pendentes.append({
                    "chave": chave,
                    "versao_local": v_loc or "(ausente)",
                    "versao_remota": v_rem,
                    "arquivo": r.get("arquivo", ""),
                    "sha256": r.get("sha256", ""),
                    "obrigatorio": bool(r.get("obrigatorio", False)),
                })
        return pendentes
    except Exception:
        logger.warning("[RECURSOS] comparação de manifestos falhou.", exc_info=True)
        return []


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_e_verificar(url: str, destino: Path, sha256: str = "", timeout: int = 60) -> dict:
    """Baixa `url` para `destino` de forma ATÔMICA (grava em .part e só então renomeia) e, se
    `sha256` for informado, VALIDA a integridade — descartando o arquivo se não bater (§18/§45).
    Devolve {ok, caminho, bytes, sha256, detalhe}. Nunca levanta."""
    import urllib.request
    destino = Path(destino)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    tmp = None
    try:
        fd, tmp_nome = tempfile.mkstemp(prefix=destino.name + ".", suffix=".part", dir=str(destino.parent))
        os.close(fd)
        tmp = Path(tmp_nome)
        req = urllib.request.Request(url, headers={"User-Agent": "OpenRotas-Desktop"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
            while True:
                bloco = resp.read(1024 * 256)
                if not bloco:
                    break
                out.write(bloco)
        digest = _sha256_arquivo(tmp)
        if sha256 and digest.lower() != str(sha256).lower():
            try:
                tmp.unlink()
            except Exception:
                pass
            return {"ok": False, "caminho": None, "bytes": 0, "sha256": digest,
                    "detalhe": "hash não confere (esperado %s, obtido %s) — descartado" % (sha256[:12], digest[:12])}
        tam = tmp.stat().st_size
        os.replace(str(tmp), str(destino))      # troca atômica
        return {"ok": True, "caminho": str(destino), "bytes": tam, "sha256": digest,
                "detalhe": "verificado por sha256" if sha256 else "baixado (sem sha256 para verificar)"}
    except Exception as e:
        try:
            if tmp and tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        logger.warning("[RECURSOS] download de %s falhou.", url, exc_info=True)
        return {"ok": False, "caminho": None, "bytes": 0, "sha256": "", "detalhe": "erro: %s" % e}


def atualizar(manifesto_remoto: dict, base_url: str, apenas=None) -> list:
    """Aplica as atualizações pendentes: baixa cada recurso mudado de `base_url`/arquivo para o
    diretório de override no perfil do usuário e verifica por sha256. `apenas` (iterável de chaves)
    limita o que atualizar. Devolve a lista de resultados por recurso. Não levanta."""
    cfg, reg = _registry()
    import local_data
    _provisionaveis = {d.chave for d in local_data.CATALOGO if d.formato == "osrm"}
    pendentes = verificar_atualizacoes(manifesto_remoto)
    if apenas is not None:
        apenas = set(apenas)
        pendentes = [p for p in pendentes if p["chave"] in apenas]
    resultados = []
    for p in pendentes:
        # O grafo OSRM NÃO é uma base de cópia simples (vem em partes e é extraído/servido via
        # Docker); é provisionado por provisionar_grafo/garantir_grafo, não por aqui. Baixá-lo
        # para override_dir seria ignorado (caminho() não consulta override p/ data_local/).
        if p["chave"] in _provisionaveis:
            resultados.append({"chave": p["chave"], "ok": False, "arquivo": p.get("arquivo", ""),
                               "versao": p["versao_remota"],
                               "detalhe": "provisionável (grafo) — use provisionar_grafo/--reparar, não atualizar"})
            continue
        arq = p.get("arquivo") or ""
        if not arq:
            resultados.append({"chave": p["chave"], "ok": False, "detalhe": "sem nome de arquivo no manifesto"})
            continue
        url = base_url.rstrip("/") + "/" + arq
        destino = reg.override_dir / arq
        r = baixar_e_verificar(url, destino, p.get("sha256", ""))
        if r["ok"]:
            _registrar_versao_local(p["chave"], p["versao_remota"])   # idempotência (§19)
        reg.liberar_memoria()               # invalida cache em memória para reler a cópia nova
        resultados.append({"chave": p["chave"], "ok": r["ok"], "arquivo": arq,
                           "versao": p["versao_remota"], "detalhe": r["detalhe"], "caminho": r.get("caminho")})
    return resultados


def reparar_tudo(osrm_cfg: dict | None = None, base_url: str = "") -> dict:
    """[REPARO DE UM CLIQUE - §18] Verifica tudo e conserta o que der, SEM reinstalar:
      1. integridade/ausência dos recursos (verificar);
      2. se `base_url` (Release de dados) → baixa/atualiza as bases pendentes (sha256);
      3. se `osrm_cfg.graph_url` e o grafo falta → provisiona o grafo.
    Devolve um relatório combinado. Não levanta. É o que o atalho "Reparar/Atualizar" e o
    `launcher --reparar` chamam."""
    rel = {"verificacao": verificar(), "bases_atualizadas": [], "grafo": None, "ok": True}
    base_url = str(base_url or "").strip()
    try:
        if base_url:
            remoto = carregar_manifesto_remoto(base_url)
            if remoto:
                rel["bases_atualizadas"] = atualizar(remoto, base_url)
    except Exception:
        logger.warning("[RECURSOS] atualização de bases no reparo falhou.", exc_info=True)
    try:
        cfg, reg = _registry()
        oc = dict(osrm_cfg or {})
        if not reg.existe("osrm_brasil") and str(oc.get("graph_url", "")).strip():
            rel["grafo"] = provisionar_grafo(oc)
    except Exception:
        logger.warning("[RECURSOS] provisionamento do grafo no reparo falhou.", exc_info=True)
    # 'ok' reflete: nada obrigatório faltando/corrompido e nenhum download marcado como falho.
    rel["ok"] = (rel["verificacao"]["ok"]
                 and all(b.get("ok", True) for b in rel["bases_atualizadas"])
                 and (rel["grafo"] is None or rel["grafo"].get("ok", True)))
    return rel


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
    if cmd == "manifesto":
        m = carregar_manifesto()
        rec = m.get("recursos", {})
        print("Manifesto embarcado (schema %s, release de dados '%s'):" % (m.get("schema"), m.get("data_release_tag")))
        for ch, r in rec.items():
            print("  %-22s versao=%-9s %s" % (ch, r.get("versao"), "obrigatório" if r.get("obrigatorio") else "opcional"))
        return 0
    print("uso: resource_manager.py [status|verificar|manifesto]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
