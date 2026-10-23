# -*- coding: utf-8 -*-
"""OpenRotas Desktop — PAINEL EXECUTIVO (Central de Inteligência Nacional) — visão única.

Uma página só, de marca, que consolida num relance TUDO que a edição desktop sabe sobre a
infraestrutura nacional instalada — reusando (sem reprocessar lógica) os auditores e o repositório
já existentes:

  • Mapa nacional por UF (coroplético, contorno ≈ municípios reais) colorido por presença rodoviária;
  • KPIs: UFs/27, municípios, feições multimodais, classes multimodais, prontidão offline;
  • Saúde dos dados (barra de proporção OK/Parcial/Ausente das dimensões);
  • Modais por volume de feições (gráfico de barras).

É o "landing" visual do software (atalho/menu e `--painel-executivo`). Puro/defensivo: cada bloco
degrada sozinho; nunca levanta. Offline e autossuficiente (herda o tema compartilhado)."""
from __future__ import annotations

import sys
import html
import logging
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
for _p in (_AQUI, _AQUI.parent, _AQUI.parent / "app", _AQUI.parent / "data_local",
           _AQUI.parent / "audit", _AQUI.parent / "geo"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger("openrotas.desktop.painel_exec")


def _tema():
    try:
        from resources import tema
        return tema
    except Exception:
        try:
            import tema
            return tema
        except Exception:
            return None


def _kpi(valor, rotulo) -> str:
    return ("<div class='kpi'><div class='v'>%s</div><div class='l'>%s</div></div>"
            % (html.escape(str(valor)), html.escape(str(rotulo))))


def _num_br(n) -> str:
    try:
        return "{:,}".format(int(n)).replace(",", ".")
    except Exception:
        return str(n)


def _bloco_mapa(tema) -> str:
    try:
        from audit import coverage_auditor as ca
        hulls = ca.hulls_uf()
        if not hulls:
            return ""
        laudo = ca.auditar(rapido=True)
        rod = set((laudo.get("camadas", {}).get("rodovias", {}) or {}).get("ufs_presentes") or [])
        polis = [{"uf": uf, "pts": pts, "classe": "teal" if uf in rod else "bad",
                  "dica": "%s — malha rodoviária %s" % (uf, "presente" if uf in rod else "ausente")}
                 for uf, pts in hulls.items()]
        leg = [{"rotulo": "com malha rodoviária", "cor": "var(--teal)"},
               {"rotulo": "sem presença detectada", "cor": "var(--bad)"}]
        m = tema.mapa_coropletico(polis, titulo="COBERTURA NACIONAL POR UF", legenda=leg)
        return ("<section class='card'><h2>Mapa nacional</h2>%s</section>" % m) if m else ""
    except Exception:
        logger.warning("[PAINEL-EXEC] bloco mapa falhou.", exc_info=True)
        return ""


def _dados() -> dict:
    """Coleta defensiva dos números de todas as fontes. Campos ausentes viram None/0."""
    d = {"ufs": 0, "municipios": 0, "feicoes": 0, "classes": 0, "offline": None,
         "saude": None, "modais": []}
    try:
        from audit import coverage_auditor as ca
        laudo = ca.auditar(rapido=True)
        d["ufs"] = (laudo.get("estados", {}) or {}).get("encontrado", 0)
        d["municipios"] = (laudo.get("municipios", {}) or {}).get("encontrado", 0)
    except Exception:
        pass
    try:
        from geo import repositorio
        inv = repositorio.GeoIntelligenceRepository().inventario_multimodal()
        d["feicoes"] = inv.get("total_feicoes", 0)
        d["classes"] = len(inv.get("classes_presentes", []) or [])
        d["modais"] = sorted(((k, int(v)) for k, v in (inv.get("classes", {}) or {}).items()),
                             key=lambda kv: -kv[1])
    except Exception:
        pass
    try:
        import desktop_config as cfg
        import local_data
        reg = local_data.LocalDataRegistry(cfg.app_root(), cfg.user_data_dir() / "data_local")
        d["offline"] = reg.offline_pronto()
    except Exception:
        pass
    try:
        from audit import saude_nacional as sn
        d["saude"] = sn.diagnostico(rapido=True)
    except Exception:
        pass
    try:
        from resources import provisionamento as _prov
        d["motor"] = _prov.status_motor_rotas()
    except Exception:
        try:
            import provisionamento as _prov
            d["motor"] = _prov.status_motor_rotas()
        except Exception:
            d["motor"] = None
    return d


def construir_html() -> str:
    """Monta o Painel Executivo (HTML completo de marca). Nunca levanta."""
    tema = _tema()
    d = _dados()
    if tema is None:   # fallback mínimo (sem o tema compartilhado)
        return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Painel "
                "Executivo — OpenRotas</title></head><body><h1>Painel Executivo</h1>"
                "<p>UFs %s/27 · municípios %s · feições %s</p></body></html>"
                % (d["ufs"], _num_br(d["municipios"]), _num_br(d["feicoes"])))
    off = d.get("offline") or {}
    if off.get("pronto"):
        off_txt = "pronto"
    elif off.get("geocodificacao_hidro_local"):
        off_txt = "parcial"
    else:
        off_txt = "—"
    # Motor de rotas: o que as ANÁLISES vão usar — rodoviário local real (OSRM no ar) × estimativa.
    # É a distinção que mais pesa na paridade com o web (que sempre roteia de verdade), então entra
    # no panorama executivo. Reusa status_motor_rotas() (mesma fonte da Central de Dados).
    mot = d.get("motor") or {}
    if mot.get("local_no_ar"):
        motor_txt = "rodoviário local"
    elif mot.get("ferramentas_modo"):
        motor_txt = "estimado"
    else:
        motor_txt = "—"
    corpo = ["<section class='card'><h2>Panorama</h2><div class='kpis'>",
             _kpi("%s/27" % d["ufs"], "Estados (UFs)"),
             _kpi(_num_br(d["municipios"]), "Municípios"),
             _kpi(_num_br(d["feicoes"]), "Feições multimodais"),
             _kpi(d["classes"], "Classes multimodais"),
             _kpi(off_txt, "Prontidão offline"),
             _kpi(motor_txt, "Motor de rotas"),
             "</div></section>",
             _bloco_mapa(tema)]
    # Saúde dos dados (proporção das dimensões).
    sa = d.get("saude") or {}
    r = sa.get("resumo") or {}
    if r:
        segs = [{"rotulo": "OK", "valor": r.get("ok", 0), "classe": "ok"},
                {"rotulo": "Parciais", "valor": r.get("parciais", 0), "classe": "warn"},
                {"rotulo": "Ausentes", "valor": r.get("ausentes", 0), "classe": "bad"}]
        g = tema.barra_proporcao(segs, titulo="SAÚDE DOS DADOS (DIMENSÕES)")
        if g:
            corpo.append("<section class='card'><h2>Saúde dos dados</h2>%s</section>" % g)
    # Modais por volume de feições.
    if d.get("modais"):
        itens = [{"rotulo": k, "valor": v, "dica": "%s: %s feições" % (k, _num_br(v))}
                 for k, v in d["modais"]]
        g = tema.grafico_barras(itens, titulo="MODAIS POR VOLUME DE FEIÇÕES")
        if g:
            corpo.append("<section class='card'><h2>Rede multimodal</h2>%s</section>" % g)
    rodape = ("Números reais das bases instaladas · presença por UF e contornos são espaciais "
              "(aproximados) · dados locais, nada sai do seu computador.")
    sub = "Central de Inteligência Nacional · visão consolidada"
    return tema.documento("Painel Executivo", sub, "".join(corpo), rodape)


def gerar(caminho) -> str | None:
    try:
        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(construir_html(), encoding="utf-8")
        return str(p)
    except Exception:
        logger.warning("[PAINEL-EXEC] falha ao gerar o painel executivo.", exc_info=True)
        return None


def _cli(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        import desktop_config as cfg
        destino = cfg.ensure_user_dirs()["cache"] / "painel_executivo.html"
    except Exception:
        destino = Path("painel_executivo.html")
    got = gerar(destino)
    if not got:
        print("Falha ao gerar o Painel Executivo.")
        return 1
    print("Painel Executivo: %s" % got)
    if "--no-open" not in argv:
        try:
            import webbrowser
            webbrowser.open(Path(got).as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
