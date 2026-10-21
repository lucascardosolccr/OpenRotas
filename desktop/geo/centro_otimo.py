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

Distância por padrão ESTIMADA (modo 'estimado'): linha reta (haversine, vetorizada, offline) corrigida
pelo fator de sinuosidade do web (geo.distancia) — PARIDADE com a aplicação web. Com motor OSRM
local/externo (--osrm) refina para distância RODOVIÁRIA via /table (uma chamada). `--geodesico` força a
linha reta pura (modo 'geodesico'); a escolha do melhor candidato é a mesma, os km é que ficam realistas.
Reaproveita o resolvedor de nomes (com aviso de cidade ambígua / não resolvida, como a matriz e o dossiê).
Entrega dict + texto + HTML (mapa hub→destinos + ranking) + Excel. Puro/defensivo (numpy + stdlib): nunca levanta."""
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


def calcular(candidatos, destinos=None, usar_osrm=None, osrm_url=None, reg=None,
             estimar: bool = True) -> dict:
    """Melhor candidato por distância TOTAL e por PIOR CASO até os destinos. Devolve
    {ok, candidatos:[{nome,uf,lon,lat,soma_km,max_km,media_km,ambiguo,ufs_alt}], destinos:[...],
    melhor_soma, melhor_max, modo, nao_resolvidos_candidatos, nao_resolvidos_destinos, nota}.
    Sem `destinos`, usa os próprios candidatos (acha o mais central). Nunca levanta.

    `estimar` (padrão True): sem OSRM, estima a distância RODOVIÁRIA a partir da linha reta pelo fator de
    sinuosidade do web (modo 'estimado'), em paridade com a aplicação web. `estimar=False` mantém a linha
    reta pura (modo 'geodesico'). A escolha do melhor candidato é a mesma em ambos (transforma monótona
    por distância para os conjuntos típicos, de capitais), mas os km ficam realistas."""
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
        from geo import dossie_rota as _dr
        _use_osrm, _url_osrm = _dr.resolver_osrm(usar_osrm, osrm_url)
        if _use_osrm:
            rod = _matriz_osrm_cd(cand, dest, _url_osrm)
            if rod is not None:
                linhas = rod
                modo = "rodoviario"
        fluv_c = [bool(c.get("acesso_fluvial")) for c in cand]
        fluv_d = [bool(d.get("acesso_fluvial")) for d in dest]
        if estimar and modo == "geodesico":
            # Sem OSRM: estima a distância rodoviária da linha reta (fator de sinuosidade do web), em vez
            # da reta crua. CONSCIÊNCIA FLUVIAL: o par candidato×destino com algum extremo de acesso só
            # fluvial usa o fator FLUVIAL (~3×). A reta é o piso. (centro_otimo.calcular)
            from geo import distancia
            linhas = [distancia.estimar_rodoviaria_vetor(row, fluvial=[fluv_c[i] or fd for fd in fluv_d])
                      for i, row in enumerate(linhas)]
            modo = "estimado"
        out = []
        for i, c in enumerate(cand):
            row = [float(v) for v in linhas[i]]
            soma = float(sum(row))
            mx = float(max(row)) if row else 0.0
            out.append({"nome": c["nome"], "uf": c.get("uf", ""), "lon": c["lon"], "lat": c["lat"],
                        "ambiguo": bool(c.get("ambiguo")), "ufs_alt": c.get("ufs_alt", []),
                        "coord_suspeita": c.get("coord_suspeita", []),
                        "acesso_fluvial": fluv_c[i],
                        "soma_km": round(soma, 1), "max_km": round(mx, 1),
                        "media_km": round(soma / len(row), 1) if row else 0.0,
                        "distancias": [round(v, 1) for v in row]})
        melhor_soma = min(out, key=lambda x: x["soma_km"])
        melhor_max = min(out, key=lambda x: x["max_km"])
        # pior caso: o destino mais distante do melhor candidato por minimax — é fluvial? (p/ tempo correto)
        _mm_dist = melhor_max.get("distancias") or []
        _mm_fluv = bool(fluv_d[_mm_dist.index(max(_mm_dist))]) if _mm_dist else False
        base.update({
            "ok": True, "candidatos": out,
            "destinos": [{"nome": p["nome"], "uf": p.get("uf", ""), "lon": p["lon"], "lat": p["lat"],
                          "acesso_fluvial": fluv_d[j]} for j, p in enumerate(dest)],
            "modo": modo, "self_dest": self_dest,
            "melhor_soma": {"nome": melhor_soma["nome"], "uf": melhor_soma["uf"], "soma_km": melhor_soma["soma_km"]},
            "melhor_max": {"nome": melhor_max["nome"], "uf": melhor_max["uf"], "max_km": melhor_max["max_km"],
                           "max_min": _tempo_estimado(melhor_max["max_km"], modo, fluvial=_mm_fluv)},
            "nota": ("Distância %s de %d candidato(s) a %d destino(s)%s."
                     % (_descricao_modo(modo), len(out), len(dest),
                        " (destinos = candidatos)" if self_dest else "")),
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


def _modo_rotulo(modo) -> str:
    """Rótulo curto do modo ('rodoviário' | 'estimado' | 'geodésico'), via geo.distancia."""
    try:
        from geo import distancia
        return distancia.rotulo_modo(modo)
    except Exception:
        return str(modo)


def _descricao_modo(modo) -> str:
    """Frase descritiva do modo para a nota de rodapé, via geo.distancia."""
    try:
        from geo import distancia
        return distancia.descricao_modo(modo)
    except Exception:
        return str(modo)


def _tempo_estimado(km, modo, fluvial=False):
    """Tempo estimado (min) para uma distância (modos 'estimado'/'rodoviario'), pelo modelo do web
    (45/65 km/h), ou fluvial (~22 km/h) quando `fluvial`. None no modo 'geodesico' — não se estima
    tempo de viagem a partir da reta pura."""
    if str(modo) == "geodesico":
        return None
    try:
        from geo import distancia
        return distancia.estimar_tempo_min(km, fluvial=bool(fluvial))
    except Exception:
        return None


def _fmt_dur(minutos) -> str:
    """Minutos → 'Xh YYmin' (via geo.distancia.formatar_duracao, compartilhado). '' para None/0."""
    try:
        from geo import distancia
        return distancia.formatar_duracao(minutos)
    except Exception:
        return ""


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
    susp = [c for c in r["candidatos"] if c.get("coord_suspeita")]
    if susp:
        L.append("⚠ %d coordenada(s) suspeita(s) (verifique a ordem lon,lat / se está no Brasil): %s"
                 % (len(susp), "; ".join("%s (%s)" % (_rotulo(c), "; ".join(c.get("coord_suspeita", []))) for c in susp)))
    flv = [p for p in (r["candidatos"] + r.get("destinos", [])) if p.get("acesso_fluvial")]
    if flv:
        from geo import distancia
        nomes = sorted({_rotulo(p) for p in flv})
        L.append("🛶 " + distancia.aviso_fluvial(len(nomes)) + " Local(is): " + ", ".join(nomes))


# ----------------------------------------------------------------------------
#  K HUBS — múltiplos centros de apoio (p-mediana / p-centro). Cada destino é
#  atendido pelo hub escolhido MAIS PRÓXIMO; escolhemos o conjunto de k hubs que
#  minimiza a soma (p-mediana) ou o pior caso (p-centro). Exato por enumeração
#  quando viável (C pequeno), guloso (aproximação declarada) caso contrário.
# ----------------------------------------------------------------------------
def _dist_cd(cand, dest, usar_osrm, osrm_url, estimar: bool = True):
    """Matriz candidato×destino (km) como list[C][D] + modo. OSRM local (AUTO/forçado), estimativa
    rodoviária (sinuosidade, padrão sem OSRM) ou geodésico (estimar=False). Nunca levanta."""
    import numpy as np
    from geo import isocronas
    from geo import dossie_rota as _dr
    d_lons = np.array([p["lon"] for p in dest], dtype="float64")
    d_lats = np.array([p["lat"] for p in dest], dtype="float64")
    linhas = [[float(v) for v in isocronas._haversine_km(c["lon"], c["lat"], d_lons, d_lats)] for c in cand]
    modo = "geodesico"
    _use_osrm, _url_osrm = _dr.resolver_osrm(usar_osrm, osrm_url)
    if _use_osrm:
        rod = _matriz_osrm_cd(cand, dest, _url_osrm)
        if rod is not None:
            linhas = [[float(v) for v in row] for row in rod]
            modo = "rodoviario"
    if estimar and modo == "geodesico":
        # CONSCIÊNCIA FLUVIAL: par hub×destino com algum extremo de acesso só fluvial usa o fator FLUVIAL.
        from geo import distancia
        fluv_c = [bool(c.get("acesso_fluvial")) for c in cand]
        fluv_d = [bool(d.get("acesso_fluvial")) for d in dest]
        linhas = [[float(distancia.estimar_rodoviaria_km(v, fluvial=(fluv_c[i] or fluv_d[j])))
                   for j, v in enumerate(row)] for i, row in enumerate(linhas)]
        modo = "estimado"
    return linhas, modo


def _aval_subset(D, S, nd):
    """Para o conjunto de hubs S (índices de candidatos), atribui cada destino ao hub mais próximo.
    Devolve (total, pior_caso, atribuicao=[(destino_idx, hub_idx, km)])."""
    total = 0.0
    mx = 0.0
    atrib = []
    for j in range(nd):
        best = None
        bc = None
        for c in S:
            v = D[c][j]
            if best is None or v < best:
                best = v
                bc = c
        total += best
        if best > mx:
            mx = best
        atrib.append((j, bc, best))
    return total, mx, atrib


def _val(D, S, nd, criterio):
    total, mx, _ = _aval_subset(D, S, nd)
    return total if criterio == "soma" else mx


def _exato(D, C, nd, k, criterio):
    from itertools import combinations
    melhor_S = None
    melhor = None
    for S in combinations(range(C), k):
        v = _val(D, S, nd, criterio)
        if melhor is None or v < melhor - 1e-9:
            melhor = v
            melhor_S = list(S)
    return melhor_S


def _guloso(D, C, nd, k, criterio):
    """Guloso: adiciona a cada passo o candidato que mais reduz o critério. Aproximação (declarada)."""
    chosen = []
    remaining = set(range(C))
    while len(chosen) < k and remaining:
        best_add = None
        best = None
        for c in remaining:
            v = _val(D, chosen + [c], nd, criterio)
            if best is None or v < best - 1e-9:
                best = v
                best_add = c
        chosen.append(best_add)
        remaining.discard(best_add)
    return chosen


def _montar_solucao(S, cand, dest, D):
    nd = len(dest)
    total, mx, atrib = _aval_subset(D, S, nd)
    S = list(S)
    hubs = [{"nome": cand[i]["nome"], "uf": cand[i].get("uf", ""),
             "lon": cand[i]["lon"], "lat": cand[i]["lat"]} for i in S]
    atribuicao = [{"destino": _rotulo(dest[j]), "hub": _rotulo(cand[c]),
                   "hub_pos": S.index(c), "km": round(km, 1)} for (j, c, km) in atrib]
    return {"hub_idx": S, "hubs": hubs, "total_km": round(total, 1),
            "max_km": round(mx, 1), "atribuicao": atribuicao}


def calcular_k(candidatos, destinos=None, k: int = 2, usar_osrm=None, osrm_url=None, reg=None,
               estimar: bool = True) -> dict:
    """Escolhe k hubs (dentre os candidatos) atendendo cada destino pelo hub mais próximo. Devolve
    {ok, k, modo, metodo('exato'|'guloso'), candidatos, destinos, solucao_soma, solucao_max,
    nao_resolvidos_*}. solucao_soma minimiza a SOMA (p-mediana); solucao_max minimiza o PIOR CASO
    (p-centro). Sem destinos, usa os candidatos. `estimar` como em calcular(). Nunca levanta."""
    base = {"ok": False, "k": int(k or 0), "modo": "geodesico"}
    try:
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
        C, nd = len(cand), len(dest)
        k = int(k)
        if C < 1 or nd < 1:
            base["detalhe"] = "informe ao menos 1 candidato e 1 destino resolvíveis"
            return base
        if k < 1:
            base["detalhe"] = "k deve ser >= 1"
            return base
        k = min(k, C)   # não há como escolher mais hubs do que candidatos disponíveis
        D, modo = _dist_cd(cand, dest, usar_osrm, osrm_url, estimar=estimar)
        from math import comb
        exato = (C <= 22 and comb(C, k) <= 50000)
        metodo = "exato" if exato else "guloso"
        if exato:
            S_soma = _exato(D, C, nd, k, "soma")
            S_max = _exato(D, C, nd, k, "max")
        else:
            S_soma = _guloso(D, C, nd, k, "soma")
            S_max = _guloso(D, C, nd, k, "max")
        base.update({
            "ok": True, "k": k, "modo": modo, "metodo": metodo, "self_dest": self_dest,
            "candidatos": [{"nome": c["nome"], "uf": c.get("uf", ""), "lon": c["lon"], "lat": c["lat"],
                            "ambiguo": bool(c.get("ambiguo")), "ufs_alt": c.get("ufs_alt", [])} for c in cand],
            "destinos": [{"nome": p["nome"], "uf": p.get("uf", ""), "lon": p["lon"], "lat": p["lat"]} for p in dest],
            "solucao_soma": _montar_solucao(S_soma, cand, dest, D),
            "solucao_max": _montar_solucao(S_max, cand, dest, D),
            "nota": ("%d hub(s) por %s, distância %s, atendendo %d destino(s) pelo hub mais próximo%s."
                     % (k, "enumeração exata" if exato else "aproximação gulosa",
                        _descricao_modo(modo),
                        nd, " (destinos = candidatos)" if self_dest else "")),
        })
        return base
    except Exception:
        logger.warning("[CENTRO] cálculo de k hubs falhou.", exc_info=True)
        return base


def _texto_k(r: dict) -> str:
    L = ["CENTRO ÓTIMO — %d HUBS — OpenRotas" % r["k"], "=" * 60,
         "modo: %s · método: %s · %d candidato(s) · %d destino(s)"
         % (_modo_rotulo(r["modo"]), r["metodo"], len(r["candidatos"]), len(r["destinos"])), ""]
    for titulo, chave, met in (("MENOR DISTÂNCIA TOTAL (p-mediana)", "solucao_soma", "total_km"),
                               ("MENOR PIOR CASO (p-centro)", "solucao_max", "max_km")):
        s = r[chave]
        hubs = ", ".join("%s%s" % (h["nome"], ("/" + h["uf"]) if h.get("uf") else "") for h in s["hubs"])
        L.append("★ %s" % titulo)
        L.append("    hubs: %s" % hubs)
        L.append("    total %.0f km · pior caso %.0f km" % (s["total_km"], s["max_km"]))
        L.append("")
    # Atribuição da solução p-mediana (a mais usada para planejamento agregado).
    L.append("Atribuição (p-mediana) — cada destino ao hub mais próximo:")
    for a in r["solucao_soma"]["atribuicao"]:
        L.append("  %-26s → %-20s %7.0f km" % (a["destino"], a["hub"], a["km"]))
    L.append("")
    avisos = []
    _avisos_texto(r, avisos)
    L.extend(avisos)
    L.append(r["nota"] + " (valores em km)")
    return "\n".join(L)


def _html_k(r: dict, tema) -> str:
    ss, sm = r["solucao_soma"], r["solucao_max"]
    hubs_soma = ", ".join(html.escape("%s%s" % (h["nome"], ("/" + h["uf"]) if h.get("uf") else "")) for h in ss["hubs"])
    hubs_max = ", ".join(html.escape("%s%s" % (h["nome"], ("/" + h["uf"]) if h.get("uf") else "")) for h in sm["hubs"])
    corpo = ["<section class='card'><h2>%d hubs — melhor conjunto</h2><div class='kpis'>" % r["k"],
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Total (p-mediana)</div></div>" % ss["total_km"],
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Pior caso (p-centro)</div></div>" % sm["max_km"],
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Hubs</div></div>" % r["k"],
             "<div class='kpi'><div class='v'>%s</div><div class='l'>Método</div></div>"
             % ("exato" if r["metodo"] == "exato" else "guloso (aprox.)"),
             "<div class='kpi'><div class='v'>%s</div><div class='l'>Modo</div></div>"
             % html.escape(_modo_rotulo(r["modo"])),
             "</div>",
             "<p class='sub' style='margin:10px 2px 0'>Hubs por menor distância <b>total</b>: %s.</p>" % hubs_soma,
             "<p class='sub' style='margin:4px 2px 0'>Hubs por menor <b>pior caso</b>: %s.</p>" % hubs_max]
    avisos = []
    _avisos_texto(r, avisos)
    for a in avisos:
        corpo.append("<p class='sub' style='margin:8px 2px 0;color:var(--warn,#b45309)'>%s</p>" % html.escape(a))
    corpo.append("</section>")
    # Mapa: raios de cada hub (p-mediana) aos seus destinos atribuídos, sobre os municípios.
    try:
        from audit import coverage_auditor as ca
        lons, lats, _u = ca.pontos_municipios()
        # Agrupa destinos por hub e desenha ida-e-volta ao hub (as linhas só tocam os hubs).
        porhub = {}
        for a in ss["atribuicao"]:
            porhub.setdefault(a["hub_pos"], []).append(a["destino"])
        dest_por_rotulo = {_rotulo(d): (d["lon"], d["lat"]) for d in r["destinos"]}
        estrela = []
        for pos, h in enumerate(ss["hubs"]):
            hc = (h["lon"], h["lat"])
            for drot in porhub.get(pos, []):
                dc = dest_por_rotulo.get(drot)
                if dc:
                    estrela.extend([hc, dc, hc])
        m = tema.mapa_dispersao(lons, lats, rota=estrela,
                                titulo="%d HUBS (p-mediana) → DESTINOS ATRIBUÍDOS" % r["k"]) if lons and estrela else ""
        if m:
            corpo.append("<section class='card'><h2>Hubs e atribuição no mapa</h2>%s"
                         "<p class='empty' style='margin:8px 2px 0'>Cada destino ligado ao seu hub mais "
                         "próximo (solução de menor distância total), sobre os municípios do Brasil.</p></section>" % m)
    except Exception:
        pass
    # Tabela de atribuição (p-mediana).
    corpo.append("<section class='card'><h2>Atribuição (p-mediana)</h2>"
                 "<table><thead><tr><th>Destino</th><th>Hub mais próximo</th><th class='num'>km</th></tr></thead><tbody>")
    for a in sorted(ss["atribuicao"], key=lambda x: (x["hub"], -x["km"])):
        corpo.append("<tr><td>%s</td><td>%s</td><td class='num'>%.0f</td></tr>"
                     % (html.escape(a["destino"]), html.escape(a["hub"]), a["km"]))
    corpo.append("</tbody></table></section>")
    return tema.documento("Centro Ótimo — %d hubs" % r["k"], r["nota"], "".join(corpo),
                          "Destinos: " + " · ".join(_rotulo(d) for d in r["destinos"]))


def render_texto(r: dict) -> str:
    if not r.get("ok"):
        return "Centro ótimo indisponível: %s" % r.get("detalhe", "erro")
    if r.get("solucao_soma") is not None and "k" in r:
        return _texto_k(r)
    L = ["CENTRO ÓTIMO — OpenRotas", "=" * 60, "modo: %s · %d candidato(s) · %d destino(s)"
         % (_modo_rotulo(r["modo"]), len(r["candidatos"]), len(r["destinos"])), ""]
    ms, mm = r["melhor_soma"], r["melhor_max"]
    L.append("★ Menor distância TOTAL: %s%s — %.0f km somados"
             % (ms["nome"], ("/" + ms["uf"]) if ms.get("uf") else "", ms["soma_km"]))
    _dur = _fmt_dur(mm.get("max_min"))
    L.append("★ Menor PIOR CASO:       %s%s — %.0f km no destino mais distante%s"
             % (mm["nome"], ("/" + mm["uf"]) if mm.get("uf") else "", mm["max_km"],
                (" (≈ %s de viagem)" % _dur) if _dur else ""))
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
    if r.get("solucao_soma") is not None and "k" in r:
        if tema is None:
            return "<!doctype html><html><head><meta charset='utf-8'><title>Centro Ótimo — OpenRotas</title></head><body><pre>%s</pre></body></html>" % html.escape(render_texto(r))
        return _html_k(r, tema)
    ms, mm = r["melhor_soma"], r["melhor_max"]
    corpo = ["<section class='card'><h2>Melhor ponto de apoio</h2><div class='kpis'>",
             "<div class='kpi'><div class='v'>%s%s</div><div class='l'>Menor distância total</div></div>"
             % (html.escape(str(ms["nome"])), html.escape(("/" + ms["uf"]) if ms.get("uf") else "")),
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Total (soma)</div></div>" % ms["soma_km"],
             "<div class='kpi'><div class='v'>%s%s</div><div class='l'>Menor pior caso</div></div>"
             % (html.escape(str(mm["nome"])), html.escape(("/" + mm["uf"]) if mm.get("uf") else "")),
             "<div class='kpi'><div class='v'>%.0f km</div><div class='l'>Pior caso (máx.)%s</div></div>"
             % (mm["max_km"], (" · ≈ %s" % html.escape(_fmt_dur(mm.get("max_min")))) if _fmt_dur(mm.get("max_min")) else ""),
             "<div class='kpi'><div class='v'>%s</div><div class='l'>Modo</div></div>"
             % html.escape(_modo_rotulo(r["modo"])),
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


def _excel_k(r: dict, caminho) -> str | None:
    try:
        import pandas as pd
        def _hubs_rows(sol, criterio):
            return [{"criterio": criterio, "hub": "%s%s" % (h["nome"], ("/" + h["uf"]) if h.get("uf") else ""),
                     "total_km": sol["total_km"], "pior_caso_km": sol["max_km"]} for h in sol["hubs"]]
        hubs = pd.DataFrame(_hubs_rows(r["solucao_soma"], "menor_total")
                            + _hubs_rows(r["solucao_max"], "menor_pior_caso"))
        atrib = pd.DataFrame([{"destino": a["destino"], "hub": a["hub"], "km": a["km"]}
                             for a in r["solucao_soma"]["atribuicao"]])
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(pth), engine="openpyxl") as xw:
            hubs.to_excel(xw, sheet_name="Hubs", index=False)
            atrib.to_excel(xw, sheet_name="Atribuicao_pmediana", index=False)
        return str(pth)
    except Exception:
        logger.warning("[CENTRO] falha ao exportar Excel (k hubs).", exc_info=True)
        return None


def exportar_excel(r: dict, caminho) -> str | None:
    try:
        if not r.get("ok"):
            return None
        import pandas as pd
        if r.get("solucao_soma") is not None and "k" in r:
            return _excel_k(r, caminho)
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
    geod = "--geodesico" in argv
    usar_osrm = False if geod else (True if "--osrm" in argv else None)   # padrão AUTO (OSRM local se no ar)
    estimar = not geod
    destinos = None
    if "--destinos" in argv:
        j = argv.index("--destinos")
        destinos = argv[j + 1] if j + 1 < len(argv) else None
    k_val = None
    if "--k" in argv:
        j = argv.index("--k")
        kv = argv[j + 1] if j + 1 < len(argv) else None
        try:
            k_val = int(kv)
        except Exception:
            k_val = None
    candidatos = None
    for i, a in enumerate(argv):
        if a.startswith("--"):
            continue
        if a == destinos:          # não confunde a lista de destinos com a de candidatos
            continue
        if ";" in a:
            candidatos = a
            break
    if not candidatos:
        print('uso: --centro "Cand/UF;Cand/UF;..." [--destinos "Dest/UF;..."] [--k N] [--osrm] [--geodesico] [--html] [--excel]')
        return 2
    if k_val and k_val >= 2:
        r = calcular_k(candidatos, destinos=destinos, k=k_val, usar_osrm=usar_osrm, estimar=estimar)
    else:
        r = calcular(candidatos, destinos=destinos, usar_osrm=usar_osrm, estimar=estimar)
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
