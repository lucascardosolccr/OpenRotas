# -*- coding: utf-8 -*-
"""OpenRotas Desktop — ISÓCRONAS DE ALCANCE (§29): o que é atingível a partir de um centro.

Dado um ponto de origem (cidade/UF ou lon,lat), classifica TODOS os municípios reais do Brasil em
FAIXAS de distância (ex.: ≤100, ≤300, ≤600, ≤1000 km) — respondendo "o que alcanço a partir daqui".

Alcance por padrão ESTIMADO (modo 'estimado'): a linha reta (haversine, offline) dos centroides
municipais é corrigida pelo fator de sinuosidade do web (geo.distancia) — PARIDADE com a aplicação web,
que nunca classifica por linha reta crua. Quando há um MOTOR OSRM local/externo, refina as distâncias
dos candidatos para distância RODOVIÁRIA real (melhor-esforço, em lotes); o restante usa a estimativa.
`estimar=False` (CLI --geodesico) mantém a LINHA RETA pura (modo 'geodesico').

Honesto (§71): a estimativa é declarada no resultado; a linha reta permanece como PISO em `_reta`.
Puro/defensivo (numpy + stdlib): nunca levanta."""
from __future__ import annotations

import sys
import html
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.isocronas")

_R_KM = 6371.0
_FAIXAS_PADRAO = (100, 300, 600, 1000)
# Cores (sequencial, do mais perto ao mais longe) — classes aceitas por tema.mapa_dispersao.
_CLASSES_FAIXA = ["teal", "accent", "warn", "bad"]


def _reg():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _haversine_km(lon0, lat0, lons, lats):
    import numpy as np
    la1 = np.radians(float(lat0))
    la2 = np.radians(lats)
    dla = la2 - la1
    dlo = np.radians(lons - float(lon0))
    a = np.sin(dla / 2.0) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlo / 2.0) ** 2
    return 2.0 * _R_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _resolver_origem(origem, reg):
    """Aceita (lon,lat) | 'lon,lat' | 'Cidade/UF'. Devolve {ok,lon,lat,nome,uf} ou {ok:False}."""
    def _susp(lo, la):
        try:
            from geo import distancia
            return distancia.validar_coordenada_br(lo, la)
        except Exception:
            return []
    try:
        if isinstance(origem, (tuple, list)) and len(origem) >= 2:
            lo, la = float(origem[0]), float(origem[1])
            return {"ok": True, "lon": lo, "lat": la, "nome": "(%.4f, %.4f)" % (lo, la), "uf": "",
                    "coord_suspeita": _susp(lo, la)}
        s = str(origem or "").strip()
        # "lon,lat" numérico?
        if "," in s and "/" not in s:
            try:
                a, b = s.split(",", 1)
                lo, la = float(a), float(b)
                return {"ok": True, "lon": lo, "lat": la, "nome": "(%.4f, %.4f)" % (lo, la), "uf": "",
                        "coord_suspeita": _susp(lo, la)}
            except Exception:
                pass
        from geo import dossie_rota
        r = dossie_rota.resolver_local(s, reg=reg)
        if r.get("ok"):
            # HONESTIDADE: origem homônima (mesmo nome em várias UFs) sem UF → resolver_local pega
            # a 1ª e marca ambiguo. Propagamos para o relatório avisar, em vez de calcular o alcance
            # inteiro a partir da cidade errada em silêncio.
            amb = bool(r.get("ambiguo"))
            ufs_alt = sorted({c.get("uf") for c in r.get("candidatos", []) if c.get("uf")}) if amb else []
            return {"ok": True, "lon": r["lon"], "lat": r["lat"], "nome": r.get("nome", s),
                    "uf": r.get("uf", ""), "ambiguo": amb, "ufs_alt": ufs_alt}
        return {"ok": False, "detalhe": r.get("detalhe", "origem não resolvida")}
    except Exception:
        return {"ok": False, "detalhe": "erro ao resolver origem"}


def _distancias_osrm(olon, olat, lons, lats, url, cap=1500, chunk=90, timeout=20):
    """Melhor-esforço: distância RODOVIÁRIA (km) origem→cada destino via OSRM /table, em lotes.
    Só os `cap` destinos mais próximos (geodésico) são refinados. Devolve array (km, NaN onde não
    refinado) ou None se o motor não responder. Respeita OPENROTAS_NO_NET. Nunca levanta."""
    import os as _os
    if _os.environ.get("OPENROTAS_NO_NET"):
        return None
    if not url:
        return None
    try:
        import numpy as np
        import json
        import urllib.request
        n = len(lons)
        out = np.full(n, np.nan, dtype="float64")
        geod = _haversine_km(olon, olat, lons, lats)
        ordem = np.argsort(geod)[:min(cap, n)]
        base = url.rstrip("/")
        ok_any = False
        for i0 in range(0, len(ordem), chunk):
            ids = ordem[i0:i0 + chunk]
            coords = "%s,%s" % (olon, olat) + "".join(";%s,%s" % (lons[j], lats[j]) for j in ids)
            full = "%s/table/v1/driving/%s?sources=0&annotations=distance" % (base, coords)
            req = urllib.request.Request(full, headers={"User-Agent": "OpenRotas-Desktop"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            if str(d.get("code")) != "Ok":
                return None
            linha = (d.get("distances") or [[]])[0]
            vals = linha[1:] if linha else []
            for k, j in enumerate(ids):
                if k < len(vals) and vals[k] is not None:
                    out[j] = float(vals[k]) / 1000.0
                    ok_any = True
        return out if ok_any else None
    except Exception:
        logger.info("[ISOCRONAS] OSRM /table indisponível; usando geodésico.", exc_info=True)
        return None


def calcular(origem, faixas_km=_FAIXAS_PADRAO, usar_osrm: bool = False, osrm_url=None, reg=None,
             estimar: bool = True) -> dict:
    """Classifica os municípios do Brasil em faixas de distância a partir de `origem`. Devolve
    {ok, origem, modo, faixas_km, bandas:[{ate_km, municipios, ufs, cumulativo, exemplos}],
    total_municipios, alcancados, nota}. Nunca levanta.

    `estimar` (padrão True): sem roteamento viário real (OSRM), estima a distância RODOVIÁRIA a partir
    da linha reta pelo fator de sinuosidade do web (modo 'estimado') em vez de reportar a linha reta crua
    — a paridade com a aplicação web. `estimar=False` mantém a linha reta pura (modo 'geodesico')."""
    base = {"ok": False, "origem": None, "modo": "geodesico", "faixas_km": list(faixas_km),
            "bandas": [], "total_municipios": 0, "alcancados": 0, "nota": ""}
    try:
        import numpy as np
        from audit import coverage_auditor as ca
        reg = reg or _reg()
        o = _resolver_origem(origem, reg)
        if not o.get("ok"):
            base["detalhe"] = o.get("detalhe", "origem inválida")
            return base
        if not reg.existe("municipios"):
            base["detalhe"] = "base de municípios ausente"
            return base
        df = reg.carregar_parquet("municipios", colunas=["lon", "lat", "nome", "geocodigo"])
        lons = df["lon"].to_numpy(dtype="float64")
        lats = df["lat"].to_numpy(dtype="float64")
        nomes = df["nome"].astype(str).tolist()
        ufs = ca._uf_do_geocodigo(df["geocodigo"]).tolist()
        from geo import distancia
        # CONSCIÊNCIA FLUVIAL: municípios de acesso só fluvial/isolado (sem estrada) — recebem o fator
        # de sinuosidade FLUVIAL (~3×), não o rodoviário (uma estrada que não existe).
        fluv_mask = np.array(distancia.mascara_acesso_fluvial(df["geocodigo"].astype(str).tolist()), dtype=bool)
        faixas = sorted(float(f) for f in faixas_km if float(f) > 0)
        if not faixas:
            faixas = list(_FAIXAS_PADRAO)
        modo = "geodesico"
        reta = _haversine_km(o["lon"], o["lat"], lons, lats)   # linha reta (piso físico), sempre preservada
        dist = reta.copy()
        refinados = np.zeros(len(reta), dtype=bool)
        if usar_osrm:
            ref = _distancias_osrm(o["lon"], o["lat"], lons, lats, osrm_url or _osrm_url())
            if ref is not None:
                m = ~np.isnan(ref)
                dist = np.where(m, ref, dist)       # rodoviário real onde o OSRM refinou
                refinados = m
                modo = "rodoviario-parcial"
        if estimar:
            # Células ainda em LINHA RETA (não refinadas pelo OSRM) viram ESTIMATIVA rodoviária — o web
            # nunca reporta a reta crua. A reta permanece em `_reta` como piso. (isocronas.calcular)
            nao_ref = ~refinados
            if bool(nao_ref.any()):
                est = distancia.estimar_rodoviaria_vetor(reta, fluvial=fluv_mask)
                dist = np.where(nao_ref, est, dist)
                if modo == "geodesico":
                    modo = "estimado"
        idx = np.searchsorted(np.array(faixas), dist, side="left")   # 0..len-1 = faixa; len = fora
        bandas = []
        for i, ate in enumerate(faixas):
            sel = np.nonzero(idx == i)[0]
            ufset = sorted({ufs[j] for j in sel.tolist() if isinstance(ufs[j], str)})
            ordem = sel[np.argsort(dist[sel])] if sel.size else sel
            exemplos = ["%s/%s" % (nomes[j], ufs[j] if isinstance(ufs[j], str) else "?")
                        for j in ordem[:5].tolist()]
            # tempo estimado p/ a BORDA da faixa (só quando a distância é rodoviária; da reta pura não).
            tmin = distancia.estimar_tempo_min(ate) if modo != "geodesico" else None
            bandas.append({"ate_km": int(ate), "municipios": int(sel.size),
                           "ufs": ufset, "cumulativo": int(np.count_nonzero(idx <= i)),
                           "exemplos": exemplos, "tempo_min": tmin})
        alcancados = int(np.count_nonzero(idx < len(faixas)))
        fluvial_alcancados = int(np.count_nonzero(fluv_mask & (idx < len(faixas))))
        base.update({
            "ok": True, "origem": o, "modo": modo, "faixas_km": [int(f) for f in faixas],
            "bandas": bandas, "total_municipios": int(len(lons)), "alcancados": alcancados,
            "acesso_fluvial_alcancados": fluvial_alcancados,
            "_dist": dist, "_idx": idx, "_lons": lons, "_lats": lats, "_reta": reta,  # internos p/ o mapa
            "nota": ("Distância %s a partir de %s%s."
                     % (distancia.descricao_modo(modo), o["nome"],
                        ("/" + o["uf"]) if o.get("uf") else "")),
        })
        return base
    except Exception:
        logger.warning("[ISOCRONAS] cálculo falhou.", exc_info=True)
        return base


def _osrm_url():
    try:
        from geo import dossie_rota
        return dossie_rota._osrm_url()
    except Exception:
        return None


def render_texto(r: dict) -> str:
    if not r.get("ok"):
        return "Isócronas indisponíveis: %s" % r.get("detalhe", "erro")
    o = r["origem"]
    from geo import distancia
    L = ["ISÓCRONAS DE ALCANCE — OpenRotas", "=" * 56,
         "origem: %s%s  (%.4f, %.4f)" % (o["nome"], ("/" + o["uf"]) if o.get("uf") else "",
                                         o["lon"], o["lat"]),
         "modo: %s · municípios no país: %d · alcançados (≤%d km): %d" %
         (distancia.rotulo_modo(r["modo"]), r["total_municipios"], r["faixas_km"][-1], r["alcancados"]), ""]
    if o.get("ambiguo"):
        L.append("⚠ origem ambígua: há homônimas em %s — usada a 1ª. Especifique a UF "
                 "(ex.: \"Cidade/UF\") para fixar a correta." % ", ".join(o.get("ufs_alt", [])))
        L.append("")
    if o.get("coord_suspeita"):
        L.append("⚠ coordenada da origem suspeita (verifique a ordem lon,lat / se está no Brasil): %s"
                 % "; ".join(o["coord_suspeita"]))
        L.append("")
    if r.get("acesso_fluvial_alcancados"):
        L.append("🛶 " + distancia.aviso_fluvial(r["acesso_fluvial_alcancados"])
                 + " (alcançados; estimados por rio, por isso caem em faixas mais distantes).")
        L.append("")
    for b in r["bandas"]:
        _dur = distancia.formatar_duracao(b.get("tempo_min"))
        L.append("  ≤ %-5d km%s: %5d municípios · %2d UFs · acum. %d"
                 % (b["ate_km"], (" (≈ %s)" % _dur) if _dur else "",
                    b["municipios"], len(b["ufs"]), b["cumulativo"]))
        if b["exemplos"]:
            L.append("        mais próximos: %s" % ", ".join(b["exemplos"]))
    L.append("")
    L.append(r["nota"])
    return "\n".join(L)


def construir_html(r: dict) -> str:
    try:
        from resources import tema
    except Exception:
        try:
            import tema
        except Exception:
            tema = None
    if not r.get("ok"):
        txt = render_texto(r)
        if tema is None:
            return "<!doctype html><html><head><meta charset='utf-8'></head><body><pre>%s</pre></body></html>" % html.escape(txt)
        return tema.documento("Isócronas de Alcance", "", "<p class='empty'>%s</p>" % html.escape(txt))
    from geo import distancia
    o = r["origem"]
    corpo = ["<section class='card'><h2>Alcance a partir de %s%s</h2><div class='kpis'>"
             % (html.escape(str(o["nome"])), html.escape(("/" + o["uf"]) if o.get("uf") else "")),
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Municípios ≤ %d km</div></div>"
             % (r["alcancados"], r["faixas_km"][-1]),
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Total no país</div></div>" % r["total_municipios"],
             "<div class='kpi'><div class='v'>%s</div><div class='l'>Modo</div></div>"
             % html.escape(distancia.rotulo_modo(r["modo"])),
             "</div>"]
    if o.get("ambiguo"):
        corpo.append("<p class='sub' style='margin:10px 2px 0;color:var(--warn,#b45309)'>"
                     "⚠ Origem ambígua: há homônimas em %s — usada a 1ª. "
                     "Especifique a UF (ex.: \"Cidade/UF\") para fixar a correta.</p>"
                     % html.escape(", ".join(o.get("ufs_alt", [])) or "outras UFs"))
    if o.get("coord_suspeita"):
        corpo.append("<p class='sub' style='margin:10px 2px 0;color:var(--warn,#b45309)'>"
                     "⚠ Coordenada da origem suspeita — verifique a ordem <b>lon,lat</b> e se está no "
                     "Brasil: %s.</p>" % html.escape("; ".join(o["coord_suspeita"])))
    if r.get("acesso_fluvial_alcancados"):
        corpo.append("<p class='sub' style='margin:10px 2px 0;color:var(--warn,#b45309)'>🛶 %s "
                     "(alcançados; estimados por rio, caem em faixas mais distantes).</p>"
                     % html.escape(distancia.aviso_fluvial(r["acesso_fluvial_alcancados"])))
    corpo.append("</section>")
    if tema is not None:
        # Mapa nacional colorido por faixa (anéis de alcance) + origem como waypoint.
        try:
            import numpy as np
            lons = r.get("_lons"); lats = r.get("_lats"); idx = r.get("_idx")
            if lons is not None and idx is not None:
                nf = len(r["faixas_km"])
                cls = []
                for v in idx.tolist():
                    cls.append(_CLASSES_FAIXA[v] if v < nf and v < len(_CLASSES_FAIXA) else None)
                leg = [{"rotulo": "≤ %d km" % r["faixas_km"][i],
                        "cor": {"teal": "var(--teal)", "accent": "var(--accent)",
                                "warn": "var(--warn)", "bad": "var(--bad)"}.get(
                            _CLASSES_FAIXA[i] if i < len(_CLASSES_FAIXA) else "", "var(--muted)")}
                       for i in range(min(nf, len(_CLASSES_FAIXA)))]
                leg.append({"rotulo": "além", "cor": "var(--muted)"})
                m = tema.mapa_dispersao(list(lons), list(lats), classes=cls,
                                        rota=[(o["lon"], o["lat"])],
                                        titulo="ISÓCRONAS — ALCANCE POR FAIXA", legenda=leg)
                if m:
                    corpo.append("<section class='card'><h2>Mapa de alcance</h2>%s</section>" % m)
        except Exception:
            pass
        # Barras: municípios por faixa (com tempo estimado até a borda, quando rodoviário/estimado).
        itens = [{"rotulo": "≤ %d km" % b["ate_km"], "valor": b["municipios"],
                  "classe": _CLASSES_FAIXA[i] if i < len(_CLASSES_FAIXA) else None,
                  "dica": "≤ %d km%s: %d municípios em %d UFs (acum. %d)"
                          % (b["ate_km"],
                             (" (≈ %s)" % distancia.formatar_duracao(b.get("tempo_min")))
                             if distancia.formatar_duracao(b.get("tempo_min")) else "",
                             b["municipios"], len(b["ufs"]), b["cumulativo"])}
                 for i, b in enumerate(r["bandas"])]
        ch = tema.grafico_barras(itens, titulo="MUNICÍPIOS POR FAIXA DE DISTÂNCIA")
        if ch:
            corpo.append("<section class='card'><h2>Municípios por faixa</h2>%s</section>" % ch)
    if tema is None:
        return ("<!doctype html><html><head><meta charset='utf-8'><title>Isócronas — OpenRotas"
                "</title></head><body><pre>%s</pre></body></html>" % html.escape(render_texto(r)))
    return tema.documento("Isócronas de Alcance", r["nota"], "".join(corpo),
                          "Alcance a partir de centroides municipais reais · dados locais.")


def gerar(caminho, r: dict) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(r), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[ISOCRONAS] falha ao gerar HTML.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    usar_osrm = "--osrm" in argv
    estimar = "--geodesico" not in argv   # --geodesico força a linha reta pura (sem estimativa de sinuosidade)
    faixas = _FAIXAS_PADRAO
    origem = None
    for a in argv:
        if a.startswith("--faixas="):
            try:
                faixas = tuple(int(x) for x in a.split("=", 1)[1].split(",") if x.strip())
            except Exception:
                pass
        elif not a.startswith("--"):
            origem = a
    if not origem:
        print('uso: --isocronas "Cidade/UF" | "lon,lat" [--faixas=100,300,600,1000] [--osrm] [--geodesico] [--html]')
        return 2
    r = calcular(origem, faixas_km=faixas, usar_osrm=usar_osrm, estimar=estimar)
    print(render_texto(r))
    if r.get("ok") and "--html" in argv:
        try:
            import desktop_config as cfg
            destino = cfg.ensure_user_dirs()["exports"] / "isocronas.html"
        except Exception:
            destino = Path("isocronas.html")
        got = gerar(destino, r)
        if got:
            print("\nHTML: %s" % got)
            try:
                import webbrowser
                webbrowser.open(Path(got).as_uri())
            except Exception:
                pass
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
