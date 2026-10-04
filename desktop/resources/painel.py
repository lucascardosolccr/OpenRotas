# -*- coding: utf-8 -*-
"""OpenRotas Desktop — CENTRAL DE RECURSOS (painel HTML) — §17/§24/§42.

Gera um painel HTML AUTOSSUFICIENTE (um arquivo, sem rede, sem dependências externas) que reúne,
num só lugar, o estado do software para o usuário final:

  • Recursos: cada base/grafo com estado (instalado/ausente/corrompido), tamanho e módulo que usa;
  • Prontidão offline: se dá para rodar sem internet (geocodificação/hidro local + grafo rodoviário);
  • Perfil de execução (telemetria local): o que o app fez e quão rápido (média/p95 por evento).

É o lado "visual" do Gerenciador de Recursos (resource_manager): o launcher gera este arquivo e o
abre no navegador (`--recursos --html`). Puro/defensivo: nunca levanta; cada bloco degrada sozinho.
Stdlib + os módulos do próprio desktop. HTML com tema claro/escuro e layout responsivo."""
from __future__ import annotations

import os
import sys
import html
import time
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(_AQUI.parent / "app"))
sys.path.insert(0, str(_AQUI.parent))
sys.path.insert(0, str(_AQUI.parent / "data_local"))
sys.path.insert(0, str(_AQUI.parent / "telemetry"))


_CSS = """
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1a2230; --muted:#5b6676; --line:#e6e9ef;
  --accent:#1f6feb; --ok:#1a7f4b; --warn:#9a6700; --bad:#b42318; --chip:#eef2f7;
}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#0e1117; --card:#161b22; --ink:#e6edf3; --muted:#9aa4b2; --line:#283039;
  --accent:#4a9eff; --ok:#3fb950; --warn:#d29922; --bad:#ff6a5e; --chip:#1c232c;
}}
:root[data-theme="dark"]{
  --bg:#0e1117; --card:#161b22; --ink:#e6edf3; --muted:#9aa4b2; --line:#283039;
  --accent:#4a9eff; --ok:#3fb950; --warn:#d29922; --bad:#ff6a5e; --chip:#1c232c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;line-height:1.5}
.wrap{max-width:980px;margin:0 auto;padding:32px 16px 56px}
h1{font-size:1.5rem;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 24px;font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 18px}
.card h2{font-size:1.05rem;margin:0 0 12px}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.78rem;font-weight:600;background:var(--chip)}
.b-ok{color:var(--ok)} .b-warn{color:var(--warn)} .b-bad{color:var(--bad)}
.kpis{display:flex;flex-wrap:wrap;gap:12px}
.kpi{flex:1 1 160px;background:var(--chip);border-radius:10px;padding:12px 14px}
.kpi .v{font-size:1.4rem;font-weight:700;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--muted);font-size:.78rem}
.empty{color:var(--muted);font-size:.9rem;font-style:italic}
footer{color:var(--muted);font-size:.78rem;margin-top:8px;text-align:center}
"""


def _badge(estado: str) -> str:
    cls, txt = "b-ok", "instalado"
    if estado in ("ausente", "corrompido"):
        cls, txt = "b-bad", estado
    elif estado == "opcional-ausente":
        cls, txt = "b-warn", "opcional ausente"
    return '<span class="badge %s">%s</span>' % (cls, html.escape(txt))


def _tabela_recursos(osrm_cfg=None) -> str:
    try:
        from resources import resource_manager as rm
    except Exception:
        try:
            import resource_manager as rm
        except Exception:
            return '<p class="empty">Gerenciador de recursos indisponível.</p>'
    linhas = rm.status(osrm_cfg)
    out = ['<table><thead><tr><th>Recurso</th><th>Estado</th><th>Tipo</th><th>Módulo</th><th class="num">Tamanho</th></tr></thead><tbody>']
    for r in linhas:
        mb = ("%s MB" % r["mb"]) if r.get("mb") is not None else "—"
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='num'>%s</td></tr>" % (
            html.escape(str(r["chave"])), _badge(r["estado"]),
            html.escape(str(r["tipo"])), html.escape(str(r["modulo"])), html.escape(mb)))
    out.append("</tbody></table>")
    return "".join(out)


def _bloco_offline() -> str:
    try:
        import desktop_config as cfg
        import local_data
        reg = local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")
        off = reg.offline_pronto()
    except Exception:
        return '<p class="empty">Prontidão offline indisponível.</p>'
    def chip(ok):
        return '<span class="badge %s">%s</span>' % ("b-ok" if ok else "b-warn", "sim" if ok else "não")
    html_ = ['<div class="kpis">']
    html_.append('<div class="kpi"><div class="v">%s</div><div class="l">Offline pronto</div></div>'
                 % ("✓" if off["pronto"] else "parcial"))
    html_.append('<div class="kpi"><div class="l">Geocodificação / hidro local</div><div>%s</div></div>'
                 % chip(off["geocodificacao_hidro_local"]))
    html_.append('<div class="kpi"><div class="l">Roteamento local (grafo)</div><div>%s</div></div>'
                 % chip(off["roteamento_local"]))
    html_.append("</div>")
    if off.get("faltam"):
        html_.append('<p class="empty">Falta(m): %s</p>' % html.escape(", ".join(off["faltam"])))
    return "".join(html_)


def _bloco_telemetria() -> str:
    try:
        import exec_profile
        r = exec_profile.resumo()
    except Exception:
        return '<p class="empty">Perfil de execução indisponível.</p>'
    if not r.get("total"):
        return '<p class="empty">Ainda sem eventos registrados. Use o app para popular o perfil.</p>'
    out = ['<div class="kpis">']
    out.append('<div class="kpi"><div class="v">%s</div><div class="l">Eventos</div></div>' % r["total"])
    out.append('<div class="kpi"><div class="v">%s</div><div class="l">OK</div></div>' % r["ok"])
    out.append('<div class="kpi"><div class="v">%s</div><div class="l">Erros</div></div>' % r["erro"])
    out.append("</div>")
    tempos = r.get("tempos") or {}
    if tempos:
        out.append('<table><thead><tr><th>Evento</th><th class="num">N</th><th class="num">Média (ms)</th>'
                   '<th class="num">p95 (ms)</th><th class="num">Máx (ms)</th></tr></thead><tbody>')
        for ev, t in sorted(tempos.items(), key=lambda kv: -kv[1]["n"]):
            out.append("<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                       "<td class='num'>%s</td><td class='num'>%s</td></tr>" % (
                           html.escape(str(ev)), t["n"], t["media_ms"], t["p95_ms"], t["max_ms"]))
        out.append("</tbody></table>")
    return "".join(out)


def construir_html(osrm_cfg=None) -> str:
    """Monta o HTML completo do painel. Nunca levanta: cada bloco degrada sozinho."""
    quando = time.strftime("%d/%m/%Y %H:%M")
    try:
        import desktop_config as cfg
        versao = getattr(cfg, "APP_VERSION", "")
    except Exception:
        versao = ""
    partes = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Central de Recursos — OpenRotas</title><style>", _CSS, "</style></head><body><div class='wrap'>",
        "<h1>Central de Recursos</h1>",
        "<p class='sub'>OpenRotas Desktop%s · gerado em %s</p>" % (
            (" v" + html.escape(str(versao))) if versao else "", html.escape(quando)),
        "<section class='card'><h2>Recursos do software</h2>", _tabela_recursos(osrm_cfg), "</section>",
        "<section class='card'><h2>Prontidão offline</h2>", _bloco_offline(), "</section>",
        "<section class='card'><h2>Perfil de execução (local)</h2>", _bloco_telemetria(), "</section>",
        "<footer>Dados locais — nada sai do seu computador.</footer>",
        "</div></body></html>",
    ]
    return "".join(partes)


def gerar(caminho, osrm_cfg=None) -> str | None:
    """Escreve o painel HTML em `caminho` e devolve o caminho (ou None em falha)."""
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(osrm_cfg), encoding="utf-8")
        return str(p)
    except Exception:
        return None


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else "central_recursos.html"
    r = gerar(destino)
    print("painel gerado em %s" % r if r else "falha ao gerar o painel")
    raise SystemExit(0 if r else 1)
