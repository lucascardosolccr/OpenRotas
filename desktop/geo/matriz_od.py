# -*- coding: utf-8 -*-
"""OpenRotas Desktop — MATRIZ ORIGEM↔DESTINO (§29): distâncias entre vários centros.

Dado um conjunto de locais (Cidade/UF ou lon,lat), monta a MATRIZ NxN de distâncias entre todos
os pares — base para planejar alocação entre múltiplos centros ("qual par é o mais distante?",
"quão perto estão entre si?").

Distância por padrão ESTIMADA (modo 'estimado'): linha reta (haversine, offline) corrigida pelo fator
de sinuosidade do web (geo.distancia) — PARIDADE com a aplicação web, que nunca reporta a reta crua.
Com motor OSRM local/externo (--osrm) refina para distância RODOVIÁRIA real via /table (matriz completa
numa só chamada, melhor-esforço). `--geodesico` força a linha reta pura (modo 'geodesico'). Entrega
dict + texto + HTML (heatmap da matriz + KPIs) + Excel. Puro/defensivo (numpy + stdlib): nunca levanta."""
from __future__ import annotations

import sys
import html
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.matriz")


def _reg():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _suspeita_coord(lon, lat):
    """Motivos de suspeita (troca lat/lon, fora do Brasil, (0,0)) para uma coordenada CRUA do usuário —
    via geo.distancia (paridade com _validar_centroide_br do web). [] quando plausível. Nunca levanta."""
    try:
        from geo import distancia
        return distancia.validar_coordenada_br(lon, lat)
    except Exception:
        return []


def _resolver_ponto(tok, reg):
    """'lon,lat' | 'Cidade/UF' | (lon,lat) → {ok,lon,lat,nome,uf[,coord_suspeita]}."""
    try:
        if isinstance(tok, (tuple, list)) and len(tok) >= 2:
            lo, la = float(tok[0]), float(tok[1])
            return {"ok": True, "lon": lo, "lat": la, "nome": "(%.3f,%.3f)" % (lo, la), "uf": "",
                    "coord_suspeita": _suspeita_coord(lo, la)}
        s = str(tok or "").strip()
        if "," in s and "/" not in s:
            try:
                a, b = s.split(",", 1)
                lo, la = float(a), float(b)
                return {"ok": True, "lon": lo, "lat": la, "nome": "(%.3f,%.3f)" % (lo, la), "uf": "",
                        "coord_suspeita": _suspeita_coord(lo, la)}
            except Exception:
                pass
        from geo import dossie_rota
        r = dossie_rota.resolver_local(s, reg=reg)
        if r.get("ok"):
            # HONESTIDADE: homônimos (mesmo nome em várias UFs) sem UF informada → resolver_local
            # escolhe o 1º e marca ambiguo. Propagamos o aviso para o relatório não computar uma
            # matriz inteira para a cidade errada em silêncio; o usuário vê e pode especificar a UF.
            amb = bool(r.get("ambiguo"))
            ufs_alt = sorted({c.get("uf") for c in r.get("candidatos", []) if c.get("uf")}) if amb else []
            return {"ok": True, "lon": r["lon"], "lat": r["lat"],
                    "nome": r.get("nome", s), "uf": r.get("uf", ""),
                    "ambiguo": amb, "ufs_alt": ufs_alt}
        return {"ok": False, "consulta": s, "detalhe": r.get("detalhe", "não resolvido")}
    except Exception:
        return {"ok": False, "consulta": str(tok), "detalhe": "erro"}


def _matriz_osrm(lons, lats, url, timeout=25):
    """Matriz RODOVIÁRIA completa (km) via OSRM /table (uma chamada). None em falha. Respeita
    OPENROTAS_NO_NET. Nunca levanta."""
    import os as _os
    if _os.environ.get("OPENROTAS_NO_NET") or not url:
        return None
    try:
        import json
        import urllib.request
        coords = ";".join("%s,%s" % (lo, la) for lo, la in zip(lons, lats))
        full = "%s/table/v1/driving/%s?annotations=distance" % (url.rstrip("/"), coords)
        req = urllib.request.Request(full, headers={"User-Agent": "OpenRotas-Desktop"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if str(d.get("code")) != "Ok" or not d.get("distances"):
            return None
        return [[(v / 1000.0 if v is not None else None) for v in linha] for linha in d["distances"]]
    except Exception:
        logger.info("[MATRIZ] OSRM /table indisponível; usando geodésico.", exc_info=True)
        return None


def calcular(locais, usar_osrm: bool = False, osrm_url=None, reg=None, estimar: bool = True) -> dict:
    """Matriz NxN de distâncias entre `locais` (lista ou 'A;B;C'). Devolve {ok, pontos, matriz,
    modo, resumo:{par_distante, par_proximo, media_km, diametro_km}, nota}. Nunca levanta.

    `estimar` (padrão True): sem OSRM, estima a distância RODOVIÁRIA a partir da linha reta pelo fator
    de sinuosidade do web (modo 'estimado'), em paridade com a aplicação web, em vez de reportar a linha
    reta crua. `estimar=False` mantém a linha reta pura (modo 'geodesico')."""
    base = {"ok": False, "pontos": [], "matriz": [], "modo": "geodesico", "resumo": {}, "nota": ""}
    try:
        import numpy as np
        reg = reg or _reg()
        if isinstance(locais, str):
            locais = [x for x in locais.split(";") if x.strip()]
        locais = list(locais or [])
        resol = [_resolver_ponto(t, reg) for t in locais]
        pts = [r for r in resol if r.get("ok")]
        if len(pts) < 2:
            base["detalhe"] = "informe ao menos 2 locais resolvíveis"
            base["resolucoes"] = resol
            return base
        lons = [p["lon"] for p in pts]
        lats = [p["lat"] for p in pts]
        n = len(pts)
        from geo import isocronas
        lon_a = np.array(lons, dtype="float64")
        lat_a = np.array(lats, dtype="float64")
        M = [[0.0] * n for _ in range(n)]
        for i in range(n):
            row = isocronas._haversine_km(lons[i], lats[i], lon_a, lat_a)
            for j in range(n):
                M[i][j] = float(round(row[j], 1))
        modo = "geodesico"
        osrm_ok = False
        if usar_osrm:
            rod = _matriz_osrm(lons, lats, osrm_url or _osrm_url())
            if rod is not None:
                for i in range(n):
                    for j in range(n):
                        v = rod[i][j] if i < len(rod) and j < len(rod[i]) else None
                        if v is not None:
                            M[i][j] = float(round(v, 1))
                modo = "rodoviario"
                osrm_ok = True
        if estimar and not osrm_ok:
            # Sem OSRM: a matriz vira ESTIMATIVA rodoviária (linha reta × fator de sinuosidade), como o
            # web — nunca a reta crua. A diagonal (i==i == 0) e o resumo passam a refletir a estimativa.
            from geo import distancia
            for i in range(n):
                for j in range(n):
                    if i != j:
                        M[i][j] = float(round(distancia.estimar_rodoviaria_km(M[i][j]), 1))
            modo = "estimado"
        # Resumo (pares i<j).
        maxv = (-1.0, None); minv = (1e18, None); soma = 0.0; cnt = 0
        for i in range(n):
            for j in range(i + 1, n):
                v = M[i][j]
                soma += v; cnt += 1
                if v > maxv[0]:
                    maxv = (v, (i, j))
                if v < minv[0]:
                    minv = (v, (i, j))
        from geo import distancia
        def _par(pr):
            if not pr[1]:
                return None
            i, j = pr[1]
            # tempo estimado só quando a distância é rodoviária (estimado/OSRM); da reta pura não se estima.
            _mn = distancia.estimar_tempo_min(pr[0]) if modo != "geodesico" else None
            return {"de": pts[i]["nome"], "para": pts[j]["nome"], "km": round(pr[0], 1), "min": _mn}
        base.update({
            "ok": True,
            "pontos": [{"nome": p["nome"], "uf": p.get("uf", ""), "lon": p["lon"], "lat": p["lat"],
                        "ambiguo": bool(p.get("ambiguo")), "ufs_alt": p.get("ufs_alt", []),
                        "coord_suspeita": p.get("coord_suspeita", [])} for p in pts],
            "matriz": M, "modo": modo,
            "resumo": {"n": n, "par_distante": _par(maxv), "par_proximo": _par(minv),
                       "media_km": round(soma / cnt, 1) if cnt else 0.0,
                       "diametro_km": round(maxv[0], 1) if maxv[1] else 0.0,
                       "ambiguos": sum(1 for p in pts if p.get("ambiguo")),
                       "coord_suspeitas": sum(1 for p in pts if p.get("coord_suspeita"))},
            "nota": ("Distância %s entre %d pontos." % (distancia.descricao_modo(modo), n)),
        })
        if len(pts) < len(resol):
            base["nao_resolvidos"] = [r.get("consulta") for r in resol if not r.get("ok")]
        return base
    except Exception:
        logger.warning("[MATRIZ] cálculo falhou.", exc_info=True)
        return base


def _osrm_url():
    try:
        from geo import dossie_rota
        return dossie_rota._osrm_url()
    except Exception:
        return None


def _rotulo(p) -> str:
    return "%s%s" % (p["nome"], ("/" + p["uf"]) if p.get("uf") else "")


def _modo_rotulo(modo) -> str:
    """Rótulo curto do modo da matriz ('rodoviário' | 'estimado' | 'geodésico'), via geo.distancia."""
    try:
        from geo import distancia
        return distancia.rotulo_modo(modo)
    except Exception:
        return str(modo)


def render_texto(r: dict) -> str:
    if not r.get("ok"):
        return "Matriz O↔D indisponível: %s" % r.get("detalhe", "erro")
    pts = r["pontos"]; M = r["matriz"]
    L = ["MATRIZ ORIGEM↔DESTINO — OpenRotas", "=" * 60,
         "modo: %s · %d pontos" % (_modo_rotulo(r["modo"]), len(pts)), ""]
    for i, p in enumerate(pts):
        marca = "  ⚠ ambígua (há homônimas em %s)" % ", ".join(p.get("ufs_alt", [])) if p.get("ambiguo") else ""
        L.append("%2d. %s%s" % (i + 1, _rotulo(p), marca))
    L.append("")
    if r.get("resumo", {}).get("ambiguos"):
        L.append("⚠ %d cidade(s) ambígua(s): resolvida(s) pela 1ª homônima — especifique a UF "
                 "(ex.: \"Cidade/UF\") para fixar a correta." % r["resumo"]["ambiguos"])
        L.append("")
    nr = r.get("nao_resolvidos") or []
    if nr:
        L.append("⚠ %d local(is) não resolvido(s) e FORA da matriz: %s" % (len(nr), ", ".join(str(x) for x in nr)))
        L.append("")
    susp = [(p, p.get("coord_suspeita")) for p in pts if p.get("coord_suspeita")]
    if susp:
        L.append("⚠ %d coordenada(s) suspeita(s) (verifique a ordem lon,lat e se está no Brasil):" % len(susp))
        for p, mot in susp:
            L.append("    %s — %s" % (_rotulo(p), "; ".join(mot)))
        L.append("")
    cab = "      " + "".join("%8d" % (j + 1) for j in range(len(pts)))
    L.append(cab)
    for i in range(len(pts)):
        L.append("%4d  " % (i + 1) + "".join("%8.0f" % M[i][j] for j in range(len(pts))))
    rs = r["resumo"]
    L.append("")
    if rs.get("par_distante"):
        from geo import distancia
        pd = rs["par_distante"]; pp = rs["par_proximo"]
        _dur = distancia.formatar_duracao(pd.get("min"))
        L.append("mais distante: %s ↔ %s (%.0f km%s) · mais próximo: %s ↔ %s (%.0f km) · média %.0f km"
                 % (pd["de"], pd["para"], pd["km"], (" ≈ " + _dur) if _dur else "",
                    pp["de"], pp["para"], pp["km"], rs["media_km"]))
    L.append(r["nota"] + " (valores em km)")
    return "\n".join(L)


def _heatmap(r: dict) -> str:
    pts = r["pontos"]; M = r["matriz"]
    n = len(pts)
    mx = 1.0
    for i in range(n):
        for j in range(n):
            if i != j:
                mx = max(mx, M[i][j])
    out = ["<table><thead><tr><th>#</th>"]
    for j in range(n):
        out.append("<th class='num'>%d</th>" % (j + 1))
    out.append("</tr></thead><tbody>")
    for i in range(n):
        out.append("<tr><td title=\"%s\">%d. %s</td>" % (html.escape(_rotulo(pts[i])), i + 1,
                                                         html.escape(_rotulo(pts[i])[:18])))
        for j in range(n):
            v = M[i][j]
            if i == j:
                out.append("<td class='num' style='color:var(--muted)'>—</td>")
            else:
                alpha = 0.06 + 0.82 * (v / mx) if mx else 0.0
                out.append("<td class='num' style='background:rgba(59,130,246,%.2f)' "
                           "data-ork-tip=\"%s → %s: %.0f km\">%.0f</td>"
                           % (alpha, html.escape(_rotulo(pts[i])), html.escape(_rotulo(pts[j])), v, v))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def construir_html(r: dict) -> str:
    try:
        from resources import tema
    except Exception:
        try:
            import tema
        except Exception:
            tema = None
    if not r.get("ok"):
        if tema is None:
            return "<!doctype html><html><head><meta charset='utf-8'></head><body><pre>%s</pre></body></html>" % html.escape(render_texto(r))
        return tema.documento("Matriz Origem↔Destino", "", "<p class='empty'>%s</p>" % html.escape(render_texto(r)))
    rs = r["resumo"]
    corpo = ["<section class='card'><h2>Resumo</h2><div class='kpis'>",
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Pontos</div></div>" % rs.get("n", 0),
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Par mais distante</div></div>" % rs.get("diametro_km", 0),
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Distância média</div></div>" % rs.get("media_km", 0),
             "<div class='kpi'><div class='v'>%s</div><div class='l'>Modo</div></div>" % html.escape(_modo_rotulo(r["modo"])),
             "</div>"]
    if rs.get("par_distante"):
        from geo import distancia
        pd = rs["par_distante"]; pp = rs["par_proximo"]
        _dur = distancia.formatar_duracao(pd.get("min"))
        corpo.append("<p class='sub' style='margin:10px 2px 0'>Mais distante: <b>%s ↔ %s</b> (%.0f km%s) · "
                     "mais próximo: <b>%s ↔ %s</b> (%.0f km).</p>"
                     % (html.escape(pd["de"]), html.escape(pd["para"]), pd["km"],
                        (" ≈ " + html.escape(_dur)) if _dur else "",
                        html.escape(pp["de"]), html.escape(pp["para"]), pp["km"]))
    ambs = [p for p in r["pontos"] if p.get("ambiguo")]
    if ambs:
        itens = "; ".join("<b>%s</b> (também em %s)" % (html.escape(_rotulo(p)),
                          html.escape(", ".join(p.get("ufs_alt", []))) or "outras UFs") for p in ambs)
        corpo.append("<p class='sub' style='margin:10px 2px 0;color:var(--warn,#b45309)'>"
                     "⚠ %d cidade(s) ambígua(s), resolvida(s) pela 1ª homônima: %s. "
                     "Especifique a UF (ex.: \"Cidade/UF\") para fixar a correta.</p>"
                     % (len(ambs), itens))
    nr = r.get("nao_resolvidos") or []
    if nr:
        corpo.append("<p class='sub' style='margin:10px 2px 0;color:var(--warn,#b45309)'>"
                     "⚠ %d local(is) não resolvido(s) e fora da matriz: %s.</p>"
                     % (len(nr), html.escape(", ".join(str(x) for x in nr))))
    susp = [p for p in r["pontos"] if p.get("coord_suspeita")]
    if susp:
        itens = "; ".join("<b>%s</b> (%s)" % (html.escape(_rotulo(p)),
                          html.escape("; ".join(p.get("coord_suspeita", [])))) for p in susp)
        corpo.append("<p class='sub' style='margin:10px 2px 0;color:var(--warn,#b45309)'>"
                     "⚠ %d coordenada(s) suspeita(s) — verifique a ordem <b>lon,lat</b> e se está no "
                     "Brasil: %s.</p>" % (len(susp), itens))
    corpo.append("</section>")
    if tema is not None:
        # Mapa: os pontos como corredor/waypoints sobre o Brasil.
        try:
            from audit import coverage_auditor as ca
            lons, lats, _u = ca.pontos_municipios()
            rota = [(p["lon"], p["lat"]) for p in r["pontos"]]
            m = tema.mapa_dispersao(lons, lats, rota=rota, titulo="PONTOS DA MATRIZ NO BRASIL") if lons else ""
            if m:
                corpo.append("<section class='card'><h2>Pontos no mapa</h2>%s</section>" % m)
        except Exception:
            pass
    corpo.append("<section class='card'><h2>Matriz de distâncias (km)</h2>%s"
                 "<p class='empty' style='margin:8px 2px 0'>Quanto mais azul, maior a distância. "
                 "Passe o mouse para ver o par. %s</p></section>" % (_heatmap(r), html.escape(r["nota"])))
    if tema is None:
        return "<!doctype html><html><head><meta charset='utf-8'><title>Matriz O↔D — OpenRotas</title></head><body><pre>%s</pre></body></html>" % html.escape(render_texto(r))
    legenda = " · ".join("%d. %s" % (i + 1, _rotulo(p)) for i, p in enumerate(r["pontos"]))
    return tema.documento("Matriz Origem↔Destino", r["nota"], "".join(corpo),
                          "Pontos: " + legenda)


def exportar_excel(r: dict, caminho) -> str | None:
    try:
        if not r.get("ok"):
            return None
        import pandas as pd
        rot = [_rotulo(p) for p in r["pontos"]]
        df = pd.DataFrame(r["matriz"], index=rot, columns=rot)
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(pth), engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name="Matriz_km")
        return str(pth)
    except Exception:
        logger.warning("[MATRIZ] falha ao exportar Excel.", exc_info=True)
        return None


def gerar(caminho, r: dict) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(r), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[MATRIZ] falha ao gerar HTML.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    usar_osrm = "--osrm" in argv
    estimar = "--geodesico" not in argv   # --geodesico força a linha reta pura (sem estimativa de sinuosidade)
    locais = None
    for a in argv:
        if a.startswith("--"):
            continue
        if ";" in a:
            locais = a
            break
    if not locais:
        print('uso: --matriz "Cidade/UF;Cidade/UF;..." [--osrm] [--geodesico] [--html] [--excel]')
        return 2
    r = calcular(locais, usar_osrm=usar_osrm, estimar=estimar)
    print(render_texto(r))
    if r.get("ok") and ("--html" in argv or "--excel" in argv):
        try:
            import desktop_config as cfg
            exp = cfg.ensure_user_dirs()["exports"]
        except Exception:
            exp = Path(".")
        if "--html" in argv:
            got = gerar(exp / "matriz_od.html", r)
            if got:
                print("\nHTML: %s" % got)
                try:
                    import webbrowser
                    webbrowser.open(Path(got).as_uri())
                except Exception:
                    pass
        if "--excel" in argv:
            print("Excel: %s" % (exportar_excel(r, exp / "matriz_od.xlsx") or "falha"))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
