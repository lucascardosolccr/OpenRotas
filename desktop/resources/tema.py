# -*- coding: utf-8 -*-
"""OpenRotas Desktop — SISTEMA DE DESIGN DA MARCA (tema visual único).

Fonte ÚNICA do visual do desktop: paleta, tipografia e componentes usados por TODOS os
relatórios HTML (Central de Recursos, Saúde Nacional, Mapa de Cobertura, Dossiê, Comparação) e
pela janela Tkinter (Central de Dados). Antes cada relatório carregava um CSS próprio, duplicado
e utilitário; agora todos herdam uma identidade coesa e polida.

Princípios (desktop é OFFLINE-first — §31/§32): NADA de CDN/Google Fonts (quebraria sem rede);
usamos uma pilha de fontes de sistema e um design próprio, inline e autossuficiente. Tema claro
E escuro pelo padrão de 3 estados (prefers-color-scheme + data-theme). Puro/defensivo: nunca
levanta; `aplicar_tema_tk` degrada para no-op se o Tkinter/ttk não cooperar.

Identidade: logística/roteamento nacional. Acento "sinal" azul (rota) + teal (hidrografia),
neutros com leve viés frio (escolhidos, não herdados), cartões com profundidade sutil, títulos
marcados por um "waypoint" (ponto de rota). Mesmo acento nos dois temas (marca constante)."""
from __future__ import annotations

MARCA = "OpenRotas"
_VERSAO_TEMA = "1"

# Acento da marca — CONSTANTE nos dois temas (identidade estável). Baked no glifo do título.
ACENTO = "#2f6bff"
ACENTO_FORTE = "#1e4fd0"
TEAL = "#0e9aa7"

# Paleta Tkinter (janela clara, coesa com o tema claro do HTML).
TK = {
    "bg": "#eef1f8", "surface": "#ffffff", "ink": "#15203a", "ink_soft": "#3b4660",
    "muted": "#5a6681", "line": "#dbe2f0", "line_forte": "#c6d1e8",
    "accent": ACENTO, "accent_forte": ACENTO_FORTE, "accent_bg": "#eaf0ff",
    "ok": "#138a52", "warn": "#b9771c", "bad": "#c0392b", "chip": "#eef2fb", "disabled": "#aab2c5",
}


def css() -> str:
    """Folha de estilo COMPLETA e coesa da marca (string, sem a tag <style>). Define todos os
    componentes usados pelos relatórios: cartões, KPIs, tabelas, badges, matriz de cobertura,
    dimensões, rota/alertas, recomendação, legenda. Tema claro/escuro em 3 estados."""
    return """
:root{
  --bg:#eef1f8; --bg-deco:#e4e9f6; --surface:#ffffff; --surface-2:#f5f8ff; --ink:#141b2e;
  --ink-soft:#3b4660; --muted:#67718a; --line:#e2e7f1; --line-2:#d6ddec;
  --accent:#2f6bff; --accent-ink:#1e4fd0; --teal:#0e9aa7;
  --ok:#138a52; --okbg:#e4f5ec; --warn:#b9771c; --warnbg:#fbf1dd; --bad:#c0392b; --badbg:#fae9e6;
  --chip:#eef2fb; --shadow:0 1px 2px rgba(20,27,46,.05), 0 10px 26px -14px rgba(20,27,46,.28);
  --radius:16px;
}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0a0f1e; --bg-deco:#111a30; --surface:#121a30; --surface-2:#0f1728; --ink:#e9eefb;
  --ink-soft:#c3cce1; --muted:#8b97b4; --line:#243049; --line-2:#2c3a57;
  --accent:#5b8cff; --accent-ink:#9db9ff; --teal:#2bc4d4;
  --ok:#3fce84; --okbg:#0f2a1c; --warn:#e4ad48; --warnbg:#2a1f07; --bad:#ff7a6b; --badbg:#2d1512;
  --chip:#18223c; --shadow:0 1px 2px rgba(0,0,0,.4), 0 16px 34px -16px rgba(0,0,0,.7);
}}
:root[data-theme="dark"]{
  --bg:#0a0f1e; --bg-deco:#111a30; --surface:#121a30; --surface-2:#0f1728; --ink:#e9eefb;
  --ink-soft:#c3cce1; --muted:#8b97b4; --line:#243049; --line-2:#2c3a57;
  --accent:#5b8cff; --accent-ink:#9db9ff; --teal:#2bc4d4;
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
  background:var(--accent);box-shadow:0 0 0 4px rgba(47,107,255,.20)}
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
footer::before{content:"● ";color:var(--accent)}
@media (max-width:520px){.wrap{padding:28px 16px 48px}.kpi{flex-basis:calc(50% - 6px)}}
@media (prefers-reduced-motion:no-preference){
  .card,.dim{transition:box-shadow .18s ease, transform .18s ease}
  .card:hover{transform:translateY(-1px)}
}
"""


def logo_svg(altura: int = 26) -> str:
    """Logo/marca inline (SVG, sem dependências): dois waypoints ligados por uma rota curva.
    Usa currentColor — herda a cor do contexto (funciona em tema claro/escuro)."""
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
    """Cabeçalho de marca (logo + wordmark + título + subtítulo) para o topo de um relatório.
    HTML puro; escapar fica a cargo do chamador quando o conteúdo não for confiável."""
    sub = ("<p class='sub'>%s</p>" % subtitulo) if subtitulo else ""
    return ("<header class='ork-hero'>"
            "<div class='ork-brand' style='display:flex;align-items:center;gap:9px;color:var(--accent);"
            "font-weight:800;letter-spacing:-.01em;margin-bottom:10px'>%s"
            "<span style='color:var(--ink)'>%s</span></div>"
            "<h1>%s</h1>%s</header>" % (logo_svg(24), MARCA, titulo, sub))


def documento(titulo: str, subtitulo: str = "", corpo: str = "", rodape: str = "",
              lang: str = "pt-BR") -> str:
    """Documento HTML COMPLETO e autossuficiente com a identidade da marca: <!doctype> + <head>
    (charset/viewport/title + CSS embutido) + cabeçalho de marca + `corpo` + rodapé. Nunca levanta."""
    try:
        rod = ("<footer>%s</footer>" % rodape) if rodape else ""
        return ("<!doctype html><html lang='%s'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>%s — %s</title><style>%s</style></head><body><div class='wrap'>"
                "%s%s%s</div></body></html>"
                % (lang, titulo, MARCA, css(), cabecalho(titulo, subtitulo), corpo, rod))
    except Exception:
        return "<!doctype html><html><head><meta charset='utf-8'></head><body>%s</body></html>" % corpo


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
        # Botões sutis (superfície + borda + texto de acento); hover com leve tinta de acento.
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
