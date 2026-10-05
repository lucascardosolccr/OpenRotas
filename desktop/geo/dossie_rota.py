# -*- coding: utf-8 -*-
"""OpenRotas Desktop — DOSSIÊ DE ROTA: integração TOTAL dos dados nacionais (§27/§28/§29/§30/§76).

Dado um par origem→destino (ou uma polilinha), reúne num ÚNICO laudo TODA a inteligência que as
bases instaladas permitem — o "máximo de informações das rotas, origens e destinos":

  • Origem/Destino: município + UF (vizinho mais próximo na base IBGE) + referência hidrográfica;
  • Municípios/UFs atravessados no corredor;
  • Hidrografia: rios cruzados (quantos trechos, rios nomeados, navegáveis, regimes) — §29;
  • Transposições: pontes e travessias/balsas no corredor;
  • Aquaviário: hidrovias, eclusas, atracadouros, portos no corredor;
  • Ferroviário: cruzamentos;
  • Massas d'água no corredor;
  • Multimodal: resumo por classe (§8);
  • Alertas: rota depende de travessia? cruza muitos rios? (sinais de complexidade — §27);
  • Fontes: procedência das camadas usadas (rastreabilidade — §70).

Integra o GeoIntelligenceRepository (consulta espacial), o catálogo de fontes e, quando houver,
a telemetria local. Puro/defensivo: nunca levanta; cada bloco degrada sozinho. Nível bbox/corredor,
honestamente aproximado. Entrega dict + texto + HTML (Dossiê da Rota)."""
from __future__ import annotations

import sys
import html
import math
import time
import logging
import unicodedata
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.dossie")

_GRAU_KM = 111.0
_NOME_NORM_CACHE: dict = {}       # id(df) -> Série de nomes normalizados (base única de municípios)


def _repo():
    from geo import repositorio
    return repositorio.GeoIntelligenceRepository()


def _reg():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _col(df, *nomes):
    """Primeira coluna existente dentre `nomes` (nomes de coluna variam entre gerações)."""
    for n in nomes:
        if n in df.columns:
            return n
    return None


def _normalizar(s) -> str:
    """Normaliza para busca: sem acento, minúsculo, espaços colapsados."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


_UF_SIGLAS = {"ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg",
              "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc", "sp", "se", "to"}


def _parse_local(texto):
    """'Cidade/UF' | 'Cidade, UF' | 'Cidade - UF' | 'Cidade' → (nome_norm, uf_or_None)."""
    t = str(texto or "").strip()
    uf = None
    for sep in ("/", ",", " - ", "-"):
        if sep in t:
            a, b = t.rsplit(sep, 1)
            if _normalizar(b) in _UF_SIGLAS:
                return _normalizar(a), _normalizar(b).upper()
    # UF solta no fim? ("São Paulo SP")
    toks = t.split()
    if len(toks) >= 2 and _normalizar(toks[-1]) in _UF_SIGLAS:
        return _normalizar(" ".join(toks[:-1])), _normalizar(toks[-1]).upper()
    return _normalizar(t), uf


def resolver_local(texto, reg=None) -> dict:
    """Resolve um nome de cidade (com ou sem UF) para coordenada via a base de municípios IBGE.
    {ok, lon, lat, nome, uf, ambiguo, candidatos}. Desambigua por UF quando informada; sem UF e com
    homônimos, escolhe o 1º e marca ambiguo com a lista. Nunca levanta; {ok:False} se não achar."""
    try:
        from audit import coverage_auditor as ca
        reg = reg or _reg()
        nome_q, uf_q = _parse_local(texto)
        if not nome_q:
            return {"ok": False, "detalhe": "nome vazio"}
        df = reg.carregar_parquet("municipios", colunas=["lon", "lat", "nome", "geocodigo"])
        # nomes normalizados (cache por id do df — carregar_parquet reusa o mesmo objeto).
        chave = id(df)
        norm = _NOME_NORM_CACHE.get(chave)
        if norm is None:
            norm = df["nome"].astype(str).map(_normalizar)
            _NOME_NORM_CACHE.clear()               # mantém no máx. 1 entrada (base única)
            _NOME_NORM_CACHE[chave] = norm
        sub = df[norm.values == nome_q]
        if len(sub) == 0:
            return {"ok": False, "detalhe": "cidade não encontrada: %s" % texto, "candidatos": []}
        gc = sub["geocodigo"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
        ufs = [ca.UF_POR_CODIGO.get(int(c[:2])) for c in gc]
        cand = [{"nome": str(sub["nome"].iloc[i]), "uf": ufs[i],
                 "lon": float(sub["lon"].iloc[i]), "lat": float(sub["lat"].iloc[i])}
                for i in range(len(sub))]
        if uf_q:
            cand_uf = [c for c in cand if c["uf"] == uf_q]
            if cand_uf:
                cand = cand_uf
        escolhido = cand[0]
        return {"ok": True, "lon": escolhido["lon"], "lat": escolhido["lat"],
                "nome": escolhido["nome"], "uf": escolhido["uf"],
                "ambiguo": len(cand) > 1, "candidatos": cand}
    except Exception:
        logger.warning("[DOSSIE] resolução de %r falhou.", texto, exc_info=True)
        return {"ok": False, "detalhe": "erro ao resolver"}


def dossie_por_nomes(locais, folga_km: float = 3.0):
    """Dossiê a partir de NOMES de cidade (lista ou 'A;B;C'). Resolve cada um e chama dossie().
    Devolve (dossie_dict, resolucoes). Nunca levanta."""
    if isinstance(locais, str):
        locais = [x for x in locais.split(";") if x.strip()]
    resol = [resolver_local(x) for x in (locais or [])]
    coords = [(r["lon"], r["lat"]) for r in resol if r.get("ok")]
    if not coords:
        return {"erro": "nenhuma cidade resolvida", "resolucoes": resol}, resol
    dd = dossie(coords, folga_km=folga_km)
    dd["locais"] = [{"consulta": q, "resolvido": (r.get("nome"), r.get("uf")) if r.get("ok") else None,
                     "ok": r.get("ok"), "ambiguo": r.get("ambiguo", False)}
                    for q, r in zip(locais, resol)]
    return dd, resol


def _municipio_proximo(reg, lon, lat) -> dict:
    """Município IBGE mais próximo do ponto (centroide lon/lat). {nome, uf, geocodigo, dist_km}."""
    try:
        import numpy as np
        from audit import coverage_auditor as ca
        df = reg.carregar_parquet("municipios", colunas=["lon", "lat", "nome", "geocodigo"])
        dlon = df["lon"].to_numpy(dtype="float64") - lon
        dlat = df["lat"].to_numpy(dtype="float64") - lat
        d2 = dlon * dlon + dlat * dlat
        i = int(np.argmin(d2))
        gc = str(df["geocodigo"].iloc[i])
        uf = None
        try:
            uf = ca.UF_POR_CODIGO.get(int(gc.zfill(7)[:2]))
        except Exception:
            uf = None
        return {"nome": str(df["nome"].iloc[i]), "uf": uf or "?", "geocodigo": gc,
                "dist_km": round(float(math.sqrt(d2[i])) * _GRAU_KM, 1)}
    except Exception:
        logger.warning("[DOSSIE] município próximo falhou.", exc_info=True)
        return {"nome": "?", "uf": "?", "geocodigo": "", "dist_km": None}


def _ref_hidrografica(reg, lon, lat) -> dict:
    """Rio nomeado mais próximo (índice rios_nomeados). {nome, dist_km} ou {} se indisponível."""
    try:
        import numpy as np
        if not reg.existe("rios_nomeados"):
            return {}
        df = reg.carregar_parquet("rios_nomeados", colunas=["lat", "lon", "nome"])
        dlon = df["lon"].to_numpy(dtype="float64") - lon
        dlat = df["lat"].to_numpy(dtype="float64") - lat
        d2 = dlon * dlon + dlat * dlat
        i = int(np.argmin(d2))
        return {"nome": str(df["nome"].iloc[i]), "dist_km": round(float(math.sqrt(d2[i])) * _GRAU_KM, 1)}
    except Exception:
        return {}


def _estacao_proxima(lon, lat) -> dict:
    """Estação de telemetria local mais próxima, SE houver inventário local (telemetry store).
    Integra a telemetria ao dossiê (§30). {} quando não há inventário — honesto, sem inventar."""
    try:
        import math as _m
        sys.path.insert(0, str(_AQUI.parent / "telemetry"))
        import ana_incremental as tel
        regs = tel.TelemetryStore().listar("estacoes")
        if not regs:
            return {}
        melhor, md = None, None
        for r in regs:
            try:
                rlat = float(r.get("lat") or r.get("latitude"))
                rlon = float(r.get("lon") or r.get("longitude"))
            except Exception:
                continue
            d = (rlon - lon) ** 2 + (rlat - lat) ** 2
            if md is None or d < md:
                md, melhor = d, r
        if melhor is None:
            return {}
        nome = melhor.get("nome") or melhor.get("estacao") or melhor.get("codigo") or "?"
        return {"estacao": str(nome), "dist_km": round(_m.sqrt(md) * _GRAU_KM, 1)}
    except Exception:
        return {}


def _idx_corredor(repo, camada, coords, folga_graus):
    """Índices (np.ndarray) das feições da camada no corredor (união por trecho). [] se vazio."""
    import numpy as np
    acc = None
    trechos = list(zip(coords[:-1], coords[1:])) or [(coords[0], coords[0])]
    for (lon0, lat0), (lon1, lat1) in trechos:
        idx = repo.intersecta_bbox(camada, min(lon0, lon1) - folga_graus, min(lat0, lat1) - folga_graus,
                                   max(lon0, lon1) + folga_graus, max(lat0, lat1) + folga_graus)
        acc = idx if acc is None else np.union1d(acc, idx)
    return acc if acc is not None else np.empty(0, dtype="int64")


def _detalhe_rios(repo, reg, idx) -> dict:
    """A partir dos índices de drenagem no corredor, extrai nomes/navegabilidade/regime (§29)."""
    out = {"trechos": int(getattr(idx, "size", 0)), "navegaveis": 0, "rios_nomeados": [], "regimes": {}}
    if getattr(idx, "size", 0) == 0:
        return out
    try:
        import numpy as np
        df = repo.atributos("drenagem", ["nome", "navegavel", "regime"])
        if df is None:
            return out
        sub = df.iloc[idx]
        cnav = _col(sub, "navegavel")
        if cnav:
            vals = sub[cnav].astype(str).str.lower()
            out["navegaveis"] = int(vals.isin(["sim", "s", "true", "1", "navegável", "navegavel"]).sum())
        cnome = _col(sub, "nome")
        if cnome:
            nomes = sub[cnome].dropna().astype(str)
            nomes = nomes[nomes.str.strip() != ""]
            vc = nomes.value_counts().head(15)
            out["rios_nomeados"] = [{"nome": k, "trechos": int(v)} for k, v in vc.items()]
        creg = _col(sub, "regime")
        if creg:
            out["regimes"] = {str(k): int(v) for k, v in sub[creg].dropna().astype(str).value_counts().head(6).items()}
    except Exception:
        logger.warning("[DOSSIE] detalhe de rios falhou.", exc_info=True)
    return out


def _municipios_corredor(repo, reg, coords, folga_graus) -> dict:
    """Municípios/UFs cujo centroide cai no corredor (aproximado). {n_municipios, ufs:[...]}."""
    try:
        import numpy as np
        from audit import coverage_auditor as ca
        idx = _idx_corredor(repo, "municipios", coords, folga_graus)
        if idx.size == 0:
            return {"n_municipios": 0, "ufs": []}
        df = repo.atributos("municipios", ["geocodigo"])
        gc = df["geocodigo"].iloc[idx].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
        ufs = sorted(set(ca.UF_POR_CODIGO.get(int(c[:2])) for c in gc if c[:2].isdigit()) - {None})
        return {"n_municipios": int(idx.size), "ufs": ufs}
    except Exception:
        return {"n_municipios": 0, "ufs": []}


def dossie(coords, folga_km: float = 3.0) -> dict:
    """Monta o DOSSIÊ completo da rota. `coords`=[(lon,lat),...] (≥1 ponto). Nunca levanta."""
    t0 = time.perf_counter()
    repo, reg = _repo(), _reg()
    coords = [tuple(map(float, c)) for c in (coords or [])]
    if not coords:
        return {"erro": "rota vazia"}
    folga = max(0.0, float(folga_km)) / _GRAU_KM
    o, d = coords[0], coords[-1]
    dd = {
        "gerado_em": time.strftime("%d/%m/%Y %H:%M"),
        "pontos": len(coords),
        "origem": {"lon": o[0], "lat": o[1], "municipio": _municipio_proximo(reg, *o),
                   "referencia_hidrografica": _ref_hidrografica(reg, *o),
                   "estacao_telemetria": _estacao_proxima(*o)},
        "destino": {"lon": d[0], "lat": d[1], "municipio": _municipio_proximo(reg, *d),
                    "referencia_hidrografica": _ref_hidrografica(reg, *d),
                    "estacao_telemetria": _estacao_proxima(*d)},
        "corredor": {"folga_km": folga_km},
        "camadas": {}, "alertas": [], "fontes": {},
    }
    # Contagens por camada no corredor.
    from geo import repositorio as _r
    for cam in _r.MODAIS:
        idx = _idx_corredor(repo, cam, coords, folga) if repo.disponivel(cam) else None
        dd["camadas"][cam] = {"feicoes": int(idx.size) if idx is not None else 0,
                              "disponivel": bool(repo.disponivel(cam))}
        dd["camadas"][cam]["_idx"] = idx  # uso interno
    # Detalhe hidrográfico (§29).
    dd["hidrografia"] = _detalhe_rios(repo, reg, dd["camadas"].get("drenagem", {}).get("_idx")
                                      if dd["camadas"].get("drenagem", {}).get("_idx") is not None
                                      else __import__("numpy").empty(0, dtype="int64"))
    # Municípios/UFs atravessados.
    dd["travessia_territorial"] = _municipios_corredor(repo, reg, coords, folga)
    # Multimodal por classe.
    try:
        dd["multimodal"] = repo.analise_multimodal_rota(coords, folga_km=folga_km)["por_classe"]
    except Exception:
        dd["multimodal"] = {}
    # Alertas de complexidade (§27).
    pontes = dd["camadas"].get("pontes", {}).get("feicoes", 0)
    travessias = dd["camadas"].get("travessias", {}).get("feicoes", 0)
    rios = dd["hidrografia"].get("trechos", 0)
    if travessias > 0:
        dd["alertas"].append("Rota no corredor de %d travessia(s)/balsa(s) — possível dependência aquática." % travessias)
    if rios > 0:
        dd["alertas"].append("Corredor cruza %d trecho(s) de drenagem (%d navegável(is))."
                             % (rios, dd["hidrografia"].get("navegaveis", 0)))
    if pontes > 0:
        dd["alertas"].append("%d ponte(s) no corredor." % pontes)
    # Fontes/procedência (rastreabilidade).
    try:
        from catalog import fontes as _f
        cat = {r["chave"]: r for r in _f.catalogo(medir=False)}
        for cam in ("drenagem", "rodovias", "pontes", "travessias", "hidrovias"):
            if cam in cat:
                dd["fontes"][cam] = {"organizacao": cat[cam]["organizacao"], "licenca": cat[cam]["licenca"]}
    except Exception:
        pass
    # limpeza dos índices internos (não serializáveis de forma útil)
    for cam in dd["camadas"]:
        dd["camadas"][cam].pop("_idx", None)
    dd["ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    return dd


def render_texto(dd: dict) -> str:
    if dd.get("erro"):
        return "Dossiê indisponível: %s" % dd["erro"]
    o, d = dd["origem"], dd["destino"]
    L = ["DOSSIÊ DA ROTA — OpenRotas", "=" * 60,
         "Origem:  %s/%s  (%.4f, %.4f)" % (o["municipio"]["nome"], o["municipio"]["uf"], o["lon"], o["lat"]),
         "Destino: %s/%s  (%.4f, %.4f)" % (d["municipio"]["nome"], d["municipio"]["uf"], d["lon"], d["lat"])]
    tt = dd.get("travessia_territorial", {})
    if tt.get("ufs"):
        L.append("UFs no corredor: %s (%d municípios)" % (", ".join(tt["ufs"]), tt.get("n_municipios", 0)))
    h = dd.get("hidrografia", {})
    L.append("")
    L.append("Hidrografia: %d trechos de rio no corredor · %d navegáveis" % (h.get("trechos", 0), h.get("navegaveis", 0)))
    if h.get("rios_nomeados"):
        L.append("  Principais rios: " + ", ".join("%s(%d)" % (r["nome"], r["trechos"]) for r in h["rios_nomeados"][:8]))
    cam = dd.get("camadas", {})
    L.append("Transposições: %d ponte(s) · %d travessia(s)/balsa(s)"
             % (cam.get("pontes", {}).get("feicoes", 0), cam.get("travessias", {}).get("feicoes", 0)))
    L.append("Aquaviário: %d hidrovia(s) · %d eclusa(s) · %d porto(s)"
             % (cam.get("hidrovias", {}).get("feicoes", 0), cam.get("eclusas", {}).get("feicoes", 0),
                cam.get("complexos_portuarios", {}).get("feicoes", 0)))
    L.append("Ferroviário: %d cruzamento(s)" % cam.get("ferrovias", {}).get("feicoes", 0))
    if dd.get("alertas"):
        L.append("")
        L.append("Alertas:")
        for a in dd["alertas"]:
            L.append("  • " + a)
    L.append("")
    L.append("(corredor ±%s km, nível bbox aproximado; %s ms)" % (dd["corredor"]["folga_km"], dd.get("ms", "?")))
    return "\n".join(L)


_CSS_DOSSIE = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a2230;--muted:#5b6676;--line:#e6e9ef;--accent:#1f6feb;
  --ok:#1a7f4b;--warn:#9a6700;--chip:#eef2f7}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;--accent:#4a9eff;
  --ok:#3fb950;--warn:#d29922;--chip:#1c232c}}
:root[data-theme="dark"]{--bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;
  --accent:#4a9eff;--ok:#3fb950;--warn:#d29922;--chip:#1c232c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.55}
.wrap{max-width:900px;margin:0 auto;padding:32px 16px 56px}
h1{font-size:1.5rem;margin:0 0 2px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 20px;font-size:.9rem}
.rota{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:1.05rem;font-weight:600;margin-bottom:6px}
.seta{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:0 0 16px}
.card h2{font-size:1.05rem;margin:0 0 10px}
.kpis{display:flex;flex-wrap:wrap;gap:12px}
.kpi{flex:1 1 150px;background:var(--chip);border-radius:10px;padding:12px 14px}
.kpi .v{font-size:1.4rem;font-weight:700;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--muted);font-size:.78rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.03em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.alerta{background:var(--chip);border-left:3px solid var(--warn);padding:8px 12px;border-radius:0 8px 8px 0;margin:6px 0}
.empty{color:var(--muted);font-style:italic}
footer{color:var(--muted);font-size:.78rem;margin-top:10px;text-align:center}
"""


def _ponto_html(p, titulo):
    m = p.get("municipio", {})
    ref = p.get("referencia_hidrografica") or {}
    est = p.get("estacao_telemetria") or {}
    linhas = ["<div class='kpi'><div class='l'>%s</div><div class='v'>%s</div><div class='l'>%s</div></div>"
              % (titulo, html.escape(str(m.get("nome", "?"))), html.escape(str(m.get("uf", "?"))))]
    if ref.get("nome"):
        linhas.append("<div class='kpi'><div class='l'>Ref. hidrográfica</div><div>%s</div><div class='l'>%s km</div></div>"
                      % (html.escape(str(ref["nome"])), ref.get("dist_km", "?")))
    if est.get("estacao"):
        linhas.append("<div class='kpi'><div class='l'>Estação telemétrica</div><div>%s</div><div class='l'>%s km</div></div>"
                      % (html.escape(str(est["estacao"])), est.get("dist_km", "?")))
    return "".join(linhas)


def gerar_html(dd: dict, caminho) -> str | None:
    """Escreve o Dossiê da Rota como HTML autossuficiente (tema claro/escuro, pronto p/ imprimir→PDF)."""
    try:
        if dd.get("erro"):
            return None
        o, d = dd["origem"], dd["destino"]
        h = dd.get("hidrografia", {})
        cam = dd.get("camadas", {})
        tt = dd.get("travessia_territorial", {})
        P = ["<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>Dossiê da Rota — OpenRotas</title><style>", _CSS_DOSSIE, "</style></head><body><div class='wrap'>",
             "<h1>Dossiê da Rota</h1><p class='sub'>Integração nacional de dados · gerado em %s</p>"
             % html.escape(dd.get("gerado_em", "")),
             "<div class='rota'>%s/%s <span class='seta'>→</span> %s/%s</div>"
             % (html.escape(str(o["municipio"]["nome"])), html.escape(str(o["municipio"]["uf"])),
                html.escape(str(d["municipio"]["nome"])), html.escape(str(d["municipio"]["uf"]))),
             "<section class='card'><h2>Origem e destino</h2><div class='kpis'>",
             _ponto_html(o, "Origem"), _ponto_html(d, "Destino"), "</div>"]
        if tt.get("ufs"):
            P.append("<p class='sub'>Corredor atravessa %s (%d municípios).</p>"
                     % (", ".join(tt["ufs"]), tt.get("n_municipios", 0)))
        P.append("</section>")
        # Hidrografia
        P.append("<section class='card'><h2>Hidrografia</h2><div class='kpis'>"
                 "<div class='kpi'><div class='v'>%d</div><div class='l'>trechos de rio</div></div>"
                 "<div class='kpi'><div class='v'>%d</div><div class='l'>navegáveis</div></div></div>"
                 % (h.get("trechos", 0), h.get("navegaveis", 0)))
        if h.get("rios_nomeados"):
            P.append("<table><thead><tr><th>Rio</th><th class='num'>trechos</th></tr></thead><tbody>")
            for r in h["rios_nomeados"]:
                P.append("<tr><td>%s</td><td class='num'>%d</td></tr>" % (html.escape(str(r["nome"])), r["trechos"]))
            P.append("</tbody></table>")
        P.append("</section>")
        # Camadas no corredor
        P.append("<section class='card'><h2>Feições no corredor</h2>"
                 "<table><thead><tr><th>Camada</th><th class='num'>feições</th></tr></thead><tbody>")
        for ch, info in cam.items():
            P.append("<tr><td>%s</td><td class='num'>%s</td></tr>"
                     % (html.escape(ch), info.get("feicoes", 0) if info.get("disponivel") else "—"))
        P.append("</tbody></table></section>")
        # Alertas
        if dd.get("alertas"):
            P.append("<section class='card'><h2>Alertas</h2>")
            for a in dd["alertas"]:
                P.append("<div class='alerta'>%s</div>" % html.escape(a))
            P.append("</section>")
        # Fontes
        if dd.get("fontes"):
            P.append("<section class='card'><h2>Fontes (rastreabilidade)</h2><table><tbody>")
            for ch, f in dd["fontes"].items():
                P.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                         % (html.escape(ch), html.escape(str(f.get("organizacao", ""))), html.escape(str(f.get("licenca", "")))))
            P.append("</tbody></table></section>")
        P.append("<footer>Corredor ±%s km, nível bbox aproximado. Dados nacionais locais — nada sai do seu computador.</footer>"
                 % dd["corredor"]["folga_km"])
        P.append("</div></body></html>")
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        pth.write_text("".join(P), encoding="utf-8")
        return str(pth)
    except Exception:
        logger.warning("[DOSSIE] falha ao gerar HTML.", exc_info=True)
        return None


def exportar_excel(dd: dict, caminho) -> str | None:
    """Exporta o dossiê para .xlsx (abas Resumo, Rios, Feições, Fontes). Requer openpyxl (dep)."""
    try:
        if dd.get("erro"):
            return None
        import pandas as pd
        o, d = dd["origem"], dd["destino"]
        h = dd.get("hidrografia", {})
        cam = dd.get("camadas", {})
        tt = dd.get("travessia_territorial", {})
        resumo = [
            ("Origem", "%s/%s" % (o["municipio"]["nome"], o["municipio"]["uf"])),
            ("Destino", "%s/%s" % (d["municipio"]["nome"], d["municipio"]["uf"])),
            ("UFs no corredor", ", ".join(tt.get("ufs", []))),
            ("Municípios no corredor", tt.get("n_municipios", 0)),
            ("Trechos de rio", h.get("trechos", 0)),
            ("Rios navegáveis (trechos)", h.get("navegaveis", 0)),
            ("Pontes", cam.get("pontes", {}).get("feicoes", 0)),
            ("Travessias/balsas", cam.get("travessias", {}).get("feicoes", 0)),
            ("Hidrovias", cam.get("hidrovias", {}).get("feicoes", 0)),
            ("Portos", cam.get("complexos_portuarios", {}).get("feicoes", 0)),
            ("Cruzamentos ferroviários", cam.get("ferrovias", {}).get("feicoes", 0)),
            ("Gerado em", dd.get("gerado_em", "")),
        ]
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(pth), engine="openpyxl") as xw:
            pd.DataFrame(resumo, columns=["Campo", "Valor"]).to_excel(xw, sheet_name="Resumo", index=False)
            rios = h.get("rios_nomeados") or []
            pd.DataFrame(rios or [{"nome": "—", "trechos": 0}]).to_excel(xw, sheet_name="Rios", index=False)
            feic = [{"camada": ch, "feicoes": info.get("feicoes", 0), "disponivel": info.get("disponivel")}
                    for ch, info in cam.items()]
            pd.DataFrame(feic).to_excel(xw, sheet_name="Feicoes", index=False)
            fontes = [{"camada": ch, "organizacao": f.get("organizacao", ""), "licenca": f.get("licenca", "")}
                      for ch, f in (dd.get("fontes") or {}).items()]
            pd.DataFrame(fontes or [{"camada": "—", "organizacao": "", "licenca": ""}]).to_excel(
                xw, sheet_name="Fontes", index=False)
            pd.DataFrame([{"alerta": a} for a in (dd.get("alertas") or [])] or [{"alerta": "—"}]).to_excel(
                xw, sheet_name="Alertas", index=False)
        return str(pth)
    except Exception:
        logger.warning("[DOSSIE] falha ao exportar Excel.", exc_info=True)
        return None


def _parse_coords(texto):
    return [tuple(float(x) for x in par.split(",")) for par in str(texto).split(";") if par.strip()]


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dd = None
    # Modo por NOMES: --rota-nomes "São Paulo/SP;Rio de Janeiro/RJ"
    if "--rota-nomes" in argv:
        i = argv.index("--rota-nomes")
        texto = argv[i + 1] if i + 1 < len(argv) else ""
        dd, resol = dossie_por_nomes(texto)
        for r in resol:
            if not r.get("ok"):
                print("! não resolvido: %s" % r.get("detalhe", "?"))
            elif r.get("ambiguo"):
                print("! '%s/%s' é ambíguo (%d homônimos) — usando o 1º; qualifique com /UF."
                      % (r.get("nome"), r.get("uf"), len(r.get("candidatos", []))))
        if dd.get("erro"):
            print("Dossiê indisponível: %s" % dd["erro"])
            return 2
    else:
        coords = None
        for a in argv:
            if ";" in a and "," in a:
                try:
                    coords = _parse_coords(a)
                except Exception:
                    coords = None
        if not coords:
            print("uso: --dossie \"lon,lat;lon,lat\" | --rota-nomes \"Cidade/UF;Cidade/UF\" [--html] [--excel]")
            return 2
        dd = dossie(coords)
    print(render_texto(dd))
    if "--html" in argv or "--excel" in argv:
        try:
            import desktop_config as cfg
            exp = cfg.ensure_user_dirs()["exports"]
        except Exception:
            exp = Path(".")
        if "--html" in argv:
            got = gerar_html(dd, exp / "dossie_rota.html")
            if got:
                print("\nHTML: %s" % got)
                try:
                    import webbrowser
                    webbrowser.open(Path(got).as_uri())
                except Exception:
                    pass
        if "--excel" in argv:
            got = exportar_excel(dd, exp / "dossie_rota.xlsx")
            print("Excel: %s" % (got or "falha ao exportar"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
