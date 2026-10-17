# -*- coding: utf-8 -*-
"""OpenRotas Desktop — COMPARAÇÃO DE ROTAS ALTERNATIVAS (§27/§28/§29 — camada desktop).

Dado VÁRIAS rotas candidatas para o MESMO par origem→destino (traçados alternativos, ou destinos
concorrentes), analisa cada uma com TODA a inteligência nacional já instalada (reusa o `dossie()`
auditado — rios cruzados, dependência de balsa/travessia, pontes, transições de UF) e as RANQUEIA
por COMPLEXIDADE LOGÍSTICA, destacando a mais simples/segura de operar.

  • pontuar(dossie)      — nota de complexidade logística (quanto MENOR, mais simples), com o
                           detalhamento transparente de cada fator (nada de caixa-preta);
  • comparar(rotas, …)   — roda o dossiê de cada rota, pontua, ordena e aponta a RECOMENDADA;
  • render_texto / gerar_html / exportar_excel — entrega para o usuário final (tabela + recomendação).

HONESTIDADE (§1/§71): isto é um AUXÍLIO DE PLANEJAMENTO geoespacial do desktop, com pesos
EXPLÍCITOS e números REAIS das bases — NÃO é, e não substitui, a decisão de rota da aplicação
(WINNER/Google), que permanece intocada. A análise é de nível bbox/corredor, aproximada, como no
resto do dossiê. Puro/defensivo: nunca levanta; cada rota que falha é marcada e sai do ranking."""
from __future__ import annotations

import sys
import html
import time
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.geo.comparativo")

# Pesos EXPLÍCITOS da complexidade logística (quanto MAIOR o peso, mais o fator "pesa contra" a
# rota). Escolhidos por risco operacional real no transporte terrestre brasileiro:
#   • travessia/balsa: dependência de terceiros, horário e fila — o maior risco de atraso;
#   • transição de UF: mudança de jurisdição/fiscalização ao longo do trajeto;
#   • rio navegável cruzado: curso d'água relevante (ponte/estrutura obrigatória);
#   • ponte: cruzamento com infraestrutura dedicada (menor risco que balsa);
#   • trecho de rio (qualquer): sinal fraco de terreno recortado (peso pequeno).
PESOS = {
    "travessias": 10.0,
    "transicoes_uf": 3.0,
    "rios_navegaveis": 2.0,
    "pontes": 1.0,
    "trechos_rio": 0.05,
}

_FATORES = [
    ("travessias", "travessias/balsas"),
    ("transicoes_uf", "transições de UF"),
    ("rios_navegaveis", "rios navegáveis"),
    ("pontes", "pontes"),
    ("trechos_rio", "trechos de rio"),
]


def pontuar(dossie: dict) -> tuple:
    """Nota de COMPLEXIDADE LOGÍSTICA de um dossiê (quanto MENOR, mais simples/segura a rota) e o
    detalhamento por fator. Devolve (score|None, componentes). None se o dossiê falhou. Nunca levanta."""
    try:
        if not dossie or dossie.get("erro"):
            return None, {}
        cam = dossie.get("camadas", {}) or {}
        h = dossie.get("hidrografia", {}) or {}
        tt = dossie.get("travessia_territorial", {}) or {}

        def _feic(nome):
            return int((cam.get(nome, {}) or {}).get("feicoes", 0) or 0)

        comp = {
            "travessias": _feic("travessias"),
            "transicoes_uf": max(0, len(tt.get("ufs", []) or []) - 1),
            "rios_navegaveis": int(h.get("navegaveis", 0) or 0),
            "pontes": _feic("pontes"),
            "trechos_rio": int(h.get("trechos", 0) or 0),
        }
        score = round(sum(PESOS[k] * comp[k] for k in PESOS), 2)
        return score, comp
    except Exception:
        logger.warning("[COMPARATIVO] pontuação falhou.", exc_info=True)
        return None, {}


def _rotulo(dd: dict, fallback: str) -> str:
    """Rótulo legível da rota a partir do dossiê (origem→destino) ou do fallback informado."""
    try:
        o = (dd.get("origem", {}) or {}).get("municipio", {}) or {}
        d = (dd.get("destino", {}) or {}).get("municipio", {}) or {}
        if o.get("nome") and d.get("nome"):
            return "%s/%s → %s/%s" % (o.get("nome", "?"), o.get("uf", "?"),
                                      d.get("nome", "?"), d.get("uf", "?"))
    except Exception:
        pass
    return fallback


def comparar(rotas, folga_km: float = 3.0, usar_osrm: bool = False, osrm_url=None, nomes=None) -> dict:
    """Compara várias rotas candidatas. `rotas` = lista em que cada item é uma lista de coords
    [(lon,lat),...] OU uma string de nomes 'Cidade/UF;Cidade/UF'. `nomes` (opcional) rotula cada
    rota. Devolve {gerado_em, rotas:[{rotulo,score,componentes,dossie,ok}], recomendada, criterios}.
    Ordena por score crescente (a 1ª é a mais simples). Nunca levanta."""
    from geo import dossie_rota as dr
    rotas = list(rotas or [])
    nomes = list(nomes or [])
    itens = []
    for i, rota in enumerate(rotas):
        fallback = nomes[i] if i < len(nomes) and nomes[i] else ("Rota %d" % (i + 1))
        try:
            if isinstance(rota, str):
                dd, _ = dr.dossie_por_nomes(rota, folga_km=folga_km, usar_osrm=usar_osrm, osrm_url=osrm_url)
            else:
                dd = dr.dossie(list(rota), folga_km=folga_km, usar_osrm=usar_osrm, osrm_url=osrm_url)
        except Exception:
            logger.warning("[COMPARATIVO] dossiê da rota %r falhou.", fallback, exc_info=True)
            dd = {"erro": "dossiê falhou"}
        score, comp = pontuar(dd)
        itens.append({
            "indice_original": i,
            "rotulo": _rotulo(dd, fallback),
            "consulta": fallback,
            "ok": score is not None,
            "score": score,
            "componentes": comp,
            "dossie": dd,
        })
    # Ordena: rotas válidas por score crescente (empate → menos pontos de rota, depois ordem
    # original); inválidas por último, preservando a ordem.
    def _chave(it):
        if it["score"] is None:
            return (1, 0.0, 0, it["indice_original"])
        # empate no score → menos pontos de corredor, depois ordem original (estável/determinístico).
        return (0, it["score"], _n_pontos(it["dossie"]), it["indice_original"])

    ordenadas = sorted(itens, key=_chave)
    recomendada = next((it["rotulo"] for it in ordenadas if it["ok"]), None)
    return {
        "gerado_em": time.strftime("%d/%m/%Y %H:%M"),
        "rotas": ordenadas,
        "recomendada": recomendada,
        "total": len(ordenadas),
        "validas": sum(1 for it in ordenadas if it["ok"]),
        "criterios": dict(PESOS),
        "nota": ("Complexidade logística (menor = mais simples); pesos explícitos; números reais "
                 "por corredor (bbox, aproximado). Auxílio de planejamento — não substitui a "
                 "decisão de rota da aplicação."),
    }


def _n_pontos(dd: dict) -> int:
    try:
        return int(dd.get("pontos", 0) or 0)
    except Exception:
        return 0


def render_texto(cmp: dict) -> str:
    L = ["COMPARAÇÃO DE ROTAS — OpenRotas", "=" * 64,
         "gerado em %s · %d rota(s) (%d válida(s))"
         % (cmp.get("gerado_em", "?"), cmp.get("total", 0), cmp.get("validas", 0)), ""]
    for pos, it in enumerate(cmp.get("rotas", []), start=1):
        if not it["ok"]:
            L.append("  %2d. %-40s  (indisponível)" % (pos, it["rotulo"]))
            continue
        c = it["componentes"]
        marca = "★" if pos == 1 else " "
        L.append("  %s%2d. %-40s  score %6.2f" % (marca, pos, it["rotulo"], it["score"]))
        L.append("        balsas=%d · UFs(transições)=%d · rios naveg.=%d · pontes=%d · trechos rio=%d"
                 % (c.get("travessias", 0), c.get("transicoes_uf", 0), c.get("rios_navegaveis", 0),
                    c.get("pontes", 0), c.get("trechos_rio", 0)))
    L.append("")
    if cmp.get("recomendada"):
        L.append("RECOMENDADA (menor complexidade logística): %s" % cmp["recomendada"])
    L.append(cmp.get("nota", ""))
    return "\n".join(L)


_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a2230;--muted:#5b6676;--line:#e6e9ef;--accent:#1f6feb;
  --ok:#1a7f4b;--okbg:#e6f4ec;--warn:#9a6700;--chip:#eef2f7}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;--accent:#4a9eff;
  --ok:#3fb950;--okbg:#10251a;--warn:#d29922;--chip:#1c232c}}
:root[data-theme="dark"]{--bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;
  --accent:#4a9eff;--ok:#3fb950;--okbg:#10251a;--warn:#d29922;--chip:#1c232c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.55}
.wrap{max-width:960px;margin:0 auto;padding:32px 16px 56px}
h1{font-size:1.5rem;margin:0 0 2px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 20px;font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:0 0 16px}
.reco{border-left:4px solid var(--ok)}
.reco .badge{background:var(--okbg);color:var(--ok);font-weight:700;font-size:.72rem;
  padding:2px 9px;border-radius:999px;margin-left:8px}
.rt{font-size:1.05rem;font-weight:700;margin:0 0 2px}
.score{color:var(--muted);font-size:.9rem;margin:0 0 8px}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.03em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.best td{background:var(--okbg)}
.empty{color:var(--muted);font-style:italic}
footer{color:var(--muted);font-size:.78rem;margin-top:12px;text-align:center}
"""


def gerar_html(cmp: dict, caminho) -> str | None:
    """Escreve a Comparação de Rotas como HTML autossuficiente (tema claro/escuro). None em falha."""
    try:
        rotas = cmp.get("rotas", [])
        P = ["<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>Comparação de Rotas — OpenRotas</title><style>", _CSS,
             "</style></head><body><div class='wrap'>",
             "<h1>Comparação de Rotas</h1>",
             "<p class='sub'>%d rota(s) candidata(s) · %d válida(s) · gerado em %s</p>"
             % (cmp.get("total", 0), cmp.get("validas", 0), html.escape(cmp.get("gerado_em", "")))]
        reco = cmp.get("recomendada")
        if reco:
            P.append("<section class='card reco'><div class='rt'>%s<span class='badge'>RECOMENDADA</span></div>"
                     "<div class='score'>Menor complexidade logística entre as rotas comparadas.</div></section>"
                     % html.escape(str(reco)))
        P.append("<section class='card'><table><thead><tr>"
                 "<th>#</th><th>Rota</th><th class='num'>Score</th><th class='num'>Balsas</th>"
                 "<th class='num'>UFs↹</th><th class='num'>Rios naveg.</th><th class='num'>Pontes</th>"
                 "<th class='num'>Trechos rio</th></tr></thead><tbody>")
        for pos, it in enumerate(rotas, start=1):
            if not it["ok"]:
                P.append("<tr><td>%d</td><td>%s</td><td class='num' colspan='6'><span class='empty'>indisponível</span></td></tr>"
                         % (pos, html.escape(str(it["rotulo"]))))
                continue
            c = it["componentes"]
            cls = " class='best'" if pos == 1 else ""
            P.append("<tr%s><td>%d</td><td>%s</td><td class='num'>%.2f</td><td class='num'>%d</td>"
                     "<td class='num'>%d</td><td class='num'>%d</td><td class='num'>%d</td>"
                     "<td class='num'>%d</td></tr>"
                     % (cls, pos, html.escape(str(it["rotulo"])), it["score"],
                        c.get("travessias", 0), c.get("transicoes_uf", 0), c.get("rios_navegaveis", 0),
                        c.get("pontes", 0), c.get("trechos_rio", 0)))
        P.append("</tbody></table></section>")
        cr = cmp.get("criterios", {})
        P.append("<section class='card'><div class='score'>Pesos (quanto maior, mais pesa contra): "
                 "balsa %.0f · transição de UF %.0f · rio navegável %.0f · ponte %.0f · trecho de rio %.2f</div></section>"
                 % (cr.get("travessias", 0), cr.get("transicoes_uf", 0), cr.get("rios_navegaveis", 0),
                    cr.get("pontes", 0), cr.get("trechos_rio", 0)))
        P.append("<footer>%s</footer></div></body></html>" % html.escape(cmp.get("nota", "")))
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        pth.write_text("".join(P), encoding="utf-8")
        return str(pth)
    except Exception:
        logger.warning("[COMPARATIVO] falha ao gerar HTML.", exc_info=True)
        return None


def exportar_excel(cmp: dict, caminho) -> str | None:
    """Exporta a comparação para .xlsx (aba Comparacao). Requer openpyxl (já é dep do desktop)."""
    try:
        import pandas as pd
        linhas = []
        for pos, it in enumerate(cmp.get("rotas", []), start=1):
            c = it.get("componentes", {}) or {}
            linhas.append({
                "#": pos,
                "Rota": it.get("rotulo", ""),
                "Recomendada": "sim" if (pos == 1 and it.get("ok")) else "",
                "Score": it.get("score") if it.get("ok") else "",
                "Balsas/travessias": c.get("travessias", "") if it.get("ok") else "",
                "Transicoes_UF": c.get("transicoes_uf", "") if it.get("ok") else "",
                "Rios_navegaveis": c.get("rios_navegaveis", "") if it.get("ok") else "",
                "Pontes": c.get("pontes", "") if it.get("ok") else "",
                "Trechos_rio": c.get("trechos_rio", "") if it.get("ok") else "",
                "Status": "ok" if it.get("ok") else "indisponível",
            })
        pth = Path(caminho)
        pth.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(pth), engine="openpyxl") as xw:
            pd.DataFrame(linhas or [{"Rota": "—"}]).to_excel(xw, sheet_name="Comparacao", index=False)
        return str(pth)
    except Exception:
        logger.warning("[COMPARATIVO] falha ao exportar Excel.", exc_info=True)
        return None


def _parse_coords(texto):
    return [tuple(float(x) for x in par.split(",")) for par in str(texto).split(";") if par.strip()]


def _cli(argv=None) -> int:
    """CLI: rotas separadas por '||'. Coords: 'lon,lat;lon,lat || lon,lat;lon,lat'. Nomes:
    --nomes "Cidade/UF;Cidade/UF || Cidade/UF;Cidade/UF". [--html] [--excel] [--osrm]."""
    argv = argv if argv is not None else sys.argv[1:]
    usar_osrm = "--osrm" in argv
    por_nomes = "--nomes" in argv
    # coleta o argumento "payload": o 1º token que contém '||' ou (';' e ',').
    payload = None
    if por_nomes:
        j = argv.index("--nomes")
        payload = argv[j + 1] if j + 1 < len(argv) else None
    else:
        for a in argv:
            if a.startswith("--"):
                continue
            if "||" in a or (";" in a and "," in a):
                payload = a
                break
    if not payload:
        print('uso: --comparar "lon,lat;lon,lat || lon,lat;lon,lat" [--html] [--excel] [--osrm]')
        print('     --comparar --nomes "A/UF;B/UF || A/UF;C/UF"')
        return 2
    partes = [p.strip() for p in payload.split("||") if p.strip()]
    if len(partes) < 2:
        print("Informe pelo menos 2 rotas separadas por '||'.")
        return 2
    if por_nomes:
        rotas = partes                                   # strings de nomes
    else:
        rotas = []
        for p in partes:
            try:
                rotas.append(_parse_coords(p))
            except Exception:
                print("coords inválidas em %r" % p)
                return 2
    cmp = comparar(rotas, usar_osrm=usar_osrm)
    print(render_texto(cmp))
    if "--html" in argv or "--excel" in argv:
        try:
            import desktop_config as cfg
            exp = cfg.ensure_user_dirs()["exports"]
        except Exception:
            exp = Path(".")
        if "--html" in argv:
            got = gerar_html(cmp, exp / "comparacao_rotas.html")
            if got:
                print("\nHTML: %s" % got)
                try:
                    import webbrowser
                    webbrowser.open(Path(got).as_uri())
                except Exception:
                    pass
        if "--excel" in argv:
            got = exportar_excel(cmp, exp / "comparacao_rotas.xlsx")
            print("Excel: %s" % (got or "falha ao exportar"))
    return 0 if cmp.get("validas", 0) >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
