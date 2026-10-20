# -*- coding: utf-8 -*-
"""OpenRotas Desktop — CENTRO ÓTIMO (localização de facilidade, §29).

Dado um conjunto de CANDIDATOS (cidades onde o centro/hub poderia ficar) e um conjunto de
DESTINOS (as cidades a atender), responde a pergunta de alocação "qual candidato é o melhor ponto
de apoio?" por dois critérios clássicos, honestos e explicáveis:

  • MENOR DISTÂNCIA TOTAL  (p-mediana de 1 facilidade): minimiza a soma das distâncias a todos os
    destinos — melhor no agregado (custo/esforço total de deslocamento);
  • MENOR PIOR CASO        (1-centro / minimax): minimiza a MAIOR distância a qualquer destino —
    melhor equidade (ninguém fica longe demais).

Sem lista de destinos, os próprios candidatos são os destinos (acha o mais CENTRAL do conjunto).

Distância GEODÉSICA (haversine, vetorizada) por padrão — 100% offline e honesta. Com motor OSRM
local/externo (--osrm) refina para distância RODOVIÁRIA via /table (uma chamada), degradando para o
geodésico sem rede/motor (OPENROTAS_NO_NET). Reaproveita o resolvedor de nomes (com aviso de cidade
ambígua / não resolvida, como a matriz e o dossiê). Entrega dict + texto + HTML (mapa hub→destinos +
ranking) + Excel. Puro/defensivo (numpy + stdlib): nunca levanta."""
from __future__ import annotations

import sys
import html
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.centro")


def _reg():
    import desktop_config as cfg
    import local_data
    return local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")


def _osrm_url():
    try:
        from geo import dossie_rota
        return dossie_rota._osrm_url()
    except Exception:
        return None


def _resolver_lista(entrada, reg):
    """Resolve 'A;B;C' | lista → (pontos_ok, nao_resolvidos). Cada ponto_ok carrega
    nome/uf/lon/lat/ambiguo/ufs_alt (via matriz_od._resolver_ponto)."""
    from geo import matriz_od
    if isinstance(entrada, str):
        entrada = [x for x in entrada.split(";") if x.strip()]
    entrada = list(entrada or [])
    pts, nao = [], []
    for tok in entrada:
        r = matriz_od._resolver_ponto(tok, reg)
        if r.get("ok"):
            pts.append(r)
        else:
            nao.append(r.get("consulta") or str(tok))
    return pts, nao


def calcular(candidatos, destinos=None, usar_osrm: bool = False, osrm_url=None, reg=None) -> dict:
    """Melhor candidato por distância TOTAL e por PIOR CASO até os destinos. Devolve
    {ok, candidatos:[{nome,uf,lon,lat,soma_km,max_km,media_km,ambiguo,ufs_alt}], destinos:[...],
    melhor_soma, melhor_max, modo, nao_resolvidos_candidatos, nao_resolvidos_destinos, nota}.
    Sem `destinos`, usa os próprios candidatos (acha o mais central). Nunca levanta."""
    base = {"ok": False, "candidatos": [], "destinos": [], "melhor_soma": None,
            "melhor_max": None, "modo": "geodesico", "nota": ""}
    try:
        import numpy as np
        reg = reg or _reg()
        cand, nao_c = _resolver_lista(candidatos, reg)
        self_dest = destinos is None or (isinstance(destinos, str) and not destinos.strip()) \
            or (isinstance(destinos, (list, tuple)) and len(destinos) == 0)
        if self_dest:
            dest, nao_d = list(cand), []
        else:
            dest, nao_d = _resolver_lista(destinos, reg)
        base["nao_resolvidos_candidatos"] = nao_c
        base["nao_resolvidos_destinos"] = nao_d
        if len(cand) < 1 or len(dest) < 1:
            base["detalhe"] = "informe ao menos 1 candidato e 1 destino resolvíveis"
            return base
        d_lons = np.array([p["lon"] for p in dest], dtype="float64")
        d_lats = np.array([p["lat"] for p in dest], dtype="float64")
        from geo import isocronas
        # Matriz candidato×destino (km). Geodésico por padrão.
        linhas = [isocronas._haversine_km(c["lon"], c["lat"], d_lons, d_lats) for c in cand]
        modo = "geodesico"
        if usar_osrm:
            rod = _matriz_osrm_cd(cand, dest, osrm_url or _osrm_url())
            if rod is not None:
                linhas = rod
                modo = "rodoviario"
        out = []
        for i, c in enumerate(cand):
            row = [float(v) for v in linhas[i]]
            soma = float(sum(row))
            mx = float(max(row)) if row else 0.0
            out.append({"nome": c["nome"], "uf": c.get("uf", ""), "lon": c["lon"], "lat": c["lat"],
                        "ambiguo": bool(c.get("ambiguo")), "ufs_alt": c.get("ufs_alt", []),
                        "soma_km": round(soma, 1), "max_km": round(mx, 1),
                        "media_km": round(soma / len(row), 1) if row else 0.0,
                        "distancias": [round(v, 1) for v in row]})
        melhor_soma = min(out, key=lambda x: x["soma_km"])
        melhor_max = min(out, key=lambda x: x["max_km"])
        base.update({
            "ok": True, "candidatos": out,
            "destinos": [{"nome": p["nome"], "uf": p.get("uf", ""), "lon": p["lon"], "lat": p["lat"]} for p in dest],
            "modo": modo, "self_dest": self_dest,
            "melhor_soma": {"nome": melhor_soma["nome"], "uf": melhor_soma["uf"], "soma_km": melhor_soma["soma_km"]},
            "melhor_max": {"nome": melhor_max["nome"], "uf": melhor_max["uf"], "max_km": melhor_max["max_km"]},
            "nota": ("Distância %s de %d candidato(s) a %d destino(s)%s."
                     % ("rodoviária (OSRM)" if modo == "rodoviario" else "geodésica (linha reta)",
                        len(out), len(dest), " (destinos = candidatos)" if self_dest else "")),
        })
        return base
    except Exception:
        logger.warning("[CENTRO] cálculo falhou.", exc_info=True)
        return base


def _matriz_osrm_cd(cand, dest, url):
    """Matriz RODOVIÁRIA candidato×destino via OSRM /table completo (candidatos+destinos), fatiada.
    None em falha/sem rede. Nunca levanta."""
    try:
        from geo import matriz_od
        lons = [p["lon"] for p in cand] + [p["lon"] for p in dest]
        lats = [p["lat"] for p in cand] + [p["lat"] for p in dest]
        full = matriz_od._matriz_osrm(lons, lats, url)
        if full is None:
            return None
        nc, nd = len(cand), len(dest)
        out = []
        for i in range(nc):
            row = []
            for j in range(nd):
                v = full[i][nc + j] if i < len(full) and (nc + j) < len(full[i]) else None
                if v is None:
                    return None
                row.append(float(v))
            out.append(row)
        return out
    except Exception:
        return None


def _rotulo(p) -> str:
    return "%s%s" % (p["nome"], ("/" + p["uf"]) if p.get("uf") else "")


def _avisos_texto(r: dict, L: list) -> None:
    ambs = [c for c in r["candidatos"] if c.get("ambiguo")]
    if ambs:
        L.append("⚠ %d cidade(s) ambígua(s) (resolvida(s) pela 1ª homônima; qualifique com /UF): %s"
                 % (len(ambs), ", ".join("%s (também em %s)" % (_rotulo(c), ", ".join(c.get("ufs_alt", [])) or "outras UFs") for c in ambs)))
    nrc = r.get("nao_resolvidos_candidatos") or []
    nrd = r.get("nao_resolvidos_destinos") or []
    if nrc:
        L.append("⚠ Candidato(s) não resolvido(s) e fora da análise: %s" % ", ".join(str(x) for x in nrc))
    if nrd:
        L.append("⚠ Destino(s) não resolvido(s) e fora da análise: %s" % ", ".join(str(x) for x in nrd))


def render_texto(r: dict) -> str:
    if not r.get("ok"):
        return "Centro ótimo indisponível: %s" % r.get("detalhe", "erro")
    L = ["CENTRO ÓTIMO — OpenRotas", "=" * 60, "modo: %s · %d candidato(s) · %d destino(s)"
         % (r["modo"], len(r["candidatos"]), len(r["destinos"])), ""]
    ms, mm = r["melhor_soma"], r["melhor_max"]
    L.append("★ Menor distância TOTAL: %s%s — %.0f km somados"
             % (ms["nome"], ("/" + ms["uf"]) if ms.get("uf") else "", ms["soma_km"]))
    L.append("★ Menor PIOR CASO:       %s%s — %.0f km no destino mais distante"
             % (mm["nome"], ("/" + mm["uf"]) if mm.get("uf") else "", mm["max_km"]))
    L.append("")
    L.append("Candidatos (ordenados por distância total; menor = melhor):")
    for c in sorted(r["candidatos"], key=lambda x: x["soma_km"]):
        marca = " ⚠" if c.get("ambiguo") else ""
        L.append("  %-28s total %8.0f km · pior caso %7.0f km · média %7.0f km%s"
                 % (_rotulo(c), c["soma_km"], c["max_km"], c["media_km"], marca))
    L.append("")
    _avisos_texto(r, L)
    L.append(r["nota"] + " (valores em km)")
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
        return tema.documento("Centro Ótimo", "", "<p class='empty'>%s</p>" % html.escape(txt))
    ms, mm = r["melhor_soma"], r["melhor_max"]
    corpo = ["<section class='card'><h2>Melhor ponto de apoio</h2><div class='kpis'>",
             "<div class='kpi'><div class='v'>%s%s</div><div class='l'>Menor distância total</div></div>"
             % (html.escape(str(ms["nome"])), html.escape(("/" + ms["uf"]) if ms.get("uf") else "")),
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Total (soma)</div></div>" % ms["soma_km"],
             "<div class='kpi'><div class='v'>%s%s</div><div class='l'>Menor pior caso</div></div>"
             % (html.escape(str(mm["nome"])), html.escape(("/" + mm["uf"]) if mm.get("uf") else "")),
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Pior caso (máx.)</div></div>" % mm["max_km"],
             "<div class='kpi'><div class='v'>%s</div><div class='l'>Modo</div></div>"
             % ("rodoviário" if r["modo"] == "rodoviario" else "geodésico"),
             "</div>"]
    # Avisos (ambiguidade / não resolvidos) — mesma honestidade da matriz e do dossiê.
    avisos = []
    _avisos_texto(r, avisos)
    for a in avisos:
        corpo.append("<p class='sub' style='margin:8px 2px 0;color:var(--warn,#b45309)'>%s</p>" % html.escape(a))
    corpo.append("</section>")
    if tema is not None:
        # Mapa: municípios ao fundo + estrela do melhor candidato (soma) a cada destino.
        try:
            from audit import coverage_auditor as ca
            lons, lats, _u = ca.pontos_municipios()
            melhor = min(r["candidatos"], key=lambda x: x["soma_km"])
            estrela = []
            for d in r["destinos"]:
                estrela.append((melhor["lon"], melhor["lat"]))
                estrela.append((d["lon"], d["lat"]))
            m = tema.mapa_dispersao(lons, lats, rota=estrela,
                                    titulo="HUB ÓTIMO (menor total) → DESTINOS") if lons and estrela else ""
            if m:
                corpo.append("<section class='card'><h2>Hub e destinos no mapa</h2>%s"
                             "<p class='empty' style='margin:8px 2px 0'>Raios do melhor candidato "
                             "(menor distância total) a cada destino, sobre os municípios do Brasil.</p></section>" % m)
        except Exception:
            pass
        # Ranking por distância total (menor = melhor).
        try:
            melhor_nome = min(r["candidatos"], key=lambda x: x["soma_km"])["nome"]
            itens = [{"rotulo": _rotulo(c), "valor": c["soma_km"],
                      "classe": "teal" if c["nome"] == melhor_nome else None,
                      "dica": "%s: total %.0f km · pior caso %.0f km" % (_rotulo(c), c["soma_km"], c["max_km"])}
                     for c in sorted(r["candidatos"], key=lambda x: x["soma_km"])]
            g = tema.grafico_barras(itens, unidade="km", titulo="DISTÂNCIA TOTAL POR CANDIDATO (menor = melhor)")
            if g:
                corpo.append("<section class='card'><h2>Ranking</h2>%s</section>" % g)
        except Exception:
            pass
    # Tabela completa.
    corpo.append("<section class='card'><h2>Candidatos × métricas</h2>"
                 "<table><thead><tr><th>Candidato</th><th class='num'>Total (km)</th>"
                 "<th class='num'>Pior caso (km)</th><th class='num'>Média (km)</th></tr></thead><tbody>")
    for c in sorted(r["candidatos"], key=lambda x: x["soma_km"]):
        corpo.append("<tr><td>%s</td><td class='num'>%.0f</td><td class='num'>%.0f</td><td class='num'>%.0f</td></tr>"
                     % (html.escape(_rotulo(c)), c["soma_km"], c["max_km"], c["media_km"]))
    corpo.append("</tbody></table></section>")
    if tema is None:
        return "<!doctype html><html><head><meta charset='utf-8'><title>Centro Ótimo — OpenRotas</title></head><body><pre>%s</pre></body></html>" % html.escape(render_texto(r))
    return tema.documento("Centro Ótimo", r["nota"], "".join(corpo),
                          "Destinos: " + " · ".join(_rotulo(d) for d in r["destinos"]))


def exportar_excel(r: dict, caminho) -> str | None:
    try:
        if not r.get("ok"):
            return None
        import pandas as pd
        rows = [{"candidato": _rotulo(c), "total_km": c["soma_km"], "pior_caso_km": c["max_km"],
                 "media_km": c["media_km"]} for c in sorted(r["candidatos"], key=lambda x: x["soma_km"])]
        df = pd.DataFrame(rows)
        # Matriz candidato×destino (detalhe).
        dest_rot = [_rotulo(d) for d in r["destinos"]]
        det = pd.DataFrame([c["distancias"] for c in r["candidatos"]],
                           index=[_rotulo(c) for c in r["candidatos"]], columns=dest_rot)
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(pth), engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name="Ranking", index=False)
            det.to_excel(xw, sheet_name="Distancias_km")
        return str(pth)
    except Exception:
        logger.warning("[CENTRO] falha ao exportar Excel.", exc_info=True)
        return None


def gerar(caminho, r: dict) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(r), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[CENTRO] falha ao gerar HTML.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    usar_osrm = "--osrm" in argv
    destinos = None
    if "--destinos" in argv:
        j = argv.index("--destinos")
        destinos = argv[j + 1] if j + 1 < len(argv) else None
    candidatos = None
    for i, a in enumerate(argv):
        if a.startswith("--"):
            continue
        if a == destinos:
            continue
        if ";" in a:
            candidatos = a
            break
    if not candidatos:
        print('uso: --centro "Cand/UF;Cand/UF;..." [--destinos "Dest/UF;Dest/UF;..."] [--osrm] [--html] [--excel]')
        return 2
    r = calcular(candidatos, destinos=destinos, usar_osrm=usar_osrm)
    print(render_texto(r))
    if r.get("ok") and ("--html" in argv or "--excel" in argv):
        try:
            import desktop_config as cfg
            exp = cfg.ensure_user_dirs()["exports"]
        except Exception:
            exp = Path(".")
        if "--html" in argv:
            got = gerar(exp / "centro_otimo.html", r)
            if got:
                print("\nHTML: %s" % got)
                try:
                    import webbrowser
                    webbrowser.open(Path(got).as_uri())
                except Exception:
                    pass
        if "--excel" in argv:
            got = exportar_excel(r, exp / "centro_otimo.xlsx")
            if got:
                print("Excel: %s" % got)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
