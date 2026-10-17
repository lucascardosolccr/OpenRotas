# -*- coding: utf-8 -*-
"""OpenRotas Desktop — CONECTIVIDADE MULTIMODAL REAL (§8/§43): nós compartilhados entre modais.

O inventário/consulta on-route (repositorio) responde "o que a rota cruza"; aqui damos o passo
seguinte (flagado em grafo_topologico/integridade/repositorio): um GRAFO de CONECTIVIDADE entre
MODAIS — onde rodovias, ferrovias, drenagem, hidrovias, massas d'água e as TRANSPOSIÇÕES
(pontes, travessias/balsas, eclusas, atracadouros, portos) COINCIDEM no espaço.

Método (honesto e barato, 100% offline): cada feição contribui a CÉLULA do seu ponto
representativo (lon/lat) numa grade de precisão P (P=1 ⇒ ~11 km). Dois modais se CONECTAM numa
célula quando ambos têm feição ali. Derivamos:
  • hubs multimodais  — células com ≥2 CLASSES de modal (nós onde modos se encontram);
  • matriz classe×classe — nº de células compartilhadas por par de classes;
  • transposições efetivas — fração de pontes/balsas/eclusas/portos cuja célula também tem RODOVIA
    e ÁGUA (fluvial/aquaviário/hídrico): indício de que a transposição de fato liga modos.

Honesto quanto ao método (§71): é COINCIDÊNCIA de pontos representativos no nível de célula
(aproximada; a tolerância = tamanho da célula), não interseção geométrica exata — por isso
reportamos a precisão usada. Puro/defensivo (numpy + stdlib): nunca levanta."""
from __future__ import annotations

import sys
import html
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.multimodal")

_GRAU_KM = 111.0
# Classes de "água" (para confirmar transposições rodovia↔água).
_AGUA = ("fluvial", "aquaviario", "hidrico")
# Camadas de transposição/infra que ligam modos.
_TRANSPOSICAO = ("pontes", "travessias", "eclusas", "atracadouros_terminal", "complexos_portuarios")
_ROTULO_CAM = {
    "pontes": "Pontes", "travessias": "Travessias/balsas", "eclusas": "Eclusas",
    "atracadouros_terminal": "Atracadouros", "complexos_portuarios": "Portos",
}


def _repo():
    from geo import repositorio
    return repositorio.GeoIntelligenceRepository()


def _celulas_por_camada(repo, precisao: int) -> dict:
    """{camada: set((kx,ky))} — célula do ponto representativo de cada feição, por camada instalada."""
    import numpy as np
    from geo import repositorio
    f = 10 ** precisao
    out = {}
    for cam in repositorio.MODAIS:
        a = repo.arrays(cam)
        if not a or a["n"] == 0:
            continue
        kx = np.rint(a["lon"] * f).astype("int64")
        ky = np.rint(a["lat"] * f).astype("int64")
        out[cam] = set(zip(kx.tolist(), ky.tolist()))
    return out


def analisar(precisao: int = 1) -> dict:
    """Grafo de conectividade multimodal (coincidência por célula). Devolve {classes, matriz, hubs,
    hubs3, total_celulas, transposicoes, precisao, celula_km, nota}. Nunca levanta."""
    base = {"precisao": precisao, "celula_km": round(_GRAU_KM / (10 ** precisao), 1),
            "classes": [], "matriz": {}, "hubs": 0, "hubs3": 0, "total_celulas": 0,
            "transposicoes": {}, "status": "AUSENTE",
            "nota": ""}
    try:
        from collections import Counter
        from geo import repositorio
        repo = _repo()
        cel = _celulas_por_camada(repo, precisao)
        if not cel:
            return base
        # Agrega células por CLASSE multimodal.
        classes_cells: dict = {}
        for cam, keys in cel.items():
            cl = repositorio.MODAIS.get(cam, "outro")
            classes_cells.setdefault(cl, set()).update(keys)
        classes = sorted(classes_cells)
        # Matriz de co-ocorrência classe×classe (nº de células compartilhadas).
        matriz = {a: {b: len(classes_cells[a] & classes_cells[b]) for b in classes} for a in classes}
        # Hubs: células com ≥2 (e ≥3) classes distintas.
        cnt = Counter()
        for cl, keys in classes_cells.items():
            for k in keys:
                cnt[k] += 1
        hubs = sum(1 for v in cnt.values() if v >= 2)
        hubs3 = sum(1 for v in cnt.values() if v >= 3)
        # Transposições efetivas (célula com rodovia E água).
        agua = set()
        for cl in _AGUA:
            agua |= classes_cells.get(cl, set())
        rod = classes_cells.get("rodoviario", set())
        transp = {}
        for cam in _TRANSPOSICAO:
            keys = cel.get(cam)
            if not keys:
                continue
            conn = sum(1 for k in keys if (k in rod and k in agua))
            tot = len(keys)
            transp[cam] = {"rotulo": _ROTULO_CAM.get(cam, cam), "total": tot, "conecta": conn,
                           "pct": round(100.0 * conn / tot, 1) if tot else 0.0}
        base.update({
            "classes": classes, "matriz": matriz, "hubs": hubs, "hubs3": hubs3,
            "total_celulas": len(cnt), "transposicoes": transp, "status": "OK",
            "nota": ("Coincidência de pontos representativos em célula de ~%s km (precisão %d casas) — "
                     "aproximada, não é interseção geométrica exata."
                     % (base["celula_km"], precisao)),
        })
        return base
    except Exception:
        logger.warning("[MULTIMODAL] análise de conectividade falhou.", exc_info=True)
        return base


def render_texto(g: dict) -> str:
    if g.get("status") != "OK":
        return "Conectividade multimodal indisponível (bases ausentes)."
    L = ["CONECTIVIDADE MULTIMODAL — OpenRotas", "=" * 56,
         "classes presentes: %s" % ", ".join(g["classes"]),
         "hubs multimodais (≥2 classes): %d · (≥3 classes): %d · células totais: %d"
         % (g["hubs"], g["hubs3"], g["total_celulas"]), ""]
    if g["transposicoes"]:
        L.append("Transposições efetivas (célula com rodovia E água):")
        for cam, t in g["transposicoes"].items():
            L.append("  %-16s %5d/%-5d  %.1f%%" % (t["rotulo"], t["conecta"], t["total"], t["pct"]))
    L.append("")
    L.append(g["nota"])
    return "\n".join(L)


def _heatmap_html(g: dict) -> str:
    """Matriz classe×classe como heatmap sequencial (um matiz: azul da marca por opacidade)."""
    classes = g.get("classes", [])
    matriz = g.get("matriz", {})
    if not classes:
        return ""
    mx = 1
    for a in classes:
        for b in classes:
            if a != b:
                mx = max(mx, matriz.get(a, {}).get(b, 0))
    out = ["<table><thead><tr><th>classe</th>"]
    for b in classes:
        out.append("<th class='num'>%s</th>" % html.escape(b[:6]))
    out.append("</tr></thead><tbody>")
    for a in classes:
        out.append("<tr><td>%s</td>" % html.escape(a))
        for b in classes:
            v = matriz.get(a, {}).get(b, 0)
            if a == b:
                cell = "<td class='num' style='color:var(--muted)'>%d</td>" % v
            else:
                alpha = 0.08 + 0.80 * (v / mx) if mx else 0.0
                cell = ("<td class='num' style='background:rgba(59,130,246,%.2f)'>%d</td>"
                        % (alpha, v))
            out.append(cell)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def construir_html() -> str:
    """Painel HTML da conectividade multimodal (tema de marca). Nunca levanta."""
    g = analisar()
    try:
        from resources import tema
    except Exception:
        try:
            import tema
        except Exception:
            tema = None
    if tema is None:
        return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Conectividade "
                "Multimodal — OpenRotas</title></head><body><pre>%s</pre></body></html>"
                % html.escape(render_texto(g)))
    if g.get("status") != "OK":
        return tema.documento("Conectividade Multimodal", "", "<p class='empty'>Bases ausentes.</p>")
    corpo = ["<section class='card'><h2>Panorama</h2><div class='kpis'>",
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Hubs multimodais (≥2)</div></div>" % g["hubs"],
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Hubs (≥3 classes)</div></div>" % g["hubs3"],
             "<div class='kpi'><div class='v'>%d</div><div class='l'>Classes conectadas</div></div>" % len(g["classes"]),
             "<div class='kpi'><div class='v'>~%s km</div><div class='l'>Resolução da célula</div></div>" % g["celula_km"],
             "</div></section>"]
    # Transposições efetivas (barras de %).
    if g["transposicoes"]:
        itens = [{"rotulo": t["rotulo"], "valor": t["pct"],
                  "classe": "teal" if t["pct"] >= 50 else ("warn" if t["pct"] >= 20 else "bad"),
                  "dica": "%s: %d de %d em célula com rodovia e água (%.1f%%)"
                          % (t["rotulo"], t["conecta"], t["total"], t["pct"])}
                 for t in g["transposicoes"].values()]
        ch = tema.grafico_barras(itens, unidade="%", max_valor=100,
                                 titulo="TRANSPOSIÇÕES EM CÉLULA COM RODOVIA E ÁGUA (%)")
        if ch:
            corpo.append("<section class='card'><h2>Transposições efetivas</h2>%s"
                         "<p class='empty' style='margin:8px 2px 0'>Fração de cada tipo cuja célula "
                         "também contém rodovia e água — indício de ligação real entre modos.</p></section>" % ch)
    # Matriz de co-ocorrência (heatmap).
    hm = _heatmap_html(g)
    if hm:
        corpo.append("<section class='card'><h2>Matriz de conexões por classe</h2>%s"
                     "<p class='empty' style='margin:8px 2px 0'>Nº de células compartilhadas por par de "
                     "classes (quanto mais azul, mais conexões). Diagonal = células próprias da classe.</p>"
                     "</section>" % hm)
    return tema.documento("Conectividade Multimodal", "Nós compartilhados entre modais · " + g["nota"],
                          "".join(corpo),
                          "Coincidência por célula (aproximada) · dados locais, nada sai do seu computador.")


def gerar(caminho) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[MULTIMODAL] falha ao gerar o painel.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    prec = 1
    for a in argv:
        if a.startswith("--precisao="):
            try:
                prec = int(a.split("=", 1)[1])
            except Exception:
                pass
    if "--html" in argv:
        try:
            import desktop_config as cfg
            destino = cfg.ensure_user_dirs()["cache"] / "conectividade_multimodal.html"
        except Exception:
            destino = Path("conectividade_multimodal.html")
        got = gerar(destino)
        if got:
            print("Conectividade Multimodal: %s" % got)
            try:
                import webbrowser
                webbrowser.open(Path(got).as_uri())
            except Exception:
                pass
            return 0
        print("Falha ao gerar o painel.")
        return 1
    g = analisar(precisao=prec)
    print(render_texto(g))
    return 0 if g.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
