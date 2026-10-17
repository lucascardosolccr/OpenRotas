# -*- coding: utf-8 -*-
"""OpenRotas Desktop — SISTEMA DE DESIGN DA MARCA (tema visual único).

Fonte ÚNICA do visual do desktop: paleta, tipografia, componentes e GRÁFICOS usados por TODOS os
relatórios HTML (Central de Recursos, Saúde Nacional, Mapa de Cobertura, Dossiê, Comparação), pela
janela Tkinter (Central de Dados) e em harmonia com a janela nativa (app/janela.py) e o app web.
Antes cada relatório carregava um CSS próprio, duplicado e utilitário; agora todos herdam UMA
identidade coesa e polida.

Princípios (desktop é OFFLINE-first — §31/§32): NADA de CDN/Google Fonts (quebraria sem rede);
pilha de fontes de sistema e design próprio, inline e autossuficiente. Tema claro E escuro pelo
padrão de 3 estados (prefers-color-scheme + data-theme). Gráficos em SVG inline (sem bibliotecas)
com tooltip dinâmico por JS leve e realce no hover. Puro/defensivo: nunca levanta.

Identidade: logística/roteamento nacional, alinhada à marca do app (azul #3B82F6 + ciano/teal).
Mesma cor de acento nos dois temas (marca constante). Títulos marcados por um "waypoint"."""
from __future__ import annotations

import html
import math

MARCA = "OpenRotas"
_VERSAO_TEMA = "2"

# Acento da marca — alinhado ao app (web/janela nativa): azul #3B82F6. CONSTANTE nos dois temas.
ACENTO = "#3b82f6"
ACENTO_FORTE = "#2563eb"
TEAL = "#0891b2"

# Paleta Tkinter (janela clara da Central de Dados, coesa com o tema claro do HTML).
TK = {
    "bg": "#eef2fb", "surface": "#ffffff", "ink": "#15203a", "ink_soft": "#3b4660",
    "muted": "#5a6681", "line": "#dbe2f0", "line_forte": "#c6d1e8",
    "accent": ACENTO, "accent_forte": ACENTO_FORTE, "accent_bg": "#e8f0ff",
    "ok": "#138a52", "warn": "#b9771c", "bad": "#c0392b", "chip": "#eef2fb", "disabled": "#aab2c5",
}


def css() -> str:
    """Folha de estilo COMPLETA e coesa da marca (string, sem a tag <style>): cartões, KPIs,
    tabelas, badges, matriz de cobertura, dimensões, rota/alertas, recomendação, legenda E
    gráficos SVG. Tema claro/escuro em 3 estados."""
    return """
:root{
  --bg:#eef2fb; --bg-deco:#e3eaf8; --surface:#ffffff; --surface-2:#f5f8ff; --ink:#111a2e;
  --ink-soft:#394563; --muted:#64708c; --line:#e2e8f4; --line-2:#d5def0;
  --accent:#3b82f6; --accent-ink:#2563eb; --teal:#0891b2;
  --ok:#138a52; --okbg:#e4f5ec; --warn:#b9771c; --warnbg:#fbf1dd; --bad:#c0392b; --badbg:#fae9e6;
  --chip:#eef2fb; --shadow:0 1px 2px rgba(17,26,46,.05), 0 10px 26px -14px rgba(17,26,46,.30);
  --radius:16px;
}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0b0f1a; --bg-deco:#111a30; --surface:#141b2b; --surface-2:#0f1625; --ink:#eaf0fb;
  --ink-soft:#c3cce1; --muted:#8a97b4; --line:#242f45; --line-2:#2d3a55;
  --accent:#60a5fa; --accent-ink:#9dc0ff; --teal:#22d3ee;
  --ok:#3fce84; --okbg:#0f2a1c; --warn:#e4ad48; --warnbg:#2a1f07; --bad:#ff7a6b; --badbg:#2d1512;
  --chip:#18223c; --shadow:0 1px 2px rgba(0,0,0,.4), 0 16px 34px -16px rgba(0,0,0,.7);
}}
:root[data-theme="dark"]{
  --bg:#0b0f1a; --bg-deco:#111a30; --surface:#141b2b; --surface-2:#0f1625; --ink:#eaf0fb;
  --ink-soft:#c3cce1; --muted:#8a97b4; --line:#242f45; --line-2:#2d3a55;
  --accent:#60a5fa; --accent-ink:#9dc0ff; --teal:#22d3ee;
  --ok:#3fce84; --okbg:#0f2a1c; --warn:#e4ad48; --warnbg:#2a1f07; --bad:#ff7a6b; --badbg:#2d1512;
  --chip:#18223c; --shadow:0 1px 2px rgba(0,0,0,.4), 0 16px 34px -16px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink); line-height:1.55;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,"Noto Sans",sans-serif;
  font-feature-settings:"kern" 1; -webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(1200px 380px at 100% -10%, var(--bg-deco), transparent 60%),
    radial-gradient(900px 320px at -10% 0%, var(--bg-deco), transparent 55%);
  background-repeat:no-repeat;
}
body::before{content:"";position:fixed;inset:0 0 auto 0;height:4px;z-index:2;
  background:linear-gradient(90deg,var(--accent),var(--teal))}
.wrap{max-width:980px;margin:0 auto;padding:40px 20px 64px}
h1{font-size:clamp(1.4rem,1.1rem + 1.4vw,1.75rem);line-height:1.15;margin:0 0 6px;
  letter-spacing:-.02em;text-wrap:balance;display:flex;align-items:center;gap:12px}
h1::before{content:"";flex:0 0 auto;width:13px;height:13px;border-radius:50%;
  background:var(--accent);box-shadow:0 0 0 4px rgba(59,130,246,.20)}
h2{font-size:1.06rem;margin:0 0 12px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 26px;font-size:.92rem;max-width:68ch}
a{color:var(--accent-ink);text-underline-offset:2px}
code{background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:1px 6px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.86em}
/* Cartões ------------------------------------------------------------------ */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:18px 20px;margin:0 0 16px;box-shadow:var(--shadow)}
.card > h2:first-child{display:flex;align-items:center;gap:8px}
.card > h2:first-child::before{content:"";width:7px;height:16px;border-radius:3px;
  background:linear-gradient(var(--accent),var(--teal));flex:0 0 auto}
/* KPIs --------------------------------------------------------------------- */
.kpis{display:flex;flex-wrap:wrap;gap:12px}
.kpi{flex:1 1 150px;background:var(--surface-2);border:1px solid var(--line);border-radius:12px;
  padding:13px 15px}
.kpi .v{font-size:1.5rem;font-weight:750;letter-spacing:-.02em;font-variant-numeric:tabular-nums;
  line-height:1.1}
.kpi .l{color:var(--muted);font-size:.76rem;letter-spacing:.02em;margin-top:2px}
/* Tabelas ------------------------------------------------------------------ */
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{color:var(--muted);font-weight:650;font-size:.72rem;text-transform:uppercase;
  letter-spacing:.05em;border-bottom:1px solid var(--line-2)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--surface-2)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
/* Badges / pills ----------------------------------------------------------- */
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.74rem;font-weight:700;
  letter-spacing:.01em;background:var(--chip);border:1px solid transparent}
.b-ok{color:var(--ok);background:var(--okbg)} .b-warn,.b-parcial{color:var(--warn);background:var(--warnbg)}
.b-bad,.b-ausente{color:var(--bad);background:var(--badbg)}
/* Matriz de cobertura (coverage_map) --------------------------------------- */
.cell{font-weight:700;border-radius:8px;text-align:center}
.cell.ok,.ok{color:var(--ok);background:var(--okbg)} .cell.bad,.bad{color:var(--bad);background:var(--badbg)}
.reg{background:var(--chip);font-weight:800;text-transform:uppercase;letter-spacing:.05em;
  font-size:.74rem;color:var(--ink-soft)}
.legenda{display:flex;gap:16px;margin:14px 2px 0;color:var(--muted);font-size:.85rem;flex-wrap:wrap}
.pill{display:inline-block;width:12px;height:12px;border-radius:4px;vertical-align:middle;margin-right:6px}
/* Dimensões (saude_nacional) ----------------------------------------------- */
.dim{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--line-2);
  border-radius:12px;padding:14px 16px;margin:0 0 12px;box-shadow:var(--shadow)}
.dim.ok{border-left-color:var(--ok)} .dim.parcial{border-left-color:var(--warn)}
.dim.ausente{border-left-color:var(--bad)}
.dim h2{font-size:1.02rem;margin:0 0 2px;display:flex;align-items:center;gap:8px}
.dim .resumo{font-size:.95rem}
.dim details{margin-top:6px;color:var(--muted);font-size:.86rem}
details summary{cursor:pointer;color:var(--accent-ink);font-weight:600}
/* Dossiê / comparação ------------------------------------------------------ */
.rota{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:1.1rem;font-weight:750;
  letter-spacing:-.01em;margin-bottom:8px}
.seta{color:var(--accent)}
.alerta{background:var(--warnbg);border-left:3px solid var(--warn);padding:9px 13px;
  border-radius:0 10px 10px 0;margin:7px 0;color:var(--ink)}
.reco{border-left:4px solid var(--ok)}
.reco .badge{background:var(--okbg);color:var(--ok);margin-left:8px}
.rt{font-size:1.08rem;font-weight:750;margin:0 0 2px}
.score{color:var(--muted);font-size:.9rem;margin:0 0 8px}
tr.best td{background:var(--okbg)}
.empty{color:var(--muted);font-style:italic}
footer{color:var(--muted);font-size:.78rem;margin-top:18px;text-align:center}
footer::before{content:"\\25CF ";color:var(--accent)}
/* Gráficos (SVG inline) ---------------------------------------------------- */
.ork-chart{width:100%;height:auto;display:block;margin:4px 0 2px;overflow:visible}
.ork-chart .track{fill:var(--chip)}
.ork-chart .bar{fill:var(--accent)}
.ork-chart .bar.ok{fill:var(--ok)} .ork-chart .bar.warn{fill:var(--warn)}
.ork-chart .bar.bad{fill:var(--bad)} .ork-chart .bar.teal{fill:var(--teal)}
.ork-chart .lbl{fill:var(--ink-soft);font-size:12px}
.ork-chart .val{fill:var(--ink);font-size:12px;font-weight:700;font-variant-numeric:tabular-nums}
.ork-chart .cap{fill:var(--muted);font-size:11px;letter-spacing:.02em}
.ork-chart .bar{cursor:default}
.ork-chart:hover .bar{opacity:.5} .ork-chart .bar:hover{opacity:1}
.ork-leg{display:flex;flex-wrap:wrap;gap:14px;margin:8px 2px 0;color:var(--muted);font-size:.82rem}
.ork-leg i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.ork-tip{position:fixed;z-index:60;pointer-events:none;opacity:0;background:var(--ink);
  color:var(--surface);font-size:.78rem;padding:6px 9px;border-radius:8px;box-shadow:var(--shadow);
  max-width:260px;line-height:1.35;transition:opacity .12s ease}
/* Mapa nacional (dispersão de municípios, SVG) ----------------------------- */
.ork-mapa{width:100%;height:auto;display:block;margin:4px 0 2px;max-height:600px}
.ork-mapa .pt{fill:var(--muted);opacity:.5}
.ork-mapa .pt.teal,.ork-mapa .pt.ok{fill:var(--teal);opacity:.8}
.ork-mapa .pt.bad{fill:var(--bad);opacity:.85} .ork-mapa .pt.warn{fill:var(--warn);opacity:.85}
.ork-mapa .pt.accent{fill:var(--accent);opacity:.7}
.ork-mapa .rota{fill:none;stroke:var(--accent);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.ork-mapa .wp{fill:var(--accent);stroke:var(--surface);stroke-width:1.6}
@media (max-width:520px){.wrap{padding:28px 16px 48px}.kpi{flex-basis:calc(50% - 6px)}}
@media (prefers-reduced-motion:no-preference){
  .card,.dim{transition:box-shadow .18s ease, transform .18s ease}
  .card:hover{transform:translateY(-1px)}
  .ork-chart .bar{transition:opacity .15s ease}
}
"""


def logo_svg(altura: int = 26) -> str:
    """Logo/marca inline (SVG): dois waypoints ligados por uma rota curva. Usa currentColor —
    herda a cor do contexto (claro/escuro). É o mesmo motivo do 'waypoint' dos títulos."""
    try:
        h = int(altura)
    except Exception:
        h = 26
    return (
        "<svg width='%d' height='%d' viewBox='0 0 28 28' fill='none' "
        "xmlns='http://www.w3.org/2000/svg' aria-hidden='true' role='img'>"
        "<path d='M6 20 C 13 16, 12 10, 20 8' stroke='currentColor' stroke-width='2.2' "
        "stroke-linecap='round' fill='none' opacity='.55'/>"
        "<circle cx='6' cy='20' r='3.4' fill='currentColor'/>"
        "<circle cx='21' cy='8' r='3.4' fill='currentColor'/>"
        "</svg>" % (h, h)
    )


def cabecalho(titulo: str, subtitulo: str = "") -> str:
    """Cabeçalho de marca (logo + wordmark + título + subtítulo) para o topo de um relatório."""
    sub = ("<p class='sub'>%s</p>" % subtitulo) if subtitulo else ""
    return ("<header class='ork-hero'>"
            "<div class='ork-brand' style='display:flex;align-items:center;gap:9px;color:var(--accent);"
            "font-weight:800;letter-spacing:-.01em;margin-bottom:10px'>%s"
            "<span style='color:var(--ink)'>%s</span></div>"
            "<h1>%s</h1>%s</header>" % (logo_svg(24), MARCA, titulo, sub))


def documento(titulo: str, subtitulo: str = "", corpo: str = "", rodape: str = "",
              lang: str = "pt-BR") -> str:
    """Documento HTML COMPLETO e autossuficiente com a identidade da marca. Nunca levanta."""
    try:
        rod = ("<footer>%s</footer>" % rodape) if rodape else ""
        return ("<!doctype html><html lang='%s'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>%s — %s</title><style>%s</style></head><body><div class='wrap'>"
                "%s%s%s</div></body></html>"
                % (lang, titulo, MARCA, css(), cabecalho(titulo, subtitulo), corpo, rod))
    except Exception:
        return "<!doctype html><html><head><meta charset='utf-8'></head><body>%s</body></html>" % corpo


# ---------------------------------------------------------------------------
# GRÁFICOS — SVG inline (sem bibliotecas, offline), temáticos e interativos.
# ---------------------------------------------------------------------------
def _fmt(v) -> str:
    """Número legível em pt-BR: inteiro quando for inteiro, senão 1 casa com vírgula."""
    try:
        f = float(v)
    except Exception:
        return str(v)
    if abs(f - round(f)) < 1e-9:
        return "{:,}".format(int(round(f))).replace(",", ".")
    return ("%.1f" % f).replace(".", ",")


def _trunc(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else (s[: n - 1] + "…")


def _tooltip_js() -> str:
    """Script IDEMPOTENTE (guarda window.__orkTip) que mostra um tooltip dinâmico sobre qualquer
    elemento com [data-ork-tip]. Seguro repetir em vários gráficos: só o 1º vincula. Offline."""
    return ("<script>(function(){if(window.__orkTip)return;window.__orkTip=1;"
            "var t=document.createElement('div');t.className='ork-tip';"
            "if(document.body)document.body.appendChild(t);else return;"
            "function mv(e){t.style.left=Math.min(window.innerWidth-270,e.clientX+14)+'px';"
            "t.style.top=(e.clientY+16)+'px';}"
            "document.addEventListener('pointerover',function(e){var el=e.target.closest&&"
            "e.target.closest('[data-ork-tip]');if(!el)return;t.textContent="
            "el.getAttribute('data-ork-tip');t.style.opacity='1';mv(e);});"
            "document.addEventListener('pointermove',function(e){if(t.style.opacity==='1')mv(e);});"
            "document.addEventListener('pointerout',function(e){var el=e.target.closest&&"
            "e.target.closest('[data-ork-tip]');if(el)t.style.opacity='0';});})();</script>")


def grafico_barras(itens, unidade: str = "", max_valor=None, titulo: str = "",
                   mostrar_valor: bool = True) -> str:
    """Gráfico de BARRAS horizontais (uma série = magnitude). `itens`: lista de dicts
    {rotulo, valor, classe?('ok'|'warn'|'bad'|'teal'), dica?}. Rótulo à esquerda, barra com ponta
    arredondada ancorada na base, valor na ponta; tooltip nativo (<title>) + dinâmico (data-ork-tip)
    e realce no hover. Puro; devolve '' se não houver itens. Nunca levanta."""
    try:
        itens = [i for i in (itens or []) if isinstance(i, dict)]
        if not itens:
            return ""
        vals = [float(i.get("valor") or 0) for i in itens]
        vmax = float(max_valor) if max_valor else max(vals + [1e-9])
        if vmax <= 0:
            vmax = 1e-9
        W, LBL, PADR, GAP, BH = 680, 190, 58, 12, 22
        top = 24 if titulo else 6
        rowh = BH + GAP
        H = top + rowh * len(itens) + 4
        x0 = LBL
        barw = W - LBL - PADR
        P = ["<svg class='ork-chart' viewBox='0 0 %d %d' preserveAspectRatio='xMinYMin meet' "
             "role='img' style='max-height:%dpx'>" % (W, H, H + 8)]
        if titulo:
            P.append("<text class='cap' x='0' y='13'>%s</text>" % html.escape(titulo))
        for k, it in enumerate(itens):
            y = top + k * rowh
            v = float(it.get("valor") or 0)
            w = max(3.0, barw * (v / vmax))
            cls = "bar " + it["classe"] if it.get("classe") in ("ok", "warn", "bad", "teal") else "bar"
            rot = str(it.get("rotulo", ""))
            vtxt = _fmt(v) + ((" " + unidade) if unidade else "")
            dica = html.escape(str(it.get("dica") or ("%s: %s" % (rot, vtxt))))
            P.append("<rect class='track' x='%d' y='%d' width='%d' height='%d' rx='%d'/>"
                     % (x0, y, barw, BH, BH // 2))
            P.append("<rect class='%s' x='%d' y='%d' width='%.1f' height='%d' rx='%d' "
                     "data-ork-tip=\"%s\"><title>%s</title></rect>"
                     % (cls, x0, y, w, BH, BH // 2, dica, dica))
            P.append("<text class='lbl' x='0' y='%d'>%s</text>" % (y + BH - 6, html.escape(_trunc(rot, 26))))
            if mostrar_valor:
                P.append("<text class='val' x='%.1f' y='%d'>%s</text>"
                         % (min(x0 + w + 6, W - PADR + 2), y + BH - 6, html.escape(vtxt)))
        P.append("</svg>")
        return "".join(P) + _tooltip_js()
    except Exception:
        return ""


_CORES_SEG = {"ok": "var(--ok)", "warn": "var(--warn)", "bad": "var(--bad)",
              "teal": "var(--teal)", "": "var(--accent)"}


def barra_proporcao(segmentos, titulo: str = "") -> str:
    """Barra de PROPORÇÃO (100% empilhada) + legenda com rótulos (identidade nunca só por cor).
    `segmentos`: dicts {rotulo, valor, classe?}. Puro; '' se vazio. Nunca levanta."""
    try:
        segs = [s for s in (segmentos or []) if isinstance(s, dict) and float(s.get("valor") or 0) > 0]
        if not segs:
            return ""
        total = sum(float(s["valor"]) for s in segs)
        W, BH, gap = 680, 20, 3
        top = 22 if titulo else 0
        H = top + BH
        usable = W - gap * (len(segs) - 1)
        cx = 0.0
        P = ["<svg class='ork-chart' viewBox='0 0 %d %d' preserveAspectRatio='none' role='img' "
             "style='height:%dpx'>" % (W, H, H)]
        if titulo:
            P.append("<text class='cap' x='0' y='13'>%s</text>" % html.escape(titulo))
        for s in segs:
            v = float(s["valor"])
            w = max(2.0, usable * (v / total))
            cl = s.get("classe") if s.get("classe") in ("ok", "warn", "bad", "teal") else ""
            dica = html.escape("%s: %s (%.0f%%)" % (s.get("rotulo", ""), _fmt(v), 100 * v / total))
            P.append("<rect class='bar %s' x='%.1f' y='%d' width='%.1f' height='%d' rx='6' "
                     "data-ork-tip=\"%s\"><title>%s</title></rect>"
                     % (cl, cx, top, w, BH, dica, dica))
            cx += w + gap
        P.append("</svg><div class='ork-leg'>")
        for s in segs:
            cor = _CORES_SEG.get(s.get("classe", ""), "var(--accent)")
            P.append("<span><i style='background:%s'></i>%s · %s</span>"
                     % (cor, html.escape(str(s.get("rotulo", ""))), _fmt(float(s["valor"]))))
        P.append("</div>")
        return "".join(P) + _tooltip_js()
    except Exception:
        return ""


def mapa_dispersao(xs, ys, classes=None, rota=None, titulo: str = "", legenda=None,
                   cap: int = 4500) -> str:
    """Mapa NACIONAL por dispersão de pontos (lon/lat) em SVG — desenha a forma do Brasil a partir
    de dados REAIS (ex.: os ~5.570 municípios). Projeção equirretangular com correção de longitude
    por cos(lat). `classes`: lista paralela com 'ok'|'teal'|'bad'|'warn'|'accent'|None (cor do ponto).
    `rota`: polilinha [(lon,lat),...] desenhada por cima com waypoints nas pontas. `legenda`: lista
    de {rotulo, cor}. Puro; '' se vazio. Downsample até `cap` pontos (tamanho do arquivo). Nunca levanta."""
    try:
        xs = [float(v) for v in (xs or [])]
        ys = [float(v) for v in (ys or [])]
        n = min(len(xs), len(ys))
        if n == 0:
            return ""
        xs, ys = xs[:n], ys[:n]
        cls = list(classes or [])
        rota = [p for p in (rota or []) if p is not None]
        rx = [float(p[0]) for p in rota]
        ry = [float(p[1]) for p in rota]
        minx, maxx = min(xs + rx), max(xs + rx)
        miny, maxy = min(ys + ry), max(ys + ry)
        if maxx - minx < 1e-6:
            maxx = minx + 1e-6
        if maxy - miny < 1e-6:
            maxy = miny + 1e-6
        kx = math.cos(math.radians((miny + maxy) / 2.0)) or 1.0
        W, pad = 680.0, 12.0
        spanx, spany = (maxx - minx) * kx, (maxy - miny)
        innerW = W - 2 * pad
        innerH = max(150.0, min(innerW * (spany / spanx) if spanx > 0 else innerW, 560.0))
        top = 24 if titulo else 6
        H = innerH + 2 * pad + top

        def X(x):
            return pad + ((x - minx) * kx) / spanx * innerW if spanx > 0 else pad + innerW / 2

        def Y(y):
            return top + pad + (1 - (y - miny) / spany) * innerH if spany > 0 else top + pad + innerH / 2

        step = max(1, int(math.ceil(n / float(max(1, cap)))))
        P = ["<svg class='ork-mapa' viewBox='0 0 %d %d' preserveAspectRatio='xMidYMid meet' "
             "role='img' aria-label='Mapa nacional de municípios'>" % (int(W), int(H + 2))]
        if titulo:
            P.append("<text class='cap' x='0' y='13'>%s</text>" % html.escape(titulo))
        for i in range(0, n, step):
            c = cls[i] if i < len(cls) else None
            kls = "pt " + c if c in ("ok", "teal", "bad", "warn", "accent") else "pt"
            P.append("<circle class='%s' cx='%.1f' cy='%.1f' r='1.1'/>" % (kls, X(xs[i]), Y(ys[i])))
        if rota:
            if len(rota) >= 2:
                pts = " ".join("%.1f,%.1f" % (X(float(p[0])), Y(float(p[1]))) for p in rota)
                P.append("<polyline class='rota' points='%s'/>" % pts)
            for j, p in enumerate(rota):
                r = 4.4 if (j == 0 or j == len(rota) - 1) else 2.4
                P.append("<circle class='wp' cx='%.1f' cy='%.1f' r='%.1f'/>" % (X(float(p[0])), Y(float(p[1])), r))
        P.append("</svg>")
        out = "".join(P)
        if legenda:
            L = ["<div class='ork-leg'>"]
            for it in legenda:
                L.append("<span><i style='background:%s'></i>%s</span>"
                         % (it.get("cor", "var(--accent)"), html.escape(str(it.get("rotulo", "")))))
            L.append("</div>")
            out += "".join(L)
        return out
    except Exception:
        return ""


def aplicar_tema_tk(root) -> bool:
    """Aplica a identidade da marca a uma janela Tkinter/ttk (Central de Dados): tema 'clam' como
    base, paleta coesa, botões sutis com acento, campos e barra de progresso com a cor da marca.
    NÃO toca em nenhum handler — só estilo. Devolve True se aplicou; no-op defensivo em falha."""
    try:
        from tkinter import ttk
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        c = TK
        fonte = "Segoe UI"
        try:
            root.configure(bg=c["bg"])
        except Exception:
            pass
        style.configure(".", background=c["bg"], foreground=c["ink"], font=(fonte, 10))
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["ink"])
        style.configure("TLabelframe", background=c["bg"], bordercolor=c["line"],
                        relief="solid", borderwidth=1, padding=10)
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["ink_soft"],
                        font=(fonte, 10, "bold"))
        style.configure("TButton", background=c["surface"], foreground=c["accent_forte"],
                        bordercolor=c["line_forte"], borderwidth=1, relief="flat",
                        padding=(13, 7), font=(fonte, 10))
        style.map("TButton",
                  background=[("pressed", "#dce7ff"), ("active", c["accent_bg"]),
                              ("disabled", c["chip"])],
                  foreground=[("disabled", c["disabled"])],
                  bordercolor=[("active", c["accent"]), ("focus", c["accent"])])
        style.configure("TEntry", fieldbackground=c["surface"], foreground=c["ink"],
                        bordercolor=c["line_forte"], borderwidth=1, padding=5)
        style.configure("TProgressbar", background=c["accent"], troughcolor=c["line"],
                        bordercolor=c["line"], lightcolor=c["accent"], darkcolor=c["accent"])
        return True
    except Exception:
        return False
