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
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.dossie")

_GRAU_KM = 111.0


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


def _parse_coords(texto):
    return [tuple(float(x) for x in par.split(",")) for par in str(texto).split(";") if par.strip()]


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    coords = None
    for a in argv:
        if ";" in a and "," in a:
            try:
                coords = _parse_coords(a)
            except Exception:
                coords = None
    if not coords:
        print("uso: --dossie \"lon,lat;lon,lat[;...]\"  (ex.: -46.63,-23.55;-43.20,-22.90)")
        return 2
    print(render_texto(dossie(coords)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
