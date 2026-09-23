"""
Enrichment Engine - enriquecimento de pontos/rotas com inteligência geoespacial local.

Produz os campos previstos no plano (Task 6) de forma ADITIVA e auditável, sem
rede, usando as camadas derivadas IBGE (bases_locais) e o validador cruzado:

    enriquecer_ponto(lat, lon, ...)  -> perfil + confiança + balsas/pontes próximas
    enriquecer_rota(orig, dest, ...) -> rios_detectados, pontes_encontradas,
        balsas_confirmadas, infraestrutura_aquaviaria, confianca_geral,
        fontes_concordam, motivo_decisao
"""

from __future__ import annotations

from . import bases_locais as _bl
from .validators import CoordinateValidator, _nome, _NIVEL_CONFIANCA

try:
    from . import ana_hidroweb as _ana
except Exception:  # fail-open: enriquecimento segue sem a estação ANA
    _ana = None

try:
    from . import rodovias_local as _rodo
except Exception:  # fail-open: enriquecimento segue sem a rodovia de referência
    _rodo = None

try:
    from . import ferrovias_local as _ferro
except Exception:  # fail-open: enriquecimento segue sem a ferrovia de referência
    _ferro = None


def _rodovia_ref(lat, lon):
    """Rodovia de referência do ponto (índice local, sem rede). None se indisponível."""
    if _rodo is None:
        return None
    try:
        return _rodo.rodovia_mais_proxima(lat, lon)
    except Exception:
        return None


def _ferrovia_ref(lat, lon):
    """Ferrovia de referência do ponto (índice local, sem rede). None se indisponível/sem ferrovia perto."""
    if _ferro is None:
        return None
    try:
        return _ferro.ferrovia_mais_proxima(lat, lon)
    except Exception:
        return None


def _estacao_ana(lat, lon, rio_nome=None):
    """Estação ANA fluviométrica de referência (rede nacional LOCAL, sem rede) — casa pelo MESMO RIO quando
    o rio do ponto é conhecido, para a referência mais exata. None se indisponível."""
    if _ana is None:
        return None
    try:
        return _ana.estacao_de_referencia(lat, lon, rio_nome=rio_nome)
    except Exception:
        return None


def _rio_do_perfil(perfil):
    try:
        _r = (perfil or {}).get("rio_mais_proximo") or {}
        return _r.get("nome") if isinstance(_r, dict) else None
    except Exception:
        return None

_CAMPOS_NULOS_SE_AUSENTE = ("bacia_hidrografica", "alternativa_sem_balsa")


def enriquecer_ponto(lat: float, lon: float, raio_km: float = 30.0,
                     limite: int = 5) -> dict:
    """Enriquece um ponto: município, drenagem nomeada, pontes, balsas e confiança."""
    v = CoordinateValidator(raio_km=raio_km, limite=limite)
    perfil = v.perfil(float(lat), float(lon), raio_km=raio_km)
    confianca = v.confianca(perfil)

    balsas = v.mais_proximas("travessias", float(lat), float(lon),
                             raio_km=raio_km, filtros={"tipotraves": "Balsa"})
    balsas_confirmadas = [
        {
            "nome": _nome(b.get("nome")) or "<sem nome>",
            "distancia_km": round(float(b["distancia_km"]), 2),
            "tipoembarc": _nome(b.get("tipoembarc")) or "Desconhecido",
        }
        for b in balsas
    ]

    return {
        "coordenadas": {"lat": float(lat), "lon": float(lon)},
        "municipio": perfil.get("municipio") or None,
        "rio_mais_proximo": perfil.get("rio_mais_proximo"),
        "pontes_encontradas": perfil.get("feicoes", {}).get("pontes", []),
        "balsas_confirmadas": balsas_confirmadas,
        "estacao_ana": _estacao_ana(lat, lon, _rio_do_perfil(perfil)),
        "rodovia_ref": _rodovia_ref(lat, lon),
        "ferrovia_ref": _ferrovia_ref(lat, lon),
        "confianca": confianca,
        "fonte": "IBGE BC250 v2025 + BC100 (camadas derivadas locais) + estações ANA/SNIRH",
    }


def enriquecer_rota(origem: tuple, destino: tuple, raio_km: float = 30.0,
                    limite: int = 5) -> dict:
    """Enriquece um par origem/destino com os campos de auditoria do plano.

    Campos sempre presentes (aditivos; podem ser None/vazios quando a base local
    não cobre o tema): rios_detectados, bacia_hidrografica, pontes_encontradas,
    infraestrutura_aquaviaria, balsas_confirmadas, alternativa_sem_balsa,
    confianca_geral, fontes_concordam, motivo_decisao.
    """
    v = CoordinateValidator(raio_km=raio_km, limite=limite)
    o = v.perfil(float(origem[0]), float(origem[1]), raio_km=raio_km)
    d = v.perfil(float(destino[0]), float(destino[1]), raio_km=raio_km)
    co = v.confianca(o)
    cd = v.confianca(d)

    rios = []
    for per, rotulo in ((o, "origem"), (d, "destino")):
        r = per.get("rio_mais_proximo")
        if r:
            rios.append({
                "nome": r["nome"],
                "distancia_km": r["distancia_km"],
                "navegavel": r["navegavel"],
                "regime": r["regime"],
                "referencia": rotulo,
            })
    rios.sort(key=lambda x: x["distancia_km"])

    balsas = []
    for per, rotulo in ((o, "origem"), (d, "destino")):
        for b in v.mais_proximas("travessias", per["parametros"]["lat"],
                                 per["parametros"]["lon"], raio_km=raio_km,
                                 filtros={"tipotraves": "Balsa"}):
            balsas.append({
                "nome": _nome(b.get("nome")) or "<sem nome>",
                "distancia_km": round(float(b["distancia_km"]), 2),
                "referencia": rotulo,
            })
    balsas.sort(key=lambda x: x["distancia_km"])

    infra_aqua = {}
    for camada in ("atracadouros_terminal", "complexos_portuarios", "eclusas"):
        itens = []
        for per in (o, d):
            for it in per.get("feicoes", {}).get(camada, []):
                itens.append({**it, "referencia": "origem" if per is o else "destino"})
        if itens:
            infra_aqua[camada] = sorted(itens, key=lambda x: x["distancia_km"])

    pontes = []
    for per, rotulo in ((o, "origem"), (d, "destino")):
        for p in per.get("feicoes", {}).get("pontes", []):
            pontes.append({**p, "referencia": rotulo})
    pontes.sort(key=lambda x: x["distancia_km"])

    fontes = sorted(set(co["fontes_concordam"]) | set(cd["fontes_concordam"]))
    if o.get("municipio") or d.get("municipio"):
        conf_geral = min(co["pontuacao"], cd["pontuacao"])
    else:
        conf_geral = int((co["pontuacao"] + cd["pontuacao"]) / 2)
    nivel = "baixa"
    for nome_nivel, lim in _NIVEL_CONFIANCA:
        if conf_geral >= lim:
            nivel = nome_nivel
            break

    motivo_parts = []
    if o.get("municipio") and d.get("municipio"):
        motivo_parts.append(
            "Origem em %s e destino em %s (IBGE)." % (
                o["municipio"].get("nome"), d["municipio"].get("nome")))
    if rios:
        motivo_parts.append(
            "Drenagem mais próxima: %s a %.1f km (%s)." % (
                rios[0]["nome"], rios[0]["distancia_km"],
                ("navegável" if (rios[0]["navegavel"] or "").lower() in ("sim", "parcial") else "não navegável")))
    if balsas:
        motivo_parts.append(
            "Balsa(s) confirmada(s) no entorno: %s a %.1f km." % (
                balsas[0]["nome"], balsas[0]["distancia_km"]))
    if not fontes:
        motivo_parts.append("Nenhuma base local confirma o ponto (possivelmente fora do Brasil).")

    return {
        "origem": {
            "municipio": o.get("municipio") or None,
            "confianca": co,
            "estacao_ana": _estacao_ana(origem[0], origem[1], _rio_do_perfil(o)),
            "rodovia_ref": _rodovia_ref(origem[0], origem[1]),
            "ferrovia_ref": _ferrovia_ref(origem[0], origem[1]),
        },
        "destino": {
            "municipio": d.get("municipio") or None,
            "confianca": cd,
            "estacao_ana": _estacao_ana(destino[0], destino[1], _rio_do_perfil(d)),
            "rodovia_ref": _rodovia_ref(destino[0], destino[1]),
            "ferrovia_ref": _ferrovia_ref(destino[0], destino[1]),
        },
        "rios_detectados": rios,
        "bacia_hidrografica": None,
        "pontes_encontradas": pontes,
        "infraestrutura_aquaviaria": infra_aqua,
        "balsas_confirmadas": balsas,
        "alternativa_sem_balsa": None,
        "confianca_geral": conf_geral,
        "confianca_nivel": nivel,
        "fontes_concordam": fontes,
        "motivo_decisao": " ".join(motivo_parts),
        "fonte": "IBGE BC250 v2025 + BC100 (camadas derivadas locais)",
        "raio_km": float(raio_km),
    }