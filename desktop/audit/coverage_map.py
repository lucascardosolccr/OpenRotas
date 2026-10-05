# -*- coding: utf-8 -*-
"""OpenRotas Desktop — MAPA DE COBERTURA NACIONAL (§41). Visualização HTML autossuficiente.

Em vez de um mapa geográfico "bonito" (que exigiria polígonos e correria o risco de parecer
cobertura onde não há), este é uma MATRIZ DE COBERTURA honesta: linhas = 27 UFs (agrupadas por
região), colunas = camadas nacionais; cada célula fica VERDE (presença espacial detectada) ou
VERMELHA (ausente), com a contagem de municípios por UF. Assim as "áreas sem dados ficam
claramente identificáveis" (§41), sem inventar geografia. Os dados vêm do Auditor de Cobertura
(presença por UF via bbox, honestamente aproximada). HTML com tema claro/escuro, sem JS/libs.

Puro/defensivo: nunca levanta; degrada para uma mensagem se o auditor estiver indisponível."""
from __future__ import annotations

import sys
import html
import time
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.audit.mapa")

# UFs agrupadas por região (ordem de exibição) — rótulo de linha do mapa.
REGIOES = [
    ("Norte", ["AC", "AM", "AP", "PA", "RO", "RR", "TO"]),
    ("Nordeste", ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]),
    ("Centro-Oeste", ["DF", "GO", "MS", "MT"]),
    ("Sudeste", ["ES", "MG", "RJ", "SP"]),
    ("Sul", ["PR", "RS", "SC"]),
]

# Camadas exibidas como colunas (chave → rótulo curto).
COLUNAS = [
    ("rodovias", "Rodov."), ("drenagem", "Drenag."), ("massas_dagua", "Massas"),
    ("ferrovias", "Ferrov."), ("pontes", "Pontes"), ("travessias", "Travess."),
    ("hidrovias", "Hidrov."), ("eclusas", "Eclusas"),
    ("atracadouros_terminal", "Atrac."), ("complexos_portuarios", "Portos"),
    ("sinalizacao", "Sinaliz."),
]

_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a2230;--muted:#5b6676;--line:#e6e9ef;
  --ok:#1a7f4b;--okbg:#e6f4ec;--bad:#b42318;--badbg:#fbeae8;--chip:#eef2f7;--accent:#1f6feb}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;
  --ok:#3fb950;--okbg:#10251a;--bad:#ff6a5e;--badbg:#2a1512;--chip:#1c232c;--accent:#4a9eff}}
:root[data-theme="dark"]{--bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;
  --ok:#3fb950;--okbg:#10251a;--bad:#ff6a5e;--badbg:#2a1512;--chip:#1c232c;--accent:#4a9eff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
.wrap{max-width:1040px;margin:0 auto;padding:32px 16px 56px}
h1{font-size:1.5rem;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 20px;font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;overflow-x:auto}
table{border-collapse:collapse;font-size:.82rem;width:100%}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap}
th.uf,td.uf{text-align:left;font-weight:600}
th{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.03em}
td.num{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted)}
.reg{background:var(--chip);font-weight:700;text-align:left}
.cell{font-weight:700;border-radius:6px}
.ok{color:var(--ok);background:var(--okbg)}
.bad{color:var(--bad);background:var(--badbg)}
.legenda{display:flex;gap:16px;margin:14px 0 0;color:var(--muted);font-size:.85rem;flex-wrap:wrap}
.pill{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:middle;margin-right:6px}
footer{color:var(--muted);font-size:.78rem;margin-top:14px;text-align:center}
"""


def _laudo(rapido: bool):
    from audit import coverage_auditor as ca
    return ca.auditar(rapido=rapido)


def _dossie_rota(rota):
    """Resolve uma rota (string 'A;B' de nomes, ou lista de nomes/coords) para um dossiê. None se
    indisponível. Usado para sobrepor a rota ao mapa."""
    if not rota:
        return None
    try:
        from geo import dossie_rota as dr
        if isinstance(rota, str):
            return dr.dossie_por_nomes(rota)[0]
        return dr.dossie_por_nomes(list(rota))[0]
    except Exception:
        logger.warning("[MAPA] dossiê da rota sobreposta falhou.", exc_info=True)
        return None


def construir_html(rapido: bool = False, rota=None) -> str:
    """Monta o HTML do Mapa de Cobertura. Com `rota` (nomes 'A/UF;B/UF' ou coords), sobrepõe a rota:
    cabeçalho-resumo + marca as UFs atravessadas. Nunca levanta."""
    quando = time.strftime("%d/%m/%Y %H:%M")
    try:
        laudo = _laudo(rapido)
    except Exception:
        laudo = None
    dd_rota = _dossie_rota(rota)
    ufs_rota = set((dd_rota.get("travessia_territorial", {}) or {}).get("ufs") or []) if dd_rota else set()
    partes = ["<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
              "<meta name='viewport' content='width=device-width,initial-scale=1'>",
              "<title>Mapa de Cobertura Nacional — OpenRotas</title><style>", _CSS,
              "</style></head><body><div class='wrap'>",
              "<h1>Mapa de Cobertura Nacional</h1>",
              "<p class='sub'>Presença por UF × camada (números reais; presença espacial por bbox, "
              "aproximada) · gerado em %s</p>" % html.escape(quando)]
    if not laudo:
        partes.append("<p>Auditoria indisponível.</p></div></body></html>")
        return "".join(partes)
    # Camada de ROTA sobreposta (opcional): resumo + marcação das UFs atravessadas.
    if dd_rota and not dd_rota.get("erro"):
        o = dd_rota.get("origem", {}).get("municipio", {})
        d = dd_rota.get("destino", {}).get("municipio", {})
        h = dd_rota.get("hidrografia", {})
        partes.append("<section class='card'><h2 style='margin:0 0 8px'>Rota sobreposta</h2>"
                      "<p class='sub' style='margin:0'>%s/%s → %s/%s · UFs: %s · %d trechos de rio · "
                      "%d ponte(s)</p></section>"
                      % (html.escape(str(o.get("nome", "?"))), html.escape(str(o.get("uf", "?"))),
                         html.escape(str(d.get("nome", "?"))), html.escape(str(d.get("uf", "?"))),
                         ", ".join(sorted(ufs_rota)) or "—", h.get("trechos", 0),
                         dd_rota.get("camadas", {}).get("pontes", {}).get("feicoes", 0)))
    presentes = {ch: set((laudo.get("camadas", {}).get(ch, {}) or {}).get("ufs_presentes") or [])
                 for ch, _ in COLUNAS}
    por_uf = (laudo.get("municipios", {}) or {}).get("por_uf", {}) or {}
    col_rota = "<th>Rota</th>" if ufs_rota else ""
    partes.append("<div class='card'><table><thead><tr><th class='uf'>UF</th><th class='num'>Mun.</th>" + col_rota)
    for _, rot in COLUNAS:
        partes.append("<th>%s</th>" % html.escape(rot))
    partes.append("</tr></thead><tbody>")
    ncols = len(COLUNAS) + 2 + (1 if ufs_rota else 0)
    for regiao, ufs in REGIOES:
        partes.append("<tr><td class='reg' colspan='%d'>%s</td></tr>" % (ncols, html.escape(regiao)))
        for uf in ufs:
            partes.append("<tr><td class='uf'>%s</td><td class='num'>%s</td>" % (uf, por_uf.get(uf, 0)))
            if ufs_rota:
                na_rota = uf in ufs_rota
                partes.append("<td class='cell %s'>%s</td>" % ("ok" if na_rota else "", "●" if na_rota else ""))
            for ch, _ in COLUNAS:
                ok = uf in presentes.get(ch, set())
                partes.append("<td class='cell %s'>%s</td>" % ("ok" if ok else "bad", "✓" if ok else "—"))
            partes.append("</tr>")
    partes.append("</tbody></table>")
    partes.append("<div class='legenda'>"
                  "<span><span class='pill' style='background:var(--ok)'></span>presença detectada</span>"
                  "<span><span class='pill' style='background:var(--bad)'></span>sem dados nesta UF</span>"
                  "<span>Mun. = municípios na UF (base IBGE)</span></div>")
    partes.append("</div>")
    r = laudo.get("resumo", {})
    partes.append("<footer>%s/%s dimensões OK · presença por UF é espacial (bbox), aproximada — "
                  "camadas naturalmente parciais (ex.: eclusas) aparecem com UFs vazias, sem mascarar."
                  "</footer>" % (r.get("ok", "?"), r.get("dimensoes", "?")))
    partes.append("</div></body></html>")
    return "".join(partes)


def gerar(caminho, rapido: bool = False, rota=None) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(rapido=rapido, rota=rota), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[MAPA] falha ao gerar o mapa de cobertura.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    rapido = "--rapido" in argv
    rota = None
    if "--rota" in argv:
        i = argv.index("--rota")
        rota = argv[i + 1] if i + 1 < len(argv) else None
    try:
        import desktop_config as cfg
        destino = cfg.ensure_user_dirs()["cache"] / "mapa_cobertura.html"
    except Exception:
        destino = Path("mapa_cobertura.html")
    got = gerar(destino, rapido=rapido, rota=rota)
    if not got:
        print("Falha ao gerar o mapa de cobertura.")
        return 1
    print("Mapa de Cobertura: %s" % got)
    try:
        import webbrowser
        webbrowser.open(Path(got).as_uri())
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
