# -*- coding: utf-8 -*-
"""OpenRotas Desktop — AUDITOR DE COBERTURA NACIONAL (§3/§4/§40/§42/§64/§65/§66).

Requisito central do produto: o software NÃO pode declarar "Brasil completo" sem PROVA. Este
módulo mede, a partir dos DADOS REALMENTE INSTALADOS (nunca de números inventados — §71), a
cobertura nacional por dimensão e devolve um laudo objetivo com status honesto (OK / PARCIAL /
AUSENTE) e percentuais derivados dos dados:

  • Estados (UFs):   UFs distintas presentes na base de municípios (prefixo do geocódigo IBGE) —
                     sinal AUTORITATIVO (a lista de municípios é a fonte oficial das 27 UFs).
  • Municípios:      nº de geocódigos distintos vs 5.570 oficiais (reporta o número real; o IBGE
                     lista 5.570 municípios + o Distrito Estadual de Fernando de Noronha).
  • Malha/Hidro/etc: para cada camada nacional (rodovias, drenagem, ferrovias, pontes, travessias,
                     hidrovias, massas d'água, …), conta FEIÇÕES e verifica a PRESENÇA ESPACIAL em
                     cada UF, atribuindo o ponto representativo (lon/lat) de cada feição à caixa
                     envolvente (bbox) de cada UF — método aproximado, honestamente rotulado.
                     (Obs.: a coluna fonte_uf é um RÓTULO DE ORIGEM — "BR" para a base nacional
                     IBGE BC250 + alguns complementos estaduais — e por isso NÃO serve para medir
                     cobertura por UF; usamos a geografia real das feições.)
  • Grafo OSRM:      presente/ausente (recurso provisionável de vários GB — baixável na Central).
  • Índices:         presença dos índices espaciais/auxiliares embarcados.

Puro e defensivo: nunca levanta para o chamador; cada dimensão degrada sozinha. Depende de
pandas/numpy (já presentes). Projeção de colunas (lê só o necessário) para não estourar RAM."""
from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent / "app", _AQUI.parent, _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.audit")

# 27 unidades federativas (26 estados + DF) e o prefixo do geocódigo IBGE (2 primeiros dígitos).
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}
UFS_ESPERADAS = set(UF_POR_CODIGO.values())           # 27
MUNICIPIOS_OFICIAIS = 5570                            # IBGE (sem o distrito de Fernando de Noronha)

OK, PARCIAL, AUSENTE, NA = "OK", "PARCIAL", "AUSENTE", "N/A"

# Camadas de REDE/feições a auditar espacialmente (chave do catálogo → rótulo legível).
CAMADAS_REDE = [
    ("rodovias", "Malha rodoviária"),
    ("drenagem", "Rede de drenagem / rios"),
    ("massas_dagua", "Massas d'água"),
    ("ferrovias", "Malha ferroviária"),
    ("pontes", "Pontes"),
    ("travessias", "Travessias / balsas"),
    ("hidrovias", "Hidrovias"),
    ("eclusas", "Eclusas"),
    ("atracadouros_terminal", "Atracadouros / terminais"),
    ("complexos_portuarios", "Complexos portuários"),
    ("sinalizacao", "Sinalização náutica"),
]


def _registry():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _uf_do_geocodigo(serie):
    """Mapeia uma série de geocódigos IBGE (7 díg.) para a sigla da UF pelo prefixo. Defensivo."""
    import pandas as pd
    s = serie.astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
    pref = pd.to_numeric(s.str[:2], errors="coerce")
    return pref.map(UF_POR_CODIGO)


def _bboxes_uf(reg) -> dict:
    """Caixa envolvente (xmin,ymin,xmax,ymax) de cada UF, agregada das bboxes municipais da base
    de municípios. Base para a verificação de presença espacial das camadas de rede. {} em falha."""
    try:
        df = reg.carregar_parquet("municipios", colunas=["geocodigo", "xmin", "ymin", "xmax", "ymax"])
    except Exception:
        return {}
    try:
        uf = _uf_do_geocodigo(df["geocodigo"])
        g = df.assign(_uf=uf).dropna(subset=["_uf"]).groupby("_uf")
        out = {}
        xmin = g["xmin"].min(); ymin = g["ymin"].min(); xmax = g["xmax"].max(); ymax = g["ymax"].max()
        for u in xmin.index:
            out[u] = (float(xmin[u]), float(ymin[u]), float(xmax[u]), float(ymax[u]))
        return out
    except Exception:
        logger.warning("[AUDIT] falha ao montar bboxes por UF.", exc_info=True)
        return {}


def cobertura_estados_municipios(reg) -> dict:
    """Cobertura AUTORITATIVA de estados e municípios a partir da base de municípios instalada.
    Devolve {estados:{...}, municipios:{...}} com números REAIS (nunca inventados)."""
    base = {"estados": {"status": AUSENTE, "presentes": [], "ausentes": sorted(UFS_ESPERADAS),
                        "pct": 0.0, "esperado": 27, "encontrado": 0},
            "municipios": {"status": AUSENTE, "encontrado": 0, "oficial": MUNICIPIOS_OFICIAIS,
                           "pct": 0.0, "por_uf": {}}}
    if not reg.existe("municipios"):
        return base
    try:
        df = reg.carregar_parquet("municipios", colunas=["geocodigo"])
        uf = _uf_do_geocodigo(df["geocodigo"]).dropna()
        presentes = sorted(set(uf.unique()))
        ausentes = sorted(UFS_ESPERADAS - set(presentes))
        base["estados"] = {
            "status": OK if not ausentes else PARCIAL,
            "presentes": presentes, "ausentes": ausentes,
            "encontrado": len(presentes), "esperado": 27,
            "pct": round(100.0 * len(presentes) / 27.0, 1),
        }
        n = int(df["geocodigo"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7).nunique())
        por_uf = uf.value_counts().to_dict()
        base["municipios"] = {
            "status": OK if n >= MUNICIPIOS_OFICIAIS else PARCIAL,
            "encontrado": n, "oficial": MUNICIPIOS_OFICIAIS,
            "pct": round(min(100.0, 100.0 * n / MUNICIPIOS_OFICIAIS), 1),
            "por_uf": {k: int(v) for k, v in sorted(por_uf.items())},
        }
    except Exception:
        logger.warning("[AUDIT] falha na cobertura estados/municípios.", exc_info=True)
    return base


def presenca_espacial_uf(reg, chave: str, bboxes: dict, amostra: int | None = None) -> dict:
    """Para uma camada de feições, verifica em quais UFs há PRESENÇA espacial (≥1 feição cujo
    ponto representativo lon/lat cai na bbox da UF). Método aproximado (bboxes se sobrepõem) e
    assim rotulado. Devolve {instalado, feicoes, ufs_presentes:[...], ufs_ausentes:[...], pct}.
    `amostra` (opcional) limita o nº de pontos avaliados (auditoria rápida). Nunca levanta."""
    res = {"instalado": False, "feicoes": 0, "ufs_presentes": [], "ufs_ausentes": sorted(UFS_ESPERADAS),
           "pct": 0.0}
    if not reg.existe(chave):
        return res
    res["instalado"] = True
    try:
        import numpy as np
        df = reg.carregar_parquet(chave, colunas=["lon", "lat"])
        res["feicoes"] = int(len(df))
        if not bboxes or len(df) == 0:
            return res
        lon = df["lon"].to_numpy(dtype="float64", copy=False)
        lat = df["lat"].to_numpy(dtype="float64", copy=False)
        if amostra and len(lon) > amostra:
            idx = np.linspace(0, len(lon) - 1, amostra).astype("int64")
            lon, lat = lon[idx], lat[idx]
        finito = np.isfinite(lon) & np.isfinite(lat)
        lon, lat = lon[finito], lat[finito]
        presentes = []
        for u, (xmin, ymin, xmax, ymax) in bboxes.items():
            if np.any((lon >= xmin) & (lon <= xmax) & (lat >= ymin) & (lat <= ymax)):
                presentes.append(u)
        presentes = sorted(presentes)
        res["ufs_presentes"] = presentes
        res["ufs_ausentes"] = sorted(UFS_ESPERADAS - set(presentes))
        res["pct"] = round(100.0 * len(presentes) / 27.0, 1)
    except Exception:
        logger.warning("[AUDIT] presença espacial de %r falhou.", chave, exc_info=True)
    return res


def _status_rede(r: dict) -> str:
    if not r.get("instalado"):
        return AUSENTE
    npres = len(r.get("ufs_presentes") or [])
    if npres >= 27:
        return OK
    if npres > 0:
        return PARCIAL
    return PARCIAL if r.get("feicoes") else AUSENTE


def auditar(rapido: bool = False) -> dict:
    """Executa a AUDITORIA NACIONAL completa sobre os dados instalados e devolve o laudo:
    {gerado_em, estados, municipios, camadas:{chave:{rotulo,status,feicoes,ufs,...}}, grafo,
     indices, resumo:{dimensoes_ok, dimensoes_parciais, dimensoes_ausentes, nota}}.
    `rapido`=True amostra os pontos das camadas grandes (auditoria mais veloz). Nunca levanta."""
    t0 = time.perf_counter()
    reg = _registry()
    laudo = {"gerado_em": time.strftime("%d/%m/%Y %H:%M"), "camadas": {}}
    try:
        em = cobertura_estados_municipios(reg)
        laudo["estados"], laudo["municipios"] = em["estados"], em["municipios"]
    except Exception:
        laudo["estados"] = {"status": AUSENTE, "pct": 0.0}
        laudo["municipios"] = {"status": AUSENTE, "pct": 0.0}
    bboxes = _bboxes_uf(reg)
    amostra = 150_000 if rapido else None
    for chave, rotulo in CAMADAS_REDE:
        try:
            r = presenca_espacial_uf(reg, chave, bboxes, amostra=amostra)
        except Exception:
            r = {"instalado": reg.existe(chave), "feicoes": 0, "ufs_presentes": [],
                 "ufs_ausentes": sorted(UFS_ESPERADAS), "pct": 0.0}
        r["rotulo"] = rotulo
        r["status"] = _status_rede(r)
        laudo["camadas"][chave] = r
    # Grafo rodoviário (OSRM) — provisionável; presença honesta.
    try:
        laudo["grafo"] = {"instalado": reg.existe("osrm_brasil"),
                          "status": OK if reg.existe("osrm_brasil") else AUSENTE,
                          "nota": "grafo de roteamento (baixável na Central de Dados, ~6,7 GB)"}
    except Exception:
        laudo["grafo"] = {"instalado": False, "status": AUSENTE}
    # Índices/auxiliares embarcados.
    try:
        idx = {}
        for ch in ("rios_nomeados", "hidrografia_nacional", "amazonia_fluvial", "snirh_rios"):
            idx[ch] = reg.existe(ch)
        laudo["indices"] = {"itens": idx, "status": OK if all(idx.values()) else PARCIAL}
    except Exception:
        laudo["indices"] = {"itens": {}, "status": AUSENTE}
    # Resumo honesto das dimensões.
    dims = [laudo["estados"]["status"], laudo["municipios"]["status"]] \
        + [c["status"] for c in laudo["camadas"].values()] \
        + [laudo["grafo"]["status"], laudo["indices"]["status"]]
    laudo["resumo"] = {
        "dimensoes": len(dims),
        "ok": sum(1 for s in dims if s == OK),
        "parciais": sum(1 for s in dims if s == PARCIAL),
        "ausentes": sum(1 for s in dims if s == AUSENTE),
        "nota": "números derivados dos dados instalados; presença por UF é espacial (bbox), aproximada",
        "ms": round((time.perf_counter() - t0) * 1000.0, 1),
    }
    return laudo


# ---------------------------------------------------------------------------
# Renderização (texto para CLI/painel; Markdown para o Relatório — §66).
# ---------------------------------------------------------------------------
def _barra(pct: float, larg: int = 20) -> str:
    try:
        cheio = int(round(larg * max(0.0, min(100.0, float(pct))) / 100.0))
    except Exception:
        cheio = 0
    return "█" * cheio + "░" * (larg - cheio)


def render_texto(laudo: dict) -> str:
    e, m = laudo.get("estados", {}), laudo.get("municipios", {})
    L = ["AUDITORIA NACIONAL — OpenRotas", "=" * 52,
         "gerado em %s" % laudo.get("gerado_em", "?"), ""]
    L.append("Estados (UFs)")
    L.append("  %s %s%%  (%s/%s)" % (_barra(e.get("pct", 0)), e.get("pct", 0),
                                     e.get("encontrado", 0), e.get("esperado", 27)))
    if e.get("ausentes"):
        L.append("  ausentes: %s" % ", ".join(e["ausentes"]))
    L.append("")
    L.append("Municípios")
    L.append("  %s %s%%  (%s / %s oficiais)" % (_barra(m.get("pct", 0)), m.get("pct", 0),
                                                m.get("encontrado", 0), m.get("oficial", MUNICIPIOS_OFICIAIS)))
    extra = (m.get("encontrado", 0) or 0) - MUNICIPIOS_OFICIAIS
    if extra > 0:
        L.append("  (+%d — inclui o Distrito Estadual de Fernando de Noronha)" % extra)
    L.append("")
    L.append("Camadas (feições / presença espacial por UF — aproximada):")
    for chave, c in laudo.get("camadas", {}).items():
        marca = {"OK": "✓", "PARCIAL": "◐", "AUSENTE": "✗"}.get(c["status"], "?")
        if c["instalado"]:
            L.append("  %s %-26s %7d feições · UFs %2d/27 (%.0f%%)"
                     % (marca, c["rotulo"], c["feicoes"], len(c["ufs_presentes"]), c["pct"]))
        else:
            L.append("  %s %-26s ausente" % (marca, c["rotulo"]))
    g = laudo.get("grafo", {})
    L.append("")
    L.append("Grafo rodoviário (OSRM): %s" % ("instalado ✓" if g.get("instalado") else "ausente (baixável)"))
    idx = laudo.get("indices", {}).get("itens", {})
    L.append("Índices/auxiliares: %s" % ", ".join("%s%s" % (k, "✓" if v else "✗") for k, v in idx.items()))
    r = laudo.get("resumo", {})
    L.append("")
    L.append("Resumo: %s dimensões → %s OK · %s parciais · %s ausentes"
             % (r.get("dimensoes", "?"), r.get("ok", "?"), r.get("parciais", "?"), r.get("ausentes", "?")))
    L.append("Nota honesta: %s" % r.get("nota", ""))
    return "\n".join(L)


def gerar_relatorio_md(laudo: dict, caminho) -> str | None:
    """Escreve o 'Relatório de Cobertura Nacional' (§66) em Markdown a partir do laudo. Devolve o
    caminho ou None. Números reais; lacunas documentadas (§40). Nunca levanta."""
    try:
        e, m = laudo.get("estados", {}), laudo.get("municipios", {})
        out = ["# Relatório de Cobertura Nacional — OpenRotas", "",
               "_Gerado em %s — números derivados dos dados efetivamente instalados._" % laudo.get("gerado_em", "?"),
               "", "## 1. Resumo"]
        r = laudo.get("resumo", {})
        out.append("- Dimensões auditadas: **%s** — %s OK, %s parciais, %s ausentes."
                   % (r.get("dimensoes", "?"), r.get("ok", "?"), r.get("parciais", "?"), r.get("ausentes", "?")))
        out.append("- Estados: **%s/27** (%s%%). Municípios: **%s** / %s oficiais (%s%%)."
                   % (e.get("encontrado", 0), e.get("pct", 0), m.get("encontrado", 0),
                      m.get("oficial", MUNICIPIOS_OFICIAIS), m.get("pct", 0)))
        out += ["", "## 2. Estados (UFs)"]
        out.append("Presentes (%d): %s" % (e.get("encontrado", 0), ", ".join(e.get("presentes", [])) or "—"))
        if e.get("ausentes"):
            out.append("**Lacuna** — UFs ausentes: %s" % ", ".join(e["ausentes"]))
        out += ["", "## 3. Municípios por UF"]
        out.append("| UF | Municípios |")
        out.append("|----|-----------:|")
        for uf, n in (m.get("por_uf") or {}).items():
            out.append("| %s | %d |" % (uf, n))
        out += ["", "## 4. Camadas geoespaciais (feições e presença por UF)"]
        out.append("| Camada | Status | Feições | UFs com presença |")
        out.append("|--------|:------:|--------:|:----------------:|")
        for chave, c in laudo.get("camadas", {}).items():
            out.append("| %s | %s | %s | %d/27 |"
                       % (c["rotulo"], c["status"], (c["feicoes"] if c["instalado"] else "—"),
                          len(c["ufs_presentes"])))
        out += ["", "## 5. Grafo rodoviário (roteamento)"]
        g = laudo.get("grafo", {})
        out.append("- OSRM Brasil: **%s**. %s" % ("instalado" if g.get("instalado") else "ausente",
                                                   g.get("nota", "")))
        out += ["", "## 6. Lacunas e honestidade"]
        lac = []
        if e.get("ausentes"):
            lac.append("UFs ausentes na base de municípios: %s" % ", ".join(e["ausentes"]))
        for chave, c in laudo.get("camadas", {}).items():
            if c["status"] != OK:
                if not c["instalado"]:
                    lac.append("%s: camada ausente (não instalada)." % c["rotulo"])
                elif c["ufs_ausentes"]:
                    lac.append("%s: sem presença espacial detectada em %s."
                               % (c["rotulo"], ", ".join(c["ufs_ausentes"])))
        out += (["- " + x for x in lac] if lac else ["- Nenhuma lacuna crítica detectada nas camadas instaladas."])
        out.append("")
        out.append("> Presença por UF é medida por caixa envolvente (bbox) do ponto representativo "
                   "de cada feição — método aproximado, assumido explicitamente. Nenhum dado foi "
                   "fabricado para atingir 100%.")
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[AUDIT] falha ao gerar o relatório.", exc_info=True)
        return None


def resumo_curto(laudo: dict) -> str:
    """Uma linha para a Central de Recursos/diagnóstico."""
    e, m = laudo.get("estados", {}), laudo.get("municipios", {})
    r = laudo.get("resumo", {})
    return ("UFs %s/27 · municípios %s · %s/%s dimensões OK"
            % (e.get("encontrado", 0), m.get("encontrado", 0), r.get("ok", "?"), r.get("dimensoes", "?")))


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    laudo = auditar(rapido=("--rapido" in argv))
    print(render_texto(laudo))
    if "--relatorio" in argv:
        try:
            import desktop_config as cfg
            destino = cfg.ensure_user_dirs()["exports"] / "relatorio_cobertura_nacional.md"
        except Exception:
            destino = Path("relatorio_cobertura_nacional.md")
        got = gerar_relatorio_md(laudo, destino)
        print("\nRelatório salvo em: %s" % got if got else "\nFalha ao salvar o relatório.")
    # código de saída: 0 se nenhuma dimensão essencial ausente; 1 caso contrário.
    essenciais_ok = laudo.get("estados", {}).get("status") != AUSENTE \
        and laudo.get("municipios", {}).get("status") != AUSENTE
    return 0 if essenciais_ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
