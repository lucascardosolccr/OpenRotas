"""
Evaluation - mede o impacto do enriquecimento geoespacial nas derrotas (Task 9).

ANTES × DEPOIS sobre o mesmo dataset empírico da missão (_baseline_1452.json):

  * derrotas_residuais — derrotas cujo vencedor-referência NÃO é explicado por
    balsa/fluvial/infraestrutura aquaviária confirmada nas bases locais IBGE.
    O enriquecimento separa a barreira REAL (ferry/fluvial auditável) da derrota
    corrigível, sem precisar de rede.
  * ferry_detection   — nº de trechos auditados com balsa confirmada no entorno.
  * explicacao_pct    — % de trechos auditáveis (motivo_decisao + fontes + confiança ≥ 40).

CLI:
  py -X utf8 -m inteligencia_geoespacial.evaluation --max 0 --cache on --write on
    --max n    limita a nº de derrotas auditadas (0 = todas; default 0)
    --cache    persiste os enriquecimentos em cache_geoespacial/evaluation_enriquecimento.json
    --write    reescreve docs/ANTES_DEPOIS_ENRIQUECIMENTO.md com os resultados
"""

from __future__ import annotations

import argparse
import json
import os
import time

from .enrichment_engine import enriquecer_rota

_CACHE_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cache_geoespacial", "evaluation_enriquecimento.json")

_NIVEL_MIN_AUDITAVEL = 40
_TARGET_DERROTAS = 70
_FERRY_BASELINE_MISSAO = 21
_EXPLICACAO_BASELINE_MISSAO = 80.0


def _raiz_projeto() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dataset(caminho: str | None = None) -> list | None:
    """Carrega _baseline_1452.json (cópia local; fallback no temp da análise original)."""
    if caminho and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    locais = [
        caminho or os.path.join(_raiz_projeto(), "_baseline_1452.json"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "opencode", "_relatorio_dados.json"),
    ]
    for p in locais:
        try:
            if p and os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return None


def _coords_validas(linha: dict) -> bool:
    for k in ("olat", "olon", "rlat", "rlon"):
        v = linha.get(k)
        if v is None:
            return False
        try:
            float(v)
        except (TypeError, ValueError):
            return False
    return True


def _chave_linha(linha: dict) -> str:
    return "%s|%s|%.4f,%.4f->%.4f,%.4f" % (
        linha.get("o", "?"), linha.get("uf", "?"),
        float(linha["olat"]), float(linha["olon"]),
        float(linha["rlat"]), float(linha["rlon"]))


def _carregar_cache() -> dict:
    if not os.path.exists(_CACHE_JSON):
        return {}
    try:
        with open(_CACHE_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_cache(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_JSON), exist_ok=True)
        with open(_CACHE_JSON, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _enriquecer_com_cache(linha: dict, raio_km: float, usar_cache: bool) -> dict:
    cache = {}
    chave = _chave_linha(linha)
    if usar_cache:
        cache = _carregar_cache()
        if chave in cache:
            return cache[chave]
    rec = enriquecer_rota((linha["olat"], linha["olon"]),
                          (linha["rlat"], linha["rlon"]), raio_km=raio_km)
    if usar_cache:
        cache[chave] = rec
        _salvar_cache(cache)
    return rec


def _rio_navegavel(rec: dict) -> bool:
    for r in rec.get("rios_detectados", []):
        nav = (r.get("navegavel") or "").strip().lower()
        if nav in ("sim", "parcial"):
            return True
    return False


def _tem_infra_aqua(rec: dict) -> bool:
    infra = rec.get("infraestrutura_aquaviaria") or {}
    return bool(infra.get("atracadouros_terminal") or infra.get("complexos_portuarios")
                or infra.get("eclusas"))


def _auditavel(rec: dict) -> bool:
    if not (rec.get("motivo_decisao") or "").strip():
        return False
    if len(rec.get("fontes_concordam") or []) < 1:
        return False
    try:
        return float(rec.get("confianca_geral") or 0) >= _NIVEL_MIN_AUDITAVEL
    except Exception:
        return False


def _avaliar(linhas: list, raio_km: float, usar_cache: bool,
             progresso=None) -> list:
    """Audita cada derrota e devolve métricas por linha (sem rede)."""
    res = []
    for i, linha in enumerate(linhas):
        t = time.time()
        rec = _enriquecer_com_cache(linha, raio_km, usar_cache)
        res.append({
            "origem": linha["o"],
            "uf": linha["uf"],
            "da_km": float(linha["da"]),
            "dr_km": float(linha["dr"]),
            "dif_km": float(linha["dif"]),
            "balsas": len(rec.get("balsas_confirmadas") or []),
            "rios": len(rec.get("rios_detectados") or []),
            "rio_navegavel": _rio_navegavel(rec),
            "infra_aqua": _tem_infra_aqua(rec),
            "explicada": bool(rec.get("balsas_confirmadas")) or _rio_navegavel(rec)
                         or _tem_infra_aqua(rec),
            "confianca": rec.get("confianca_geral"),
            "fontes": len(rec.get("fontes_concordam") or []),
            "auditavel": _auditavel(rec),
            "seg": round(time.time() - t, 2),
        })
        if progresso:
            progresso(i + 1, len(linhas))
    return res


def avaliar(max_rows: int = 0, usar_cache: bool = True, raio_km: float = 40.0,
            dataset_path: str | None = None) -> dict:
    """Executa a avaliação e devolve o relatório estruturado.

    max_rows=0 audita TODAS as derrotas do baseline (padrão).
    """
    base = _dataset(dataset_path)
    derrotas = [r for r in (base or []) if r.get("venc") == "Referência"]
    if not derrotas:
        return {"ok": False, "motivo": "baseline nao encontrado ou sem derrotas"}

    amostra_total = derrotas if max_rows <= 0 else derrotas[:max_rows]
    amostra = [r for r in amostra_total if _coords_validas(r)]
    sem_coords = len(amostra_total) - len(amostra)
    auditadas = _avaliar(amostra, raio_km, usar_cache, progresso=_progresso)
    n = len(auditadas) or 1

    explicadas = sum(1 for a in auditadas if a["explicada"])
    auditaveis = sum(1 for a in auditadas if a["auditavel"])
    balsas = sum(a["balsas"] for a in auditadas)
    seg_total = sum(a["seg"] for a in auditadas)

    derrotas_baseline = len(derrotas)
    derrotas_residuais = max(0, derrotas_baseline - explicadas)
    reducao_pct = round(100.0 * explicadas / derrotas_baseline, 1) if derrotas_baseline else 0.0

    return {
        "ok": True,
        "dataset": "baseline_1452",
        "total_linhas": len(base or []),
        "derrotas_baseline": derrotas_baseline,
        "derrotas_auditadas": n,
        "derrotas_sem_coords": sem_coords,
        "derrotas_explicadas": explicadas,
        "derrotas_residuais": derrotas_residuais,
        "reducao_pct": reducao_pct,
        "ferry_detection": balsas,
        "ferry_linhas_com_balsa": sum(1 for a in auditadas if a["balsas"]),
        "explicacao_qualidade_pct": round(100.0 * auditaveis / n, 1),
        "raio_km": raio_km,
        "tempo_medio_seg": round(seg_total / n, 2),
        "metas": {
            "reducao_alvo_pct": 20.0,
            "derrotas_alvo": _TARGET_DERROTAS,
            "ferry_baseline_missao": _FERRY_BASELINE_MISSAO,
            "ferry_alvo": 35,
            "explicacao_baseline_missao": _EXPLICACAO_BASELINE_MISSAO,
        },
        "linhas": auditadas,
    }


def _progresso(done: int, total: int) -> None:
    if total and done % 10 == 0:
        print("  ... %d/%d derrotas auditadas" % (done, total), flush=True)


def _markdown(r: dict) -> str:
    if not r.get("ok"):
        return "# ANTES × DEPOIS — Enriquecimento\n\nFora do ar: %s\n" % r["motivo"]
    m = r["metas"]
    linhas = ["| Origem | UF | da (km) | dr (km) | balsas | rio nav. | explicada | auditável | conf. |",
              "|---|---:|---:|---:|---:|:---:|---:|---:|---:|"]
    for a in sorted(r["linhas"], key=lambda x: (x["explicada"], -x["dif_km"])):
        linhas.append("| %s | %s | %.1f | %.1f | %d | %s | %s | %s | %s |" % (
            a["origem"], a["uf"], a["da_km"], a["dr_km"], a["balsas"],
            "sim" if a["rio_navegavel"] else "não",
            "sim" if a["explicada"] else "não",
            "sim" if a["auditavel"] else "não",
            a["confianca"]))
    return "\n".join([
        "# ANTES × DEPOIS — Enriquecimento Geoespacial (Task 9)",
        "",
        "Dataset: `_baseline_1452.json` (%d municípios) · raio de auditoria %g km · offline." % (
            r["total_linhas"], r["raio_km"]),
        "Metodologia: para cada `venc == Referência`, o enriquecimento local confirma (ou não) que o "
        "vencedor-referência é explicado por **travessia de balsa**, **rio navegável** ou "
        "**infraestrutura aquaviária** nas proximidades — sem falsa barreira.",
        "",
        "## Resultados",
        "",
        "- **derrotas residuais** %d (%d explicadas por balsa/fluvial/infra aquaviária) — "
        "redução de **%.1f%%** sobre as %d derrotas do baseline (alvo da missão: ≥ %.0f%%)" % (
            r["derrotas_residuais"], r["derrotas_explicadas"], r["reducao_pct"],
            r["derrotas_baseline"], m["reducao_alvo_pct"]),
        "- **detecção de balsa** %d balsas confirmadas nas %d derrotas auditadas — "
        "baseline da missão: %d · alvo: ≥ %d" % (r["ferry_detection"], r["derrotas_auditadas"],
                                                 m["ferry_baseline_missao"], m["ferry_alvo"]),
        "- **qualidade da explicação** %.1f%% das derrotas auditáveis (motivo + fontes + "
        "confiança ≥ 40) — baseline da missão: %.1f%%" % (r["explicacao_qualidade_pct"],
                                                          m["explicacao_baseline_missao"]),
        "- %d/%d derrotas do baseline auditadas · %.2f s/derrota médio · cache em "
        "`cache_geoespacial/evaluation_enriquecimento.json`." % (
            r["derrotas_auditadas"], r["derrotas_baseline"], r["tempo_medio_seg"]),
        "- %d derrota(s) sem coordenadas no baseline (não auditáveis offline)." % r["derrotas_sem_coords"],
        "",
        "## Detalhe por derrota",
        "",
        "\n".join(linhas),
        "",
    ])


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mede o impacto do enriquecimento (Task 9).")
    ap.add_argument("--max", type=int, default=0, help="0 = todas as derrotas")
    ap.add_argument("--cache", type=str, default="on", choices=("on", "off"))
    ap.add_argument("--write", type=str, default="off", choices=("on", "off"))
    ap.add_argument("--raio", type=float, default=40.0)
    args = ap.parse_args(argv)
    r = avaliar(max_rows=args.max, usar_cache=args.cache == "on", raio_km=args.raio)
    if not r.get("ok"):
        print(r.get("motivo", "erro"))
        return 1
    print(_markdown(r))
    if args.write == "on":
        doc = os.path.join(_raiz_projeto(), "docs", "ANTES_DEPOIS_ENRIQUECIMENTO.md")
        os.makedirs(os.path.dirname(doc), exist_ok=True)
        with open(doc, "w", encoding="utf-8") as f:
            f.write(_markdown(r))
        print("Escrito: %s" % doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())