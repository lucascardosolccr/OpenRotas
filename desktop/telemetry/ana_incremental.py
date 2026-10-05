# -*- coding: utf-8 -*-
"""OpenRotas Desktop — TELEMETRIA HIDROMETEOROLÓGICA INCREMENTAL (§9/§10/§11/§34/§35).

Infraestrutura LOCAL de telemetria (inventário de estações + séries), com ATUALIZAÇÃO
INCREMENTAL: guarda uma "marca d'água" (watermark) por dataset e, a cada atualização, só ingere o
que é NOVO — nunca rebaixa o histórico inteiro (§35). O armazenamento é append-only em JSONL no
perfil do usuário, com DEDUP por chave (§34: "o que já tenho / o que mudou").

Arquitetura (o CORE é testável sem rede):
  • TelemetryStore  — ingerir/listar/inventário/watermark em disco (JSONL), dedup por chave;
  • atualizar_incremental(dataset, fetch_fn) — laço incremental: busca só desde o watermark,
    ingere o novo, avança o watermark. `fetch_fn` é injetável (testes usam um mock; produção usa
    o AnaClient);
  • AnaClient — BEST-EFFORT online (ANA/HidroWeb/SNIRH): tenta uma URL de export configurada
    (telemetria.inventario_url no desktop.json) e degrada graciosamente offline/sem config.
    (As APIs atuais da ANA podem exigir cadastro/token; por isso a URL é configurável, sem
    endpoint frágil embutido.)

Puro/defensivo: nunca levanta para o chamador. Stdlib (json/urllib)."""
from __future__ import annotations

import os
import sys
import json
import time
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent / "app", _AQUI.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.telemetria")


def _base_padrao() -> Path:
    try:
        import desktop_config as cfg
        return cfg.user_data_dir() / "telemetry"
    except Exception:
        return Path.home() / ".openrotas" / "telemetry"


def _chave_padrao(rec: dict) -> str:
    """Chave de dedup: 'codigo'/'id'/'estacao' + 'data' quando existirem; senão o JSON ordenado."""
    for k in ("codigo", "id", "estacao", "codigo_estacao"):
        if rec.get(k) not in (None, ""):
            base = str(rec.get(k))
            if rec.get("data") not in (None, ""):
                return "%s@%s" % (base, rec.get("data"))
            return base
    try:
        return json.dumps(rec, sort_keys=True, ensure_ascii=False)
    except Exception:
        return repr(rec)


class TelemetryStore:
    """Armazém local append-only (JSONL) com watermark e dedup. Nunca levanta."""

    def __init__(self, base_dir=None):
        self.base = Path(base_dir) if base_dir else _base_padrao()
        try:
            self.base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _caminho(self, dataset: str) -> Path:
        return self.base / ("%s.jsonl" % dataset)

    def _wm_path(self) -> Path:
        return self.base / "watermark.json"

    # ---- watermark ----
    def carregar_watermark(self, dataset: str):
        try:
            p = self._wm_path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8")).get(dataset)
        except Exception:
            pass
        return None

    def salvar_watermark(self, dataset: str, valor) -> None:
        try:
            p = self._wm_path()
            m = {}
            if p.exists():
                try:
                    m = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    m = {}
            m[dataset] = valor
            p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("[TEL] não foi possível salvar watermark de %s.", dataset, exc_info=True)

    # ---- leitura ----
    def listar(self, dataset: str, limite=None) -> list:
        out = []
        try:
            p = self._caminho(dataset)
            if not p.exists():
                return out
            with open(p, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        out.append(json.loads(linha))
                    except Exception:
                        continue
                    if limite and len(out) >= limite:
                        break
        except Exception:
            logger.warning("[TEL] falha ao ler %s.", dataset, exc_info=True)
        return out

    def _chaves_existentes(self, dataset: str, chave_fn) -> set:
        return set(chave_fn(r) for r in self.listar(dataset))

    def contar(self, dataset: str) -> int:
        try:
            p = self._caminho(dataset)
            if not p.exists():
                return 0
            with open(p, "r", encoding="utf-8") as f:
                return sum(1 for l in f if l.strip())
        except Exception:
            return 0

    # ---- ingestão com dedup ----
    def ingerir(self, dataset: str, registros, chave_fn=None) -> dict:
        """Acrescenta só os registros NOVOS (dedup por chave). {novos, duplicados, total}."""
        chave_fn = chave_fn or _chave_padrao
        registros = list(registros or [])
        res = {"novos": 0, "duplicados": 0, "total": 0}
        try:
            existentes = self._chaves_existentes(dataset, chave_fn)
            novas = []
            vistas = set(existentes)
            for r in registros:
                if not isinstance(r, dict):
                    continue
                k = chave_fn(r)
                if k in vistas:
                    res["duplicados"] += 1
                    continue
                vistas.add(k)
                novas.append(r)
            if novas:
                p = self._caminho(dataset)
                with open(p, "a", encoding="utf-8") as f:
                    for r in novas:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
            res["novos"] = len(novas)
            res["total"] = self.contar(dataset)
        except Exception:
            logger.warning("[TEL] ingestão de %s falhou.", dataset, exc_info=True)
        return res

    def inventario(self) -> dict:
        out = {}
        try:
            for p in sorted(self.base.glob("*.jsonl")):
                out[p.stem] = {"registros": self.contar(p.stem),
                               "watermark": self.carregar_watermark(p.stem)}
        except Exception:
            pass
        return out


def atualizar_incremental(dataset: str, fetch_fn, store=None, chave_fn=None, campo_ts: str = "data") -> dict:
    """Laço INCREMENTAL (§35): chama fetch_fn(watermark_atual) → registros novos; ingere com dedup;
    avança o watermark para o maior `campo_ts` visto. `fetch_fn` é injetável (mock nos testes,
    AnaClient em produção). Devolve {novos, duplicados, total, watermark_anterior, watermark_novo}.
    Nunca levanta."""
    store = store or TelemetryStore()
    chave_fn = chave_fn or _chave_padrao
    wm0 = store.carregar_watermark(dataset)
    try:
        registros = list(fetch_fn(wm0) or [])
    except Exception:
        logger.warning("[TEL] fetch de %s falhou.", dataset, exc_info=True)
        registros = []
    r = store.ingerir(dataset, registros, chave_fn=chave_fn)
    wm1 = wm0
    try:
        tss = [rec.get(campo_ts) for rec in registros if rec.get(campo_ts) not in (None, "")]
        if tss:
            novo = max(str(t) for t in tss)
            if wm0 is None or str(novo) > str(wm0):
                wm1 = novo
                store.salvar_watermark(dataset, wm1)
    except Exception:
        pass
    r.update({"watermark_anterior": wm0, "watermark_novo": wm1})
    return r


class AnaClient:
    """Cliente BEST-EFFORT para export de inventário/série da ANA (URL configurável). Online quando
    há `inventario_url`/`serie_url` na config (telemetria.*); degrada para {ok:False} offline."""

    def __init__(self, conf=None):
        try:
            import desktop_config as cfg
            conf = conf if conf is not None else (cfg.carregar_config_usuario() or {})
        except Exception:
            conf = conf or {}
        self.cfg = dict((conf or {}).get("telemetria") or {})

    def _baixar(self, url: str, timeout: int = 20):
        import urllib.request
        if os.environ.get("OPENROTAS_NO_NET"):
            return None, "rede desabilitada (OPENROTAS_NO_NET)"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OpenRotas-Desktop"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = r.read().decode("utf-8", "replace")
            return dados, None
        except Exception as e:
            return None, "erro: %s" % e

    def _parse(self, texto: str) -> list:
        """Aceita JSON (lista de objetos, ou {itens:[...]}/{estacoes:[...]}) ou CSV com cabeçalho."""
        texto = (texto or "").strip()
        if not texto:
            return []
        if texto[0] in "[{":
            try:
                d = json.loads(texto)
                if isinstance(d, list):
                    return [r for r in d if isinstance(r, dict)]
                if isinstance(d, dict):
                    for k in ("itens", "estacoes", "items", "data", "results"):
                        if isinstance(d.get(k), list):
                            return [r for r in d[k] if isinstance(r, dict)]
            except Exception:
                return []
            return []
        # CSV
        import csv, io
        try:
            return list(csv.DictReader(io.StringIO(texto)))
        except Exception:
            return []

    def inventario_estacoes(self) -> dict:
        """Busca o inventário de estações (se telemetria.inventario_url). {ok, registros:[...], detalhe}."""
        url = str(self.cfg.get("inventario_url", "") or "").strip()
        if not url:
            return {"ok": False, "registros": [], "detalhe": "sem telemetria.inventario_url na config"}
        dados, erro = self._baixar(url)
        if dados is None:
            return {"ok": False, "registros": [], "detalhe": erro}
        regs = self._parse(dados)
        return {"ok": True, "registros": regs, "detalhe": "%d registros" % len(regs)}


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    store = TelemetryStore()
    print("OpenRotas — Telemetria (infraestrutura local, incremental)")
    print("=" * 56)
    inv = store.inventario()
    if not inv:
        print("Sem datasets locais ainda.")
    for ds, meta in inv.items():
        print("  %-20s %d registros · watermark=%s" % (ds, meta["registros"], meta["watermark"]))
    if "--atualizar" in argv:
        cli = AnaClient()
        r = cli.inventario_estacoes()
        if r["ok"]:
            res = atualizar_incremental("estacoes", lambda wm: r["registros"], store=store)
            print("\nAtualização incremental: +%d novos (%d duplicados), total %d."
                  % (res["novos"], res["duplicados"], res["total"]))
        else:
            print("\nAtualização online indisponível: %s" % r["detalhe"])
            print("Configure telemetria.inventario_url (export da ANA/HidroWeb) no desktop.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
