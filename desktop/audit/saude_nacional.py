# -*- coding: utf-8 -*-
"""OpenRotas Desktop — SAÚDE DOS DADOS NACIONAIS (§39). Painel único de status.

Consolida, numa só tela, o estado de TODA a infraestrutura de dados nacional, compondo os
auditores já existentes (sem reprocessar lógica):

  • Cobertura territorial  — Auditor de Cobertura (UFs/municípios/camadas por UF);
  • Integridade geométrica — Auditor de Integridade (inválidas/fora do Brasil);
  • Multimodal             — inventário de modais e feições (GeoIntelligenceRepository);
  • Prontidão offline      — bases essenciais + grafo de roteamento (local_data);
  • Recursos               — grafo OSRM e índices auxiliares.

Cada dimensão recebe um status honesto (OK / PARCIAL / AUSENTE) derivado dos dados REAIS. Entrega
dict + texto + HTML (board com "Ver detalhes" por dimensão). Puro/defensivo: nunca levanta; cada
bloco degrada sozinho."""
from __future__ import annotations

import sys
import html
import time
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local", _AQUI.parent / "geo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.audit.saude")

OK, PARCIAL, AUSENTE = "OK", "PARCIAL", "AUSENTE"


def diagnostico(rapido: bool = True) -> dict:
    """Agrega o estado de todas as dimensões de dados nacionais. Nunca levanta."""
    t0 = time.perf_counter()
    d = {"gerado_em": time.strftime("%d/%m/%Y %H:%M"), "dimensoes": []}

    def _add(nome, status, resumo, detalhe=""):
        d["dimensoes"].append({"nome": nome, "status": status, "resumo": resumo, "detalhe": detalhe})

    # 1) Cobertura territorial
    try:
        from audit import coverage_auditor as ca
        laudo = ca.auditar(rapido=rapido)
        e, m = laudo.get("estados", {}), laudo.get("municipios", {})
        camadas = laudo.get("camadas", {})
        parciais = [c["rotulo"] for c in camadas.values() if c.get("status") == "PARCIAL"]
        st = OK if (e.get("status") == "OK" and m.get("status") == "OK") else PARCIAL
        _add("Cobertura territorial", st,
             "UFs %s/27 · municípios %s · %d camadas" % (e.get("encontrado", 0), m.get("encontrado", 0), len(camadas)),
             ("camadas naturalmente parciais: %s" % ", ".join(parciais)) if parciais else "cobertura nacional validada")
        d["cobertura"] = {"ufs": e.get("encontrado", 0), "municipios": m.get("encontrado", 0)}
    except Exception:
        _add("Cobertura territorial", AUSENTE, "indisponível")

    # 2) Integridade geométrica
    try:
        from audit import integridade as ig
        aud = ig.auditar()
        r = aud.get("resumo", {})
        st = OK if r.get("status") == "OK" else PARCIAL
        _add("Integridade geométrica", st,
             "%s/%s camadas limpas" % (r.get("limpas", 0), r.get("instaladas", 0)),
             "inválidas=%d · fora do Brasil=%d" % (r.get("total_invalidas", 0), r.get("total_fora_brasil", 0)))
    except Exception:
        _add("Integridade geométrica", AUSENTE, "indisponível")

    # 3) Multimodal
    try:
        from geo import repositorio
        inv = repositorio.GeoIntelligenceRepository().inventario_multimodal()
        ncl = len(inv.get("classes_presentes", []))
        st = OK if ncl >= 5 else PARCIAL
        _add("Rede multimodal", st,
             "%d classes · %s feições" % (ncl, "{:,}".format(inv.get("total_feicoes", 0)).replace(",", ".")),
             "classes: %s" % ", ".join(inv.get("classes_presentes", [])))
    except Exception:
        _add("Rede multimodal", AUSENTE, "indisponível")

    # 4) Prontidão offline
    try:
        import desktop_config as cfg
        import local_data
        reg = local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")
        off = reg.offline_pronto()
        if off.get("pronto"):
            st, resumo = OK, "pronto para operar offline"
        elif off.get("geocodificacao_hidro_local"):
            st, resumo = PARCIAL, "bases locais OK; falta o grafo de roteamento"
        else:
            st, resumo = AUSENTE, "bases essenciais ausentes"
        _add("Prontidão offline", st, resumo,
             ("falta(m): %s" % ", ".join(off.get("faltam", []))) if off.get("faltam") else "")
    except Exception:
        _add("Prontidão offline", AUSENTE, "indisponível")

    # 5) Recursos (grafo + índices)
    try:
        from resources import resource_manager as rm
        v = rm.verificar()
        st = OK if v.get("ok") else PARCIAL
        _add("Recursos e integridade de bases", st,
             "verificação %s" % ("OK" if v.get("ok") else "com pendências"),
             ("faltam: %s" % ", ".join(v.get("faltam_obrigatorios", []))) if v.get("faltam_obrigatorios") else "")
    except Exception:
        _add("Recursos e integridade de bases", AUSENTE, "indisponível")

    dims = [x["status"] for x in d["dimensoes"]]
    d["resumo"] = {"total": len(dims), "ok": dims.count(OK), "parciais": dims.count(PARCIAL),
                   "ausentes": dims.count(AUSENTE),
                   "status": OK if all(s == OK for s in dims) else (AUSENTE if AUSENTE in dims else PARCIAL),
                   "ms": round((time.perf_counter() - t0) * 1000.0, 1)}
    return d


def render_texto(d: dict) -> str:
    L = ["SAÚDE DOS DADOS NACIONAIS — OpenRotas", "=" * 56, "gerado em %s" % d.get("gerado_em", "?"), ""]
    marca = {"OK": "✓", "PARCIAL": "◐", "AUSENTE": "✗"}
    for x in d.get("dimensoes", []):
        L.append("  %s %-32s %s" % (marca.get(x["status"], "?"), x["nome"], x["resumo"]))
        if x.get("detalhe"):
            L.append("        %s" % x["detalhe"])
    r = d.get("resumo", {})
    L.append("")
    L.append("Resumo: %s dimensões → %s OK · %s parciais · %s ausentes (%s)"
             % (r.get("total", "?"), r.get("ok", "?"), r.get("parciais", "?"),
                r.get("ausentes", "?"), r.get("status", "?")))
    return "\n".join(L)


_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a2230;--muted:#5b6676;--line:#e6e9ef;
  --ok:#1a7f4b;--okbg:#e6f4ec;--warn:#9a6700;--warnbg:#fdf4e3;--bad:#b42318;--badbg:#fbeae8}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;
  --ok:#3fb950;--okbg:#10251a;--warn:#d29922;--warnbg:#241a05;--bad:#ff6a5e;--badbg:#2a1512}}
:root[data-theme="dark"]{--bg:#0e1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa4b2;--line:#283039;
  --ok:#3fb950;--okbg:#10251a;--warn:#d29922;--warnbg:#241a05;--bad:#ff6a5e;--badbg:#2a1512}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:32px 16px 56px}
h1{font-size:1.5rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px;font-size:.9rem}
.dim{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);
  border-radius:12px;padding:14px 16px;margin:0 0 12px}
.dim.ok{border-left-color:var(--ok)} .dim.parcial{border-left-color:var(--warn)}
.dim.ausente{border-left-color:var(--bad)}
.dim h2{font-size:1.02rem;margin:0 0 2px;display:flex;align-items:center;gap:8px}
.badge{font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:999px}
.b-ok{color:var(--ok);background:var(--okbg)} .b-parcial{color:var(--warn);background:var(--warnbg)}
.b-ausente{color:var(--bad);background:var(--badbg)}
.dim .resumo{font-size:.95rem} .dim details{margin-top:6px;color:var(--muted);font-size:.86rem}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.kpi{flex:1 1 120px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .v{font-size:1.5rem;font-weight:700}.kpi .l{color:var(--muted);font-size:.78rem}
footer{color:var(--muted);font-size:.78rem;margin-top:12px;text-align:center}
"""


def construir_html(rapido: bool = True) -> str:
    d = diagnostico(rapido=rapido)
    r = d.get("resumo", {})
    cls = {"OK": "ok", "PARCIAL": "parcial", "AUSENTE": "ausente"}
    bcl = {"OK": "b-ok", "PARCIAL": "b-parcial", "AUSENTE": "b-ausente"}
    P = ["<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         "<title>Saúde dos Dados Nacionais — OpenRotas</title><style>", _CSS,
         "</style></head><body><div class='wrap'>",
         "<h1>Saúde dos Dados Nacionais</h1>",
         "<p class='sub'>Estado consolidado da infraestrutura de dados · gerado em %s</p>"
         % html.escape(d.get("gerado_em", "")),
         "<div class='kpis'>",
         "<div class='kpi'><div class='v'>%s/%s</div><div class='l'>Dimensões OK</div></div>" % (r.get("ok", 0), r.get("total", 0)),
         "<div class='kpi'><div class='v'>%s</div><div class='l'>Parciais</div></div>" % r.get("parciais", 0),
         "<div class='kpi'><div class='v'>%s</div><div class='l'>Ausentes</div></div>" % r.get("ausentes", 0),
         "</div>"]
    for x in d.get("dimensoes", []):
        P.append("<section class='dim %s'><h2>%s <span class='badge %s'>%s</span></h2>"
                 "<div class='resumo'>%s</div>%s</section>"
                 % (cls.get(x["status"], ""), html.escape(x["nome"]), bcl.get(x["status"], ""),
                    x["status"], html.escape(x["resumo"]),
                    ("<details><summary>Ver detalhes</summary>%s</details>" % html.escape(x["detalhe"])) if x.get("detalhe") else ""))
    P.append("<footer>Números derivados dos dados instalados; cobertura por UF é espacial (bbox), aproximada.</footer>")
    P.append("</div></body></html>")
    return "".join(P)


def gerar(caminho, rapido: bool = True) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(rapido=rapido), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[SAUDE] falha ao gerar o painel.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--html" in argv:
        try:
            import desktop_config as cfg
            destino = cfg.ensure_user_dirs()["cache"] / "saude_dados_nacionais.html"
        except Exception:
            destino = Path("saude_dados_nacionais.html")
        got = gerar(destino)
        if got:
            print("Saúde dos Dados Nacionais: %s" % got)
            try:
                import webbrowser
                webbrowser.open(Path(got).as_uri())
            except Exception:
                pass
            return 0
        print("Falha ao gerar o painel.")
        return 1
    d = diagnostico()
    print(render_texto(d))
    return 0 if d["resumo"]["status"] != AUSENTE else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
