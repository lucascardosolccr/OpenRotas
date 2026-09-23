"""
XAI Formatter - explicações auditáveis do enriquecimento geoespacial IBGE.

Funções PURAS que convertem a saída de `enrichment_engine` (enriquecer_ponto /
enriquecer_rota) e de `validators` (confianca) em Markdown/HTML legíveis para o
painel de auditoria — sem nenhum efeito colateral (testável com fixtures).
"""

from __future__ import annotations

_BADGE_NIVEL = {
    "alta": "🟢",
    "media": "🟡",
    "baixa": "🔴",
}


def formatar_confianca(confianca: dict) -> str:
    """Uma linha-resumo: pontuação, nível e fontes que concordam."""
    if not confianca:
        return "_confiança indisponível_"
    pts = confianca.get("pontuacao")
    nivel = confianca.get("nivel", "baixa")
    badge = _BADGE_NIVEL.get(nivel, "⚪")
    fontes = confianca.get("fontes_concordam") or []
    linha = "**Confiança:** %s **%d/100** (%s)" % (badge, int(pts or 0), nivel.upper())
    if fontes:
        linha += " — fontes: %s" % "; ".join(fontes)
    return linha


_CLASSIF_ESTACAO = {
    "direta": ("🎯", "referência direta", "mede o **mesmo rio** e fica próxima — representa bem o ponto"),
    "aproximada": ("📍", "referência aproximada", "mesmo rio porém mais distante, ou muito próxima sem rio confirmado"),
    "regional": ("🗺️", "referência regional", "estação mais distante e/ou de outro curso d'água — leitura só indicativa"),
}


def _estacao_rotulo(est: dict | None, ref: str = "") -> str:
    """Linha compacta da estação ANA de referência, com a CLASSIFICAÇÃO de exatidão (direta/aproximada/regional)."""
    if not est:
        return ""
    _tel = " · telemétrica" if str(est.get("tipo", "")).lower().startswith("telem") else ""
    _uf = ", %s" % est.get("uf") if est.get("uf") else ""
    _ic, _rot, _ = _CLASSIF_ESTACAO.get(str(est.get("classificacao", "")), ("📈", "referência", ""))
    return "**%s Estação ANA (%s · %s):** `%s` — %s (%s%s) a %s km%s" % (
        _ic, ref or "ref", _rot, est.get("codigo"), est.get("nome"), est.get("rio") or "rio n/d",
        _uf, est.get("distancia_km"), _tel)


def _rodovia_rotulo(rod: dict | None) -> str:
    """Linha compacta da rodovia de referência (sigla · jurisdição · revestimento · distância)."""
    if not rod:
        return ""
    _partes = [str(rod.get("via", "")).strip()]
    if rod.get("jurisdicao"):
        _partes.append(str(rod["jurisdicao"]))
    if rod.get("revestimento") and rod["revestimento"] != "—":
        _partes.append(str(rod["revestimento"]))
    return "**🛣️ Rodovia de referência:** %s a %s km" % (" · ".join(_partes), rod.get("distancia_km"))


def _ferrovia_rotulo(fer: dict | None) -> str:
    """Linha compacta da ferrovia de referência (operadora/linha · bitola · situação · distância)."""
    if not fer:
        return ""
    _partes = [str(fer.get("via", "")).strip()]
    for _k in ("bitola", "situacao"):
        _v = str(fer.get(_k, "")).strip()
        if _v and _v.lower() not in ("", "desconhecida", "desconhecido", "—", "nan"):
            _partes.append(_v)
    return "**🚂 Ferrovia de referência:** %s a %s km" % (" · ".join(_partes), fer.get("distancia_km"))


def _mun_rotulo(municipio: dict | None) -> str:
    if not municipio:
        return "_fora das malhas municipais IBGE_"
    nome = municipio.get("nome")
    geo = municipio.get("geocodigo")
    return "%s (%s)" % (nome, geo) if geo else str(nome)


def formatar_ponto(enriquecido: dict) -> str:
    """Painel Markdown para `enrichment_engine.enriquecer_ponto(...)`."""
    conf = (enriquecido or {}).get("confianca") or {}
    linhas = []
    linhas.append("#### 🧠 XAI — enriquecimento do ponto")
    linhas.append(formatar_confianca(conf))
    linhas.append("")

    mun = (enriquecido or {}).get("municipio")
    linhas.append("**📍 Município IBGE:** %s" % _mun_rotulo(mun))

    rio = (enriquecido or {}).get("rio_mais_proximo")
    if rio:
        nav = rio.get("navegavel")
        linhas.append("**🌊 Rio mais próximo:** %s — %s km%s" % (
            rio.get("nome"), rio.get("distancia_km"),
            (" (navegável: %s)" % nav) if nav else ""))

    balsas = (enriquecido or {}).get("balsas_confirmadas") or []
    if balsas:
        linhas.append("**🛶 Balsas no entorno:** %s" % "; ".join(
            "`%s` a %s km" % (b.get("nome"), b.get("distancia_km")) for b in balsas[:5]))

    pontes = (enriquecido or {}).get("pontes_encontradas") or []
    if pontes:
        linhas.append("**🌉 Pontes próximas (top):** %s" % "; ".join(
            "`%s` a %s km" % (p.get("nome"), p.get("distancia_km")) for p in pontes[:5]))

    est = (enriquecido or {}).get("estacao_ana")
    if est:
        linhas.append(_estacao_rotulo(est, "ponto"))
        _cl = _CLASSIF_ESTACAO.get(str(est.get("classificacao", "")))
        if _cl and _cl[2]:
            linhas.append("<small>_%s._</small>" % _cl[2])

    rod = (enriquecido or {}).get("rodovia_ref")
    if rod:
        linhas.append(_rodovia_rotulo(rod))

    fer = (enriquecido or {}).get("ferrovia_ref")
    if fer:
        linhas.append(_ferrovia_rotulo(fer))

    fonte = (enriquecido or {}).get("fonte")
    if fonte:
        linhas.append("")
        linhas.append("_Fonte: %s_" % fonte)
    return "\n".join(linhas)


def formatar_enriquecimento(enriquecido: dict) -> str:
    """Painel Markdown completo para `enrichment_engine.enriquecer_rota(...)`."""
    if not enriquecido:
        return "_enriquecimento indisponível_"

    linhas = []
    linhas.append("#### 🧠 XAI — auditoria de trecho (IBGE local)")

    conf = enriquecido.get("confianca_geral")
    nivel = enriquecido.get("confianca_nivel") or "—"
    linhas.append("**⚖️ Confiança geral do trecho:** %s **%s/100** (%s)" % (
        _BADGE_NIVEL.get(nivel, "⚪") if nivel != "—" else "⚪", conf, nivel))
    fontes = enriquecido.get("fontes_concordam") or []
    if fontes:
        linhas.append("**🔗 Fontes que concordam:** %s" % "; ".join(fontes))
    linhas.append("")

    orig = enriquecido.get("origem") or {}
    dest = enriquecido.get("destino") or {}
    linhas.append("**📍 Origem:** %s" % _mun_rotulo(orig.get("municipio")))
    linhas.append(formatar_confianca(orig.get("confianca")))
    if orig.get("estacao_ana"):
        linhas.append(_estacao_rotulo(orig["estacao_ana"], "origem"))
    if orig.get("rodovia_ref"):
        linhas.append(_rodovia_rotulo(orig["rodovia_ref"]))
    if orig.get("ferrovia_ref"):
        linhas.append(_ferrovia_rotulo(orig["ferrovia_ref"]))
    linhas.append("**📍 Destino:** %s" % _mun_rotulo(dest.get("municipio")))
    linhas.append(formatar_confianca(dest.get("confianca")))
    if dest.get("estacao_ana"):
        linhas.append(_estacao_rotulo(dest["estacao_ana"], "destino"))
    if dest.get("rodovia_ref"):
        linhas.append(_rodovia_rotulo(dest["rodovia_ref"]))
    if dest.get("ferrovia_ref"):
        linhas.append(_ferrovia_rotulo(dest["ferrovia_ref"]))
    linhas.append("")

    rios = enriquecido.get("rios_detectados") or []
    if rios:
        linhas.append("**🌊 Rios detectados:**")
        for r in rios:
            nav = r.get("navegavel")
            linhas.append("- `%s` a %s km (%s)%s" % (
                r.get("nome"), r.get("distancia_km"), r.get("referencia"),
                (" — nav.: %s" % nav) if nav else ""))
        linhas.append("")

    balsas = enriquecido.get("balsas_confirmadas") or []
    if balsas:
        linhas.append("**🛶 Balsas confirmadas:**")
        for b in balsas:
            linhas.append("- `%s` a %s km (%s)" % (
                b.get("nome"), b.get("distancia_km"), b.get("referencia")))
        linhas.append("")

    pontes = enriquecido.get("pontes_encontradas") or []
    if pontes:
        linhas.append("**🌉 Pontes encontradas:**")
        for p in pontes[:8]:
            nome = p.get("nome")
            do_ = " — %s" % p.get("atributo") if p.get("atributo") else ""
            linhas.append("- `%s` a %s km (%s)%s" % (
                nome, p.get("distancia_km"), p.get("referencia"), do_))
        linhas.append("")

    infra = enriquecido.get("infraestrutura_aquaviaria") or {}
    if infra:
        linhas.append("**⚓ Infraestrutura aquaviária:**")
        rotulos = {
            "atracadouros_terminal": "Atracadouros/terminais",
            "complexos_portuarios": "Complexos portuários",
            "eclusas": "Eclusas",
        }
        for camada, itens in infra.items():
            if not itens:
                continue
            resumo = "; ".join(
                "`%s` a %s km (%s)" % (i.get("nome"), i.get("distancia_km"), i.get("referencia"))
                for i in itens[:4])
            linha = "- **%s:** %s" % (rotulos.get(camada, camada), resumo)
            if len(itens) > 4:
                linha += " (+%d)" % (len(itens) - 4)
            linhas.append(linha)
        linhas.append("")

    motivo = enriquecido.get("motivo_decisao")
    if motivo:
        linhas.append("**📜 Motivo da decisão:**")
        linhas.append("> %s" % motivo)
        linhas.append("")

    fonte = enriquecido.get("fonte")
    if fonte:
        linhas.append("_Fonte: %s_ (raio %s km)" % (fonte, enriquecido.get("raio_km", "—")))
    return "\n".join(linhas)


def formatar_enriquecimento_html(enriquecido: dict) -> str:
    """Versão HTML (inline-safe) do painel — para relatórios/exportação."""
    parts = []
    _add = parts.append
    _add("<div style='font-family:system-ui;font-size:14px;line-height:1.5'>")
    _add("<h4>🧠 XAI — auditoria de trecho (IBGE local)</h4>")

    conf = enriquecido.get("confianca_geral") or 0
    _add("<p><b>Confiança geral:</b> <span style='font-size:16px'>%d/100</span></p>" % conf)
    fontes = enriquecido.get("fontes_concordam") or []
    if fontes:
        _add("<p><b>Fontes que concordam:</b> %s</p>" % "; ".join(fontes))

    orig = (enriquecido.get("origem") or {}).get("municipio")
    dest = (enriquecido.get("destino") or {}).get("municipio")
    _add("<p><b>Origem:</b> %s &nbsp;|&nbsp; <b>Destino:</b> %s</p>" % (
        _mun_rotulo(orig), _mun_rotulo(dest)))
    _eo = (enriquecido.get("origem") or {}).get("estacao_ana")
    _ed = (enriquecido.get("destino") or {}).get("estacao_ana")
    if _eo or _ed:
        def _e_html(_e):
            return ("`%s` %s (%s) a %s km" % (_e.get("codigo"), _e.get("nome"), _e.get("rio") or "rio n/d",
                                              _e.get("distancia_km"))) if _e else "—"
        _add("<p><b>Estação ANA (origem):</b> %s &nbsp;|&nbsp; <b>(destino):</b> %s</p>" % (
            _e_html(_eo), _e_html(_ed)))
    _ro = (enriquecido.get("origem") or {}).get("rodovia_ref")
    _rd = (enriquecido.get("destino") or {}).get("rodovia_ref")
    if _ro or _rd:
        def _r_html(_r):
            return ("%s (%s) a %s km" % (_r.get("via"), _r.get("jurisdicao"), _r.get("distancia_km"))) if _r else "—"
        _add("<p><b>Rodovia (origem):</b> %s &nbsp;|&nbsp; <b>(destino):</b> %s</p>" % (
            _r_html(_ro), _r_html(_rd)))

    rios = enriquecido.get("rios_detectados") or []
    if rios:
        _add("<p><b>Rios:</b> %s</p>" % "; ".join(
            "`%s` %skm (%s)" % (r.get("nome"), r.get("distancia_km"), r.get("referencia"))
            for r in rios[:5]))

    balsas = enriquecido.get("balsas_confirmadas") or []
    if balsas:
        _add("<p><b>Balsas:</b> %s</p>" % "; ".join(
            "`%s` %skm (%s)" % (b.get("nome"), b.get("distancia_km"), b.get("referencia"))
            for b in balsas[:5]))

    motivo = enriquecido.get("motivo_decisao")
    if motivo:
        _add("<p style='border-left:3px solid #aaa;padding-left:8px'>%s</p>" % motivo)
    _add("</div>")
    return "".join(parts)