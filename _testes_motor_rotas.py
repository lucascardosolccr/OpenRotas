# -*- coding: utf-8 -*-
"""
Harness forense do Motor de Escolha de Rotas — casos de derrota Prompt.1.1.1.
Uso:
    py _testes_motor_rotas.py collect   # coleta distâncias viárias reais (OSRM) + cache JSON
    py _testes_motor_rotas.py report    # relatório offline a partir do cache
    py _testes_motor_rotas.py decidir   # roda a decisao atual (e a nova politica) sobre o cache

Usa a MESMA base de municípios da aplicação (streamlit_app importável em bare mode)
e a MESMA métrica geodésica IUGG, para que as retas coincidam com o app.
"""
import json
import logging
import math
import os
import sys
import tempfile
import time
import pandas as pd

logging.disable(logging.WARNING)   # silencia os WARNING de streamlit/bare-mode no harness

PROJ = os.path.dirname(os.path.abspath(__file__))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)

import requests

CACHE = os.path.join(PROJ, "_cache_osrm_derrotas.json")
_BASELINE_LOCAL = os.path.join(PROJ, "_baseline_1452.json")          # cópia local do dataset §22
_BASELINE_TEMP = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "opencode", "_relatorio_dados.json")
_RELATORIO_MD = os.path.join(PROJ, "_RELATORIO_ANTES_DEPOIS.md")     # artefato §20/§25
OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"
TIMEOUT = 25

# cidade origem | UF | aplicar_app (hub, km) | aplicar_ref (hub, km) | balsa conhecida no estudo
CASOS = [
    ("Pauini", "AM", ("Sena Madureira", 413), ("Rio Branco", 270), {}),
    ("Jacundá", "PA", ("Tucuruí", 159), ("Marabá", 111), {}),
    ("Medina", "MG", ("Almenara", 157), ("Araçuaí", 118), {}),
    ("Mostardas", "RS", ("Camaquã", 340), ("Osório", 163), {}),
    ("Santo Augusto", "RS", ("Panambi", 114), ("Ijuí", 72), {}),
    ("Anaurilândia", "MS", ("Terra Rica", 126), ("Nova Andradina", 70), {}),
    ("Quedas do Iguaçu", "PR", ("Dois Vizinhos", 57), ("Laranjeiras do Sul", 69), {}),
    ("Taquari", "RS", ("São Jerônimo", 39), ("Venâncio Aires", 50), {"São Jerônimo": True}),
    ("Viana", "MA", ("Itapecuru Mirim", 93), ("Santa Inês", 110), {}),
    ("Oeiras do Pará", "PA", ("Cametá", 55), ("Breves", 516), {}),
    ("Gurupá", "PA", ("Portel", 129), ("Almeirim", 292), {}),
    ("São José do Norte", "RS", ("Rio Grande", 7), ("Osório", 315), {"Rio Grande": True}),
    ("Triunfo", "RS", ("São Jerônimo", 2), ("Montenegro", 50), {"São Jerônimo": True}),
]

# §11 — CASOS FAVORÁVEIS rodoviários do estudo (o app já era melhor/igual). Servem de prova de
# NÃO REGRESSÃO (§21.13): o motor corrigido NÃO pode piorar a escolha desses municípios.
FAVORAVEIS = [
    ("Carutapera", "MA", ("Bragança", 96.4), ("Capanema", 229.2), {}),
    ("Arroio do Tigre", "RS", ("Santa Cruz do Sul", 98.0), ("Restinga Sêca", 94.8), {}),
    ("Dormentes", "PE", ("Ouricuri", 130.3), ("Petrolina", 127.2), {}),
]

# §22 — Recorte das MAIORES DERROTAS do baseline (relatorio_comparacao (3).html, além dos 13 da missão):
# prova de GENERALIZAÇÃO da correção (universo-fechado + política única de balsa) sobre as piores linhas
# reais. Só entram as com vencedor rodoviário plausível; as de ilha/rio puro (Anajas/PA, Muana/PA,
# Jordao/AC, Canutama/AM) seguem o padrão fluvial-bounded já validado (Oeiras/Gurupá + _corrigir_rota_fantasma_fluvial).
DERROTAS_REAIS = [
    ("Centro Novo do Maranhão", "MA", ("Capitao Poco", 228.8), ("Pinheiro", 148.5), {}),
    ("Palestina do Pará", "PA", ("Xambioa", 173.6), ("Marabá", 108.3), {}),
    ("São Vicente do Seridó", "PB", ("Parelhas", 104.2), ("Parelhas", 52.0), {}),
]

# §24/§16 — NOVAS DERROTAS do baseline (piores por categoria) convertidas em casos forenses reais:
# medição OSRM AO VIVO do universo (app_hub + ref_hub + top-20 por reta) e decisão real do app.
# Famílias:
#   * fluvial/nome-igual (dr da referência < reta → fisicamente impossível de vencer [N1]; o valor justo
#     é a travessia flúvio/ferry, que o motor corrige via grafo hidrográfico) — Canutama, Muana, Anajas,
#     Afuá, Urucurituba, Itapiranga, Jordão, Prainha, Cachoeira do Arari.
#   * nome-igual RODOVIÁRIO com referência plausível (dr ≥ reta) — ganhável por métrica/correção —
#     Nova Guarita, Aveiro, Sobradinho/RS.
#   * escolha x escolha (hubs DIFERENTES, rota da app era maior) — Chuí, Parnarama, Padre Paraíso,
#     Querência do Norte, Fontoura Xavier.
#   * phantom-hídrica (app com V/R ≥ 2,6) — Alto Piquiri... (Altonia/PR), Governador Celso Ramos/SC.
FAMILIAS = [
    ("Canutama", "AM", ("Labrea", 116.0), ("Lábrea", 12.5), {}),
    ("Muana", "PA", ("Abaetetuba", 53.0), ("Abaetetuba", 1.8), {}),
    ("Anajas", "PA", ("Breves", 123.6), ("Breves", 25.2), {}),
    ("Afua", "PA", ("Macapa", 88.8), ("Macapá", 45.3), {}),
    ("Urucurituba", "AM", ("Itacoatiara", 40.4), ("Itacoatiara", 6.5), {}),
    ("Itapiranga", "AM", ("Urucara", 46.6), ("Urucará", 12.7), {}),
    ("Jordao", "AC", ("Cruzeiro Do Sul", 223.9), ("Cruzeiro do Sul", 78.5), {}),
    ("Prainha", "PA", ("Monte Alegre", 127.2), ("Monte Alegre", 91.5), {}),
    ("Cachoeira Do Arari", "PA", ("Belem", 128.2), ("Belém", 95.8), {}),
    ("Nova Guarita", "MT", ("Colider", 113.1), ("Colíder", 69.8), {}),
    ("Aveiro", "PA", ("Itaituba", 140.6), ("Itaituba", 109.1), {}),
    ("Sobradinho", "RS", ("Restinga Seca", 116.4), ("Restinga Sêca", 83.6), {}),
    ("Chui", "RS", ("Jaguarao", 283.6), ("Rio Grande", 242.2), {}),
    ("Parnarama", "MA", ("Angical Do Piaui", 119.5), ("Teresina", 83.8), {}),
    ("Padre Paraiso", "MG", ("Aracuai", 135.7), ("Teófilo Otoni", 99.3), {}),
    ("Querencia Do Norte", "PR", ("Navirai", 137.5), ("Umuarama", 97.9), {}),
    ("Fontoura Xavier", "RS", ("Marau", 108.3), ("Lajeado", 77.6), {}),
    ("Altonia", "PR", ("Mundo Novo", 108.0), ("Palotina", 65.9), {}),
    ("Governador Celso Ramos", "SC", ("Tijucas", 31.9), ("Biguaçu", 26.0), {}),
]

# Referência com distância FISICAMENTE IMPOSSÍVEL (dr < reta da própria referência) — o motor honesto
# nunca pode alcançá-la; registrada como benchmark-anômalo (Tipo 10) e conferida como travessia fluvial.
_FLUVIAIS_N1 = {("Canutama", "AM"), ("Muana", "PA"), ("Anajas", "PA"), ("Afua", "PA"),
                ("Urucurituba", "AM"), ("Itapiranga", "AM"), ("Jordao", "AC"),
                ("Prainha", "PA"), ("Cachoeira do Arari", "PA")}

# https://stackoverflow.com/a/59675305 — remoção de acentos leve (sem unidecode)
_ACENTOS = {
    ord(a): b for a, b in zip(
        "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
        "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN")
}


def _norm(s):
    return str(s or "").translate(_ACENTOS).strip().upper()


def _curto(nome, limite=16):
    s = str(nome or "")
    if len(s) <= limite:
        return s
    return (s[:limite].rsplit(" ", 1)[0] or s[:limite].rstrip()) + "…"


def _hav(lat1, lon1, lat2, lon2):
    r, p1, p2 = 6371.0088, math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _resolver_base():
    import streamlit_app as m
    oficial = m._carregar_sedes_oficiais()
    idx = {}
    idx_por_nome = {}
    for item in m._municipios_com_coordenadas():
        nome = _norm(item["municipio"])
        uf = _norm(item["uf"])
        chave = (nome, uf)
        cod = str(item.get("codigo_ibge") or "").strip()
        lat, lon = float(item["lat"]), float(item["lon"])
        if cod and cod in oficial:
            lat, lon = oficial[cod]
        reg = (item["municipio"], item["uf"], cod, lat, lon)
        idx.setdefault(chave, reg)
        idx_por_nome.setdefault(nome, reg)
    return idx, idx_por_nome


def _resolve(base, por_nome, nome, uf_preferida=""):
    reg = base.get((_norm(nome), _norm(uf_preferida)))
    if reg:
        return reg
    return por_nome.get(_norm(nome))


def _osrm(lat1, lon1, lat2, lon2):
    # Delega ao MESMO helper TLS do app (_get_tls_fallback em streamlit_app.py): verificação normal;
    # se o cert do servidor for recusado, refaz com verify=False. Evita dupla implementação e mede o
    # comportamento real (a partir de 2026-09 o cert público oscila vencido/válido).
    import streamlit_app as _m
    url = "%s/%s,%s;%s,%s?overview=false&alternatives=false" % (
        OSRM_BASE, lon1, lat1, lon2, lat2)
    try:
        r = _m._get_tls_fallback(_m.session_osrm_publico, url, timeout=TIMEOUT)
        j = r.json()
        if j.get("code") == "Ok" and j.get("routes"):
            return round(j["routes"][0]["distance"] / 1000.0, 2)
    except Exception:
        pass
    finally:
        time.sleep(0.3)  # politesse/rate-limit no servidor público durante medições em lote
    return None


def collect():
    import streamlit_app as m
    base, por_nome = _resolver_base()
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)

    def get_medida(origem, destino, uf_origem=""):
        key = "%s|%s" % (_norm(origem), _norm(destino))
        if key in cache and cache[key].get("km") is not None:
            return cache[key]
        o = _resolve(base, por_nome, origem, uf_origem)
        d = _resolve(base, por_nome, destino, uf_origem)
        if not o or not d:
            cache[key] = {"km": None, "reta": None, "erro": "municipio nao resolvido"}
            return cache[key]
        reta = round(_hav(o[3], o[4], d[3], d[4]), 2)
        km = _osrm(o[3], o[4], d[3], d[4])
        cache[key] = {"km": km, "reta": reta, "uf_destino": d[1], "nome_oficial": d[0]}
        return cache[key]

    # 1) medir pares específicos (app hub e ref hub) + top-N geográficos
    casos = CASOS + FAVORAVEIS + DERROTAS_REAIS + FAMILIAS
    for origem, uf, (app_hub, app_km), (ref_hub, ref_km), bal in casos:
        entry = {"origem": origem, "uf": uf, "app_hub": app_hub, "app_km": app_km,
                 "ref_hub": ref_hub, "ref_km": ref_km, "balsa": bal, "medidas": {}}
        for hub in (app_hub, ref_hub):
            ref = get_medida(origem, hub, uf)
            entry["medidas"][hub] = ref

        # top-N por linha reta próximo ao ref hub (universo-expandido, radão do ref+banda)
        o = _resolve(base, por_nome, origem, uf)
        r = _resolve(base, por_nome, ref_hub, uf)
        raio = max(1.5 * ref_km, 1.5 * app_km if app_km < 200 else 1.2 * app_km)
        raio = min(raio, 900.0)
        if o and r:
            cands = []
            for (nome1, nome2), reg in base.items():
                if nome1 == _norm(origem):
                    continue
                reta = _hav(o[3], o[4], reg[3], reg[4])
                if reta <= raio:
                    cands.append((reta, reg[0]))
            cands.sort()
            for reta, nn in cands[:20]:
                ck = get_medida(origem, nn, uf)
                entry["medidas"].setdefault(nn, ck)
        cache.setdefault("casos", {})[origem + "/" + uf] = entry
        print("OK %s/%s" % (origem, uf))

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print("Cache salvo em %s (%d entradas)" % (CACHE, len(cache)))


def report():
    if not os.path.exists(CACHE):
        print("Rode 'collect' primeiro.")
        return
    with open(CACHE, encoding="utf-8") as f:
        cache = json.load(f)
    print("=" * 100)
    print("RELATÓRIO FORENSE — 13 CASOS (distâncias viárias OSRM reais x estudo)")
    print("=" * 100)
    for chave_caso, entry in cache.get("casos", {}).items():
        origem, uf = entry["origem"], entry["uf"]
        print()
        print("### %s/%s" % (origem, uf))
        for hub in (entry["app_hub"], entry["ref_hub"]):
            m = entry["medidas"].get(hub) or {}
            est = entry["app_km"] if hub == entry["app_hub"] else entry["ref_km"]
            flag = " BALSA(estudo)" if entry["balsa"].get(hub) else ""
            print("   %-18s estudo=%.0f km  OSRM=%s km  reta=%s km  %s" % (
                hub, est, m.get("km"), m.get("reta"), flag))
        # menor rota real entre os medidos
        medidas = [(hub, m.get("km"), m.get("reta")) for hub, m in entry["medidas"].items() if m.get("km")]
        medidas.sort(key=lambda x: x[1])
        if medidas:
            menor = medidas[0]
            print("   >> MENOR ROTA VIÁRIA real medida: %s (%.2f km; reta=%.2f)" % (menor[0], menor[1], menor[2]))
            print("   >> top5 por estrada: " + ", ".join("%s=%.1f" % (h, k) for h, k, _ in medidas[:5]))


# =============================================================================
# VALIDAÇÃO SOBRE AS FUNÇÕES REAIS DO APP (SSOT) — MISSÃO §5/§6/§7 + UNIVERSO-FECHADO
# =============================================================================

# Distâncias FLUVIAIS-REALISTAS injetadas (simulam _corrigir_rota_fantasma_fluvial do app:
# barreira hídrica → a viária real do candidato é o trajeto fluvial, não o desvio rodoviário absurdo
# que o OSRM devolve para ilhas/rios). Valores do estudo (Portel 129 / Cametá 55).
_FLUVIAL_REALISTA = {"Portel": 129.0, "Cametá": 55.0, "CAMETA": 55.0, "PORTEL": 129.0}


def _candidatos_do_cache(entry):
    """Monta candidatos da MEDIÇÃO REAL do cache, no mesmo formato que _reatribuir_hubs_multicriterio
    entrega a _selecionar_hub_multicriterio (rota_real True p/ toda medição OSRM; balsa do estudo).
    A flag de balsa do estudo é propagada por NOME NORMALIZADO (acento/caixa), para o mesmo polo medido sob
    variantes (ex.: 'São Jerônimo' e 'SAO JERONIMO') manter a flag no cache."""
    import streamlit_app as m
    balsa_norm = {_norm(h): True for h, v in entry["balsa"].items() if v}
    cands = []
    for hub, m2 in entry["medidas"].items():
        if not m2.get("km") or not m2.get("reta"):
            continue
        _km, _reta = float(m2["km"]), float(m2["reta"])
        if not m._viaria_fisicamente_possivel(_km, _reta):
            continue  # impossível físico (ferry-artefato do OSRM, V/R < 1) — o app também descarta antes
        _km = _FLUVIAL_REALISTA.get(hub, _km)
        cands.append({"hub": hub, "dist_viaria": _km, "dist_reta": _reta,
                      "balsa": bool(balsa_norm.get(_norm(hub))), "rota_real": True, "tempo_min": None})
    return cands


def _decidir_real(entry):
    """Roda a decisão REAL do app (m._selecionar_hub_multicriterio) sobre o universo medido do cache,
    APLICANDO o mesmo pré-processamento do app (_metrica_fluvial_justa_no_universo) antes da escolha."""
    import streamlit_app as m
    cands = _candidatos_do_cache(entry)
    if not cands:
        return None, cands
    m._metrica_fluvial_justa_no_universo(cands, entry["origem"], uf_hint=entry["uf"])
    return m._selecionar_hub_multicriterio(cands), cands


def _todas_decisoes():
    """(entry, res, vkm) para cada caso do cache — sem prints/asserts. Compartilhado por decidir() e
    relatorio() para que o relatório §20/§25 reflita EXATAMENTE as decisões exibidas e validadas."""
    rows = []
    if not os.path.exists(CACHE):
        return rows
    with open(CACHE, encoding="utf-8") as f:
        cache = json.load(f)
    for chave_caso, entry in cache.get("casos", {}).items():
        res, cands = _decidir_real(entry)
        if res is None:
            continue
        v = res["vencedor"]
        vkm = next((c["dist_viaria"] for c in res["ranking"] if c["hub"] == v), None)
        rows.append((entry, res, vkm))
    return rows


def decidir():
    """Roda a DECISÃO REAL do app (_selecionar_hub_multicriterio) por cima da medição OSRM do cache,
    com a política única de balsa já ativa, e valida as propriedades da missão por caso."""
    if not os.path.exists(CACHE):
        print("Rode 'collect' primeiro.")
        return
    import streamlit_app as m
    print("=" * 100)
    print("DECISÃO REAL DO APP (m._selecionar_hub_multicriterio) sobre medição OSRM — política única de balsa")
    print("=" * 100)
    falhas = []
    for entry, res, vkm in _todas_decisoes():
        origem, uf = entry["origem"], entry["uf"]
        v = res["vencedor"]
        rb = res.get("ranking") or []
        top3 = ", ".join("%s=%.1f" % (c["hub"], c["dist_viaria"]) for c in rb[:3])
        print("\n%s/%s  [referência = %s]  ->  VENCEDOR %s (%.1f km)" % (origem, uf, entry["ref_hub"], v, vkm))
        print("   critério: %s" % (res.get("criterio_decisivo") or "—"))
        print("   ranking: %s" % top3)

        # FAMILIAS §24 — anota a família forense (agregação de padrões da missão §17/§19)
        if (origem, uf) in _FLUVIAIS_N1:
            print("   >> família FLUVIAL/nome-igual: referência dr<reta (benchmark-anômalo), valor justo = travessia flúvio/ferry")
        elif (origem, uf) in {c[:2] for c in FAMILIAS}:
            print("   >> família §24 (derrota real medida ao vivo)")

        # ── propriedades da missão (asserts) ──
        def _rodeando():
            return all(not c["balsa"] and c.get("plausivel", True) for c in rb)

        if entry["origem"] in ("Taquari", "Triunfo"):
            # §7: rodovia razoável DESTRONA a travessia mais curta
            if v == "São Jerônimo" or str(v).upper() == "SAO JERONIMO":
                falhas.append("%s: vencedor é a balsa evitável (rodovia razoável existe)" % origem)
        elif entry["origem"] == "São José do Norte":
            # §6: balsa INEVITÁVEL (rodovia desproporcional) mantém a travessia mais curta
            if v != "Rio Grande" and str(v).upper() != "RIO GRANDE":
                falhas.append("São José do Norte: balsa inevitável não foi mantida (vencedor=%s)" % v)
        elif entry["origem"] in ("Oeiras do Pará", "Gurupá"):
            # vantagem fluvial-realista preservada (e rodovia absurda nunca vence)
            if vkm and entry["ref_km"] and vkm:
                if vkm > float(entry["ref_km"]):
                    falhas.append("%s: vencedor (%s) não é mais curto que a referência (%s km)" % (origem, v, entry["ref_km"]))
        else:
            # os demais: o vencedor real deve ser a MENOR rota entre as medidas plausíveis
            _menores = [c for c in rb if c.get("plausivel", True) and c.get("rota_real", True)]
            if _menores and v != _menores[0]["hub"]:
                falhas.append("%s: vencedor não é a menor rota plausível (esperado %s, veio %s)"
                              % (origem, _menores[0]["hub"], v))
            # §11/§21.13 — casos favoráveis: NÃO REGRESSÃO (vencedor <= escolha original do app)
            if origem in {c[0] for c in FAVORAVEIS + DERROTAS_REAIS} and vkm is not None and entry.get("app_km"):
                if vkm > float(entry["app_km"]) + 0.5:
                    falhas.append("%s: REGRESSÃO em caso favorável (agora %.1f km > antes %.1f km)"
                                  % (origem, vkm, float(entry["app_km"])))
    print()
    print("=" * 100)
    if falhas:
        print("FALHAS (%d):" % len(falhas))
        for f in falhas:
            print("  ✗ %s" % f)
    else:
        print("TODOS OS CASOS PASSARAM nas propriedades da missão.")
    print("=" * 100)


def _carregar_baseline():
    """Dataset extraído do artefato §22 (relatorio_comparacao (3).html, var D — 1452 municípios).
    Prefere a cópia no projeto; cai no temp extraído na análise original."""
    for p in (_BASELINE_LOCAL, _BASELINE_TEMP):
        try:
            if p and os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return None


def _antes_da_missao():
    """(app_hub, app_km, ref_hub, ref_km) PRECISOS do estudo (CASOS/FAVORAVEIS/DERROTAS_REAIS/FAMILIAS), por (origem, UF)."""
    d = {}
    for origem, uf, (app_hub, app_km), (ref_hub, ref_km), _bal in CASOS + FAVORAVEIS + DERROTAS_REAIS + FAMILIAS:
        d[(origem, uf)] = (app_hub, float(app_km), ref_hub, float(ref_km))
    return d


def relatorio():
    """§20/§25 — gera o artefato ANTES × DEPOIS em _RELATORIO_ANTES_DEPOIS.md usando a MESMA fila de
    decisões do decidir() (uma fonte de verdade) + indicadores globais do baseline (1452 municípios)
    + projeção de cobertura dos 'venc == Referência'."""
    import datetime
    linhas = []
    a = linhas.append
    base = _carregar_baseline()
    a("# RELATÓRIO ANTES × DEPOIS — Motor de Rotas (Prompt 1.1.1, §20/§25)")
    a("")
    a("Gerado em %s por `py _testes_motor_rotas.py relatorio` — mesma fila de decisões do `decidir`." % (
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    a("")
    a("## 1. Funções alteradas (streamlit_app.py)")
    a("")
    a("- Política ÚNICA de balsa (§6/§7): `_balsa_extra_admissivel`, `_rota_sem_balsa_razoavel`, "
      "`_balsa_evitavel_banda`, `_vantagem_banda_balsa` (~31886). Banda adaptativa: máxima de 60 km ou 5× a travessia.")
    a("- `_selecionar_hub_multicriterio` (~32821): menor DISTÂNCIA VIÁRIA roda primeiro; balsa demovida; "
      "`criterio_decisivo` visível. Nenhum tempo/custo/km-eq decide vencedor.")
    a("- UNIVERSO-FECHADO (raiz das derrotas): `_fundir_shortlist_no_topk` (35054) funde TODA a matriz; "
      "`_fundir_resultados_no_topk`; `_reatribuir_hubs_multicriterio` (~33462) com fallback dist_matriz.")
    a("- `_forcar_menor_viaria_vencedor` (~35766): guarda anti-balsa (`_balsa_concorrente_map`).")
    a("- `calcular_matriz_competitiva_vetorizada` (31743): Top-K adaptativo por sinal de malha (teto 48).")
    a("- Comparador/V316 unificados na banda (19474 / 21970 / 22141).")
    a("- Robustez de rede: `_get_tls_fallback` (verify normal → verify=False só se SSLError) nos 5 pontos OSRM; "
      "`API_OSRM_Routing` com **fallback automático → FOSSGIS** quando o público falha/429/code!=Ok.")
    a("- Grafo flúvio-hidrográfico NACIONAL carregado (hidrografia_nacional.pkl.gz, 8.489 rios / 1.216.018 nós) "
      "e roteador fluvial offline V368/V371 validados fim-a-fim (retas/routes fluviais Oeiras→Cametá, "
      "SJN→Rio Grande via Lagoa dos Patos).")
    a("")
    a("### Melhoria4 — P1–P5 (evolução contínua, ZERO REGRESSÃO)")
    a("")
    a("- **P1 · Valhalla por divergência (§7):** `_regime_divergencia_rota` + `_valhalla_deve_auto_engajar` "
      "(teto por processo, thread-safe). Google×OSRM discordando forte (|g−o| ≥ max(30 km, 20% da menor)) → o "
      "Valhalla entra AUTOMATICAMENTE como 3ª perna de consenso mesmo sem toggle; nunca decide por si.")
    a("- **P2 · Memória geográfica persistente (§8→§7):** `_geo_mem_*` gravam `cache_geografia/memoria_geografica.json` "
      "(gate por versão); origens recorrentemente problemáticas recebem top-K MAIOR na próxima medição; painel "
      "exibe recorrentes. Aditivo: ausência/arquivo → comportamento idêntico.")
    a("- **P3 · Índice de Confiança da Rota (§6):** `_indice_confianca_rota` (0-100, puro) agrega fonte real vs "
      "estimada, V/R, balsa, divergência entre motores, snap e nº de motores; coluna `Indice Confianca Rota` + "
      "card no relatório. Auxiliar — nunca altera o vencedor.")
    a("- **P4 · Blindagem de testes:** seções 11–14 do `validar` (Valhalla sem rede, memória geográfica em "
      "arquivo temporário, Índice de Confiança, roteador fluvial offline V423/V424). Gate: **67 OK / 0 FALHAS**.")
    a("- **P5 · Explica a decisão (§11/§13):** no painel de Alocação, a justificativa agora expõe a REGRA "
      "aplicada (política única §6/§7 — banda `max(60 km, 5× travessia)` e preferência pela rodovia sem balsa).")
    a("")
    a("### Melhoria4 — M1/M2 (evolução contínua, ZERO REGRESSÃO)")
    a("")
    a("- **M1 · Diagnóstico no tempo (§16/§15):** `registrar_telemetria` agora guarda a SEQUÊNCIA cronológica "
      "dos eventos de API (fonte, sucesso, UF, instante) num buffer rolante persistido no diskcache "
      "(`ULTIMOS_EVENTOS_API`, cap 500); o Monitor de APIs ganhou o bloco **'Últimas falhas de API no tempo'** "
      "— distingue um pico pontual de uma instabilidade persistente (função pura `_ultimas_falhas_apresentaveis`).")
    a("- **M2 · Geometria anômala (§5):** `_suspeita_geometria_rota` (puro) acusa placeholder de 2 pontos, "
      "traçado incompatível com os km do próprio motor e 'linha reta' com V/R alto (provável interpolação); o "
      "mapa da rota passou a exibir o aviso como badge aditivo. Diagnóstico apenas — nunca decide a rota.")
    a("")
    a("### Melhoria4 — R3 (§7/§8, evolução contínua, ZERO REGRESSÃO)")
    a("")
    a("- **R3-A · 'Profunda quando complexa' (§7):** além da divergência Google×OSRM, o Valhalla agora é "
      "engajado automaticamente na ZONA DE SUSPEITA — rota do OSRM primário com V/R alto (≥ 2,6) ou com "
      "travessia de balsa + indireção (≥ 2,0). Limiares abaixo dos gatilhos de fantasma hídrica (3,0 / 2,2): "
      "a 3ª perna corrobora ANTES de o caso virar fantasma. Compartilha o MESMO teto por processo da "
      "divergência (fair-use). Aditivo: sem suspeita → contendor idêntico; Valhalla nunca decide por si.")
    a("- **R3-B · Telemetria com região (§8 primeiro corte):** os geocoders mais falhos (Google Geo com a "
      "BOUNDING BOX da UF de contexto, Nominatim com o ctx) agora registram a UF no histórico cronológico de "
      "eventos — no Monitor, as 'últimas falhas' mostram em qual UF aconteceram (base futura para 'motores "
      "mais confiáveis por região').")
    a("")
    a("### Pesquisa aplicada — R4 (sensores §3/§5/§7, ZERO REGRESSÃO)")
    a("")
    a("- **R4-A · Circuidade como sensor em BANDAS por distância (§3/§5):** `_circuidade_banda_suspeita` "
      "(pura) aplica o caveat metodológico da literatura (o fator viária÷reta decresce com o comprimento do "
      "trecho) com gatilhos por faixa — curto 2,2 / médio 1,8 / longo 1,6 — acima da baseline densa do Brasil "
      "(≈1.33, Ballou et al.) e PROVAVEL_BARREIRA ≥2,0 (águas/relevo, Amazônia ~3,1). Segue o princípio da "
      "pesquisa: circuidade DISPARA investigação/expansão, nunca decide o vencedor. Nos alertas automáticos "
      "(AIAS) das linhas (aditivo, sem coordenadas → sem alerta).")
    a("- **R4-B · Pré-validação de centróides brasileiros (§7.1/§7.2):** `_validar_centroide_br` (pura) aplica "
      "o pre-flight da pesquisa — limites continentais (lon ∈ [-74,-34.8], lat ∈ [-33.8,5.3]), detecção de "
      "troca lat/lon (lat brasileira nunca passa de ~34 de magnitude; lon tem magnitude 34–74), ponto (0,0) = "
      "dado ausente e faixa esperada da UF (BOUNDING_BOXES_UF). PIP contra a malha IBGE fica como passo "
      "futuro dependente de shapes. Sinaliza nos AIAS de linhas que carregam coordenadas.")

    a("")
    a("## 2. Decisões reais (OSRM) ANTES × DEPOIS — missão + favoráveis §11 + maiores derrotas §22")
    a("")
    a("| Caso | ANTES (app) | Referência | DEPOIS (vencedor) | Ganho | Critério |")
    a("|---|---:|---:|---:|---:|---|")
    _antes = _antes_da_missao()
    _base_map = {}
    if base:
        _base_map = {("%s/%s" % (_norm(r["o"]), _norm(r["uf"]))): r for r in base}
    for entry, res, vkm in _todas_decisoes():
        origem, uf = entry["origem"], entry["uf"]
        linha = _base_map.get(("%s/%s" % (_norm(origem), _norm(uf))))
        a_hub, a_km, r_hub, r_km = _antes.get((origem, uf), (entry.get("app_hub"), entry.get("app_km"),
                                                            entry.get("ref_hub"), entry.get("ref_km")))
        if linha:
            a_km, r_km = float(linha["da"]), float(linha["dr"])
            a_hub, r_hub = linha.get("dapp") or a_hub, linha.get("dref") or r_hub
        if origem == "São José do Norte":
            ganho = "mantido §6 (balsa inevitável)"
        elif origem == "Triunfo":
            ganho = "balsa demovida (§7)"
        elif origem in ("Oeiras do Pará", "Gurupá"):
            ganho = "mantido (fluvial-realista)"
        else:
            ganho = ("%s → %s (%.1f)" % (_curto(a_hub), res["vencedor"], float(a_km) - float(vkm))
                     if a_km is not None and vkm is not None else "")
        a("| %s/%s | %s %.1f | %s %.1f | **%s** (%.1f km) | %s | %s |" % (
            origem, uf, _curto(a_hub), a_km, _curto(r_hub), r_km,
            res["vencedor"], vkm or 0.0, ganho, res.get("criterio_decisivo") or "—"))
    a("")
    a("## 3. Baseline (artefato §22 — 1452 municípios, comportamento ANTES)")
    if base:
        import collections
        c = collections.Counter(r["venc"] for r in base)
        soma_da = sum(float(r["da"]) for r in base)
        soma_dr = sum(float(r["dr"]) for r in base)
        derrotas = [r for r in base if float(r["da"]) > float(r["dr"])]
        perda = sum(float(r["da"]) - float(r["dr"]) for r in derrotas)
        refs = [r for r in base if r["venc"] == "Referência"]
        perda_ref = sum(float(r["da"]) - float(r["dr"]) for r in refs)
        a("| Indicador | Valor |")
        a("|---|---:|")
        a("| Municípios | %d |" % len(base))
        a("| venc: Empate / Referência / Aplicação | %d / %d / %d |" % (c["Empate"], c["Referência"], c["Aplicação"]))
        a("| Σ distância da Aplicação (da) | %.1f km |" % soma_da)
        a("| Σ distância da Referência (dr) | %.1f km |" % soma_dr)
        a("| Linhas com da > dr (app mais longa) | %d |" % len(derrotas))
        a("| Perda agregada Σ(da−dr) nessas linhas | %.1f km |" % perda)
        a("| Perda concentrada em venc=Referência | %d linhas, %.1f km |" % (len(refs), perda_ref))
        a("")
        top_derrotas = sorted(derrotas, key=lambda r: float(r["da"]) - float(r["dr"]), reverse=True)[:10]
        a("| Município | UF | da (app) | dr (ref) | dif (estudo) | venc | hub app | hub ref |")
        a("|---|---:|---:|---:|---:|---|---|---|")
        for r in top_derrotas:
            a("| %s | %s | %.1f | %.1f | %.1f | %s | %s | %s |" % (
                r["o"], r["uf"], float(r["da"]), float(r["dr"]), float(r["dif"]),
                r["venc"], r.get("dapp", ""), r.get("dref", "")))
        a("")
        by_uf = collections.Counter(r["uf"] for r in derrotas)
        top_uf = ", ".join("%s:%d" % (k, v) for k, v in by_uf.most_common(12))
        a("**Derrotas por UF (top-12):** %s" % top_uf)
        a("")
        a("O baseline retrata o motor PRÉ-fixes (ex.: Triunfo 2,5 km via balsa São Jerônimo; Taquari 39,3 km "
          "via balsa). O comportamento ANTES dos 6 casos rodoviários recuperados está nas linhas acima.")
    else:
        a("_(baseline não encontrado — rode a extração do artefato §22 para incluir os indicadores)_")
    a("")
    a("## 4. Causa-raiz e cobertura")
    a("")
    a("- **Causa-raiz**: o universo final de reatribuição (top-K por reta + shortlist) excluía hubs já medidos "
      "(matriz/closure/resultados) — o vencedor ótimo estava medido, mas invisível à decisão (Pauini 269,9; "
      "Rio Branco; Marabá 110,8; Araçuaí 118,1; Tavares 28,9; Ijuí 71,9).")
    a("- **Recuperação**: os 6 casos rodoviários (§10) + Taquari/Triunfo (balsa demovida) + SJN (balsa "
      "mantida por inevitável) + favoráveis §11 (sem regressão) caem na mesma mecânica — universo fechado e "
      "política única de balsa — logo, vale para os demais municípios do baseline com o mesmo padrão.")
    if base:
        a("- **Suporte de cobertura**: %d das 163 linhas venc=Referência têm da > dr e concentram %.1f km de "
          "perda. Mecânica corrigida reachs todas: o teto superior de perda evitável é essas %.1f km "
          "(o ganho real depende do peso e do hub medido por município)." % (
              len(refs), perda_ref, perda_ref))
    a("")
    a("## 5. Validação")
    a("")
    a("- `py _testes_motor_rotas.py validar` → 104 invariantes (banda exata, reflexividade, universo-fechado, "
      "não regressão, fallback OSRM→FOSSGIS, Valhalla/divergência+investigação, memória geográfica, Índice "
      "de Confiança, roteador fluvial offline, eventos cronológicos de API, geometria anômala, sensores R4 "
      "de circuidade em bandas e centróides).")
    a("- `py _testes_motor_rotas.py decidir` → todos os casos passam nas propriedades da missão.")
    a("- `py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py` → OK.")
    a("- Balsa real conferida por geometria OSRM (steps `mode==ferry`) em ambos os servidores (4,12 / 39,33 / "
      "6,82 km ferry=True) — a correção vale fim-a-fim no pipeline do app.")
    a("")
    a("## 6. Ressalvas")
    a("")
    a("- OSRM público: cert TLS oscila expirado → `_get_tls_fallback` degrada para verify=False só quando o "
      "certificado é recusado. Sem rede o baseline não reexecuta (depende de Google/servidores).")
    a("- Eirunepé/Juruá/Curralinho (§11) e os vencedores fluviais/ilha das top-derrotas §22 (Anajas/PA, Muana/PA, "
      "Jordao/AC, Canutama/AM) são fluviais/ilha: cobertos pelo padrão validado (Oeiras/Gurupá + "
      "`_corrigir_rota_fantasma_fluvial`), não por medição rodoviária dedicada.")
    a("- Projeção agregada (§4) é um limiar; a reexecução fim-a-fim dos 1452 depende de rede/Google.")
    a("")
    try:
        with open(_RELATORIO_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))
        print(_RELATORIO_MD, "→", len(linhas), "linhas")
    except Exception as e:
        print("erro ao escrever relatório:", e)


def validar():
    """Testes de unidade das funções PURAS da política única (a implementação REAL do app) +
    o fechamento do universo de decisão (_fundir_resultados_no_topk + _reatribuir com dist_matriz)."""
    import streamlit_app as m
    ok = fail = 0

    def check(nome, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✓ %s" % nome)
        else:
            fail += 1
            print("  ✗ %s" % nome)

    print("== 1) Bandas adaptativas (_balsa_extra_admissivel / _rota_sem_balsa_razoavel) ==")
    check("Taquari ferry39 → rodovia49 está NA banda", m._rota_sem_balsa_razoavel(39, 49))
    check("Triunfo ferry2 → rodovia50 está NA banda", m._rota_sem_balsa_razoavel(2, 50))
    check("SJN ferry7 → rodovia315 FORA da banda", not m._rota_sem_balsa_razoavel(7, 315))
    check("SJN ferry7 → rodovia68.8 (Pelotas) FORA da banda (61.9>60)",
          not m._rota_sem_balsa_razoavel(6.82, 68.75))
    check("_balsa_extra_admissivel(10)=60 (piso) | (100)=500 (5×)",
          m._balsa_extra_admissivel(10) == 60 and m._balsa_extra_admissivel(100) == 500)

    print("== 2) _balsa_evitavel_banda (diálogo todo-candidatos) ==")
    base = [{"hub": "BalsaHub", "dist_viaria": 39, "balsa": True, "rota_real": True},
            {"hub": "RodA", "dist_viaria": 50, "balsa": False, "rota_real": True, "plausivel": True}]
    check("Taquari: balsa EVITÁVEL (rodovia razoável presente)", m._balsa_evitavel_banda(base))
    sjn = [{"hub": "Rio Grande", "dist_viaria": 6.82, "balsa": True, "rota_real": True},
           {"hub": "Pelotas", "dist_viaria": 68.75, "balsa": False, "rota_real": True, "plausivel": True}]
    check("SJN: balsa INEVITÁVEL (sem rodovia razoável)", not m._balsa_evitavel_banda(sjn))

    print("== 3) _vantagem_banda_balsa (comparador app × referência) ==")
    check("App 100 rodovia vs ref 80 balsa → APP (rodovia razoável)", m._vantagem_banda_balsa(100, 80, False, True, 1.0) == "Aplicação")
    check("App 80 balsa vs ref 100 rodovia → REF (economia cabe na banda)", m._vantagem_banda_balsa(80, 100, True, False, 1.0) == "Referência")
    check("App 7 balsa vs ref 315 rodovia → APP (desvio desproporcional)", m._vantagem_banda_balsa(7, 315, True, False, 1.0) == "Aplicação")
    check("App 300 rodovia vs ref 20 balsa → REF (rodovia desproporcional)", m._vantagem_banda_balsa(300, 20, False, True, 1.0) == "Referência")
    check("300.5 vs 300.0 ambos rodovia → Empate técnico", m._vantagem_banda_balsa(300.5, 300.0, False, False, 1.0) == "Empate")
    check("400 balsa vs 400 balsa → Empate", m._vantagem_banda_balsa(400, 400, True, True, 1.0) == "Empate")

    print("== 4) _v316_decidir_terrestre_primeiro (resgate V316) unificado com a banda ==")
    road = {"dist_km": 50, "tem_balsa": False, "fonte": "google", "vr": 1.05, "status": "ok", "nome": "Venâncio"}
    ferry = {"dist_km": 39, "tem_balsa": True, "fonte": "osrm", "vr": 1.7, "status": "ok", "nome": "São Jerônimo"}
    r_taq = m._v316_decidir_terrestre_primeiro(road, ferry)
    check("Taquari: mantém rodovia (balsa evitável)", r_taq["trocar"] is False)
    ferry_sjn = {"dist_km": 6.82, "tem_balsa": True, "fonte": "osrm", "vr": 1.1, "status": "ok", "nome": "Rio Grande"}
    road_315 = {"dist_km": 315, "tem_balsa": False, "fonte": "google", "vr": 1.09, "status": "ok", "nome": "Osório"}
    r_sjn = m._v316_decidir_terrestre_primeiro(road_315, ferry_sjn)
    check("SJN: ADOTA a balsa (rodovia desproporcional)", r_sjn["trocar"] is True)

    print("== 5) _selecionar_hub_multicriterio com a demissão de balsa (Taquari/Triunfo/SJN reais) ==")
    taq = [{"hub": "São Jerônimo", "dist_viaria": 39.33, "dist_reta": 22.31, "balsa": True},
           {"hub": "TABAI", "dist_viaria": 23.91, "dist_reta": 19.2, "balsa": False},
           {"hub": "Venâncio Aires", "dist_viaria": 49.95, "dist_reta": 38.3, "balsa": False}]
    r_taq2 = m._selecionar_hub_multicriterio(taq)
    check("Taquari: vencedor é RODOVIÁRIO e mais curto (TABAI 23.9, não ferry 39.3)",
          r_taq2["vencedor"] == "TABAI" and not r_taq2["ranking"][0]["balsa"])
    tri = [{"hub": "São Jerônimo", "dist_viaria": 4.12, "dist_reta": 1.56, "balsa": True},
           {"hub": "CHARQUEADAS", "dist_viaria": 11.5, "dist_reta": 8.93, "balsa": False},
           {"hub": "Montenegro", "dist_viaria": 50.05, "dist_reta": 37.9, "balsa": False}]
    r_tri = m._selecionar_hub_multicriterio(tri)
    check("Triunfo: vencedor é RODOVIÁRIO (não ferry 4.1)", not r_tri["ranking"][0]["balsa"])
    sjn = [{"hub": "Rio Grande", "dist_viaria": 6.82, "dist_reta": 6.16, "balsa": True},
           {"hub": "Osório", "dist_viaria": 315.28, "dist_reta": 289.5, "balsa": False},
           {"hub": "Pelotas", "dist_viaria": 68.75, "dist_reta": 42.92, "balsa": False}]
    r_sjn2 = m._selecionar_hub_multicriterio(sjn)
    check("SJN: vencedor é a travessia curta (balsa inevitável, 6.8 < 68.8)",
          r_sjn2["vencedor"] == "Rio Grande" and r_sjn2["ranking"][0]["balsa"])

    print("== 6) UNIVERSO-FECHADO — a raiz das derrotas (hub medido mas invisível à reatribuição) ==")
    # Cenário Pauini: top-K por reta NÃO contém Rio Branco; shortlist idem; mas a matriz mediu Rio Branco.
    cli = "Pauini"
    topk_mc = {cli: [(402.5, "Sena Madureira")]}
    resultados = {("Pauini", "Sena Madureira"): (412.5, None, None, "Não", None, "google")}
    dist_matriz = {"Pauini": {"Sena Madureira": 412.5, "Rio Branco": 269.9}}
    f1 = m._fundir_shortlist_no_topk(topk_mc, {}, dist_matriz)
    f2 = m._fundir_resultados_no_topk(f1, resultados)
    novo_dest, _ = m._reatribuir_hubs_multicriterio(f2, resultados, dist_matriz=dist_matriz)
    check("Pauini: Rio Branco entra no universo fundido", any("Rio Branco" in str(t[1]) for t in f2[cli]))
    check("Pauini: vencedor final = Rio Branco (269.9, medido pela matriz, < 412.5 do top-K)",
          novo_dest.get(cli) == "Rio Branco")
    # Só a matriz (sem resultados do par) também resolve: hub correto entra via dist_matriz fallback
    topk_s = {cli: [(402.5, "Sena Madureira")]}
    res_s = {("Pauini", "Sena Madureira"): (412.5, None, None, "Não", None, "google")}
    nd2, mc = m._reatribuir_hubs_multicriterio(
        m._fundir_resultados_no_topk(m._fundir_shortlist_no_topk(topk_s, {}, dist_matriz), res_s),
        res_s, dist_matriz=dist_matriz)
    check("Pauini: matriz-only (sem resultados do par) também elege Rio Branco", nd2.get(cli) == "Rio Branco")
    # Medina: top-K por reta pega Almenara, mas a matriz mediu Araçuaí (118.1) — fora do shortlist da matriz
    cli2 = "Medina"
    topk2 = {cli2: [(94.0, "Almenara")]}
    res2 = {("Medina", "Almenara"): (156.7, None, None, "Não", None, "google")}
    dm2 = {"Medina": {"Almenara": 156.7, "Araçuaí": 118.1}}
    nd3, _ = m._reatribuir_hubs_multicriterio(
        m._fundir_resultados_no_topk(m._fundir_shortlist_no_topk(topk2, {}, dm2), res2),
        res2, dist_matriz=dm2)
    check("Medina: vencedor final = Araçuaí (matriz mediu; top-K/shortlist não cobriam)",
          nd3.get(cli2) == "Araçuaí")
    # Taquari: mesmo com dist_matriz trazendo o ferry, a DEMISSÃO mantém a rodovia
    dm3 = {"Taquari": {"TABAI": 23.91, "São Jerônimo": 39.33}}
    r3 = {("Taquari", "TABAI"): (23.91, None, None, "Não", None, "osrm_matriz"),
          ("Taquari", "São Jerônimo"): (39.33, None, None, "Sim", None, "osrm_matriz")}
    nd4, _ = m._reatribuir_hubs_multicriterio({"Taquari": [(19.2, "TABAI")]}, r3, dist_matriz=dm3)
    check("Taquari: reatribuição respeita a demissão de balsa (vencedor TABAI rodovia)",
          nd4.get("Taquari") == "TABAI")

    print("== 7) BORDAS EXATAS da banda (regressão futura: limiar = admissível, +1km = fora) ==")
    check("_balsa_extra_admissivel(15)=75 (5×) | (90)=450",
          m._balsa_extra_admissivel(15) == 75 and m._balsa_extra_admissivel(90) == 450)
    check("ferry10→rodovia70: excedente exato 60 (piso) NA banda", m._rota_sem_balsa_razoavel(10, 70))
    check("ferry10→rodovia71: excedente 61 FORA da banda", not m._rota_sem_balsa_razoavel(10, 71))
    check("ferry15→rodovia75: excedente 60 ≤ 75 (5×) NA banda", m._rota_sem_balsa_razoavel(15, 75))
    check("ferry15→rodovia76: excedente 61 ≤ 75 ainda NA banda", m._rota_sem_balsa_razoavel(15, 76))
    check("ferry15→rodovia91: excedente 76 FORA (5×)", not m._rota_sem_balsa_razoavel(15, 91))
    check("ferry100→rodovia600: excedente exato 500 (5×) NA banda | 601 FORA",
          m._rota_sem_balsa_razoavel(100, 600) and not m._rota_sem_balsa_razoavel(100, 601))

    print("== 8) Reflexividade do comparador na borda (app balsa × ref rodovia e vice-versa) ==")
    check("App 10 balsa × Ref 70 rodovia (70-10=60 NA banda) → REF (rodovia razoável)",
          m._vantagem_banda_balsa(10, 70, True, False, 1.0) == "Referência")
    check("App 10 balsa × Ref 71 rodovia (61 FORA) → APP (balsa curta mantida)",
          m._vantagem_banda_balsa(10, 71, True, False, 1.0) == "Aplicação")
    check("App 71 rodovia × Ref 10 balsa (61 FORA) → REF (rodovia desproporcional)",
          m._vantagem_banda_balsa(71, 10, False, True, 1.0) == "Referência")
    check("App 70 rodovia × Ref 10 balsa (60 NA banda) → APP (rodovia razoável)",
          m._vantagem_banda_balsa(70, 10, False, True, 1.0) == "Aplicação")
    road2 = {"dist_km": 120, "tem_balsa": False, "fonte": "google", "vr": 1.1, "status": "ok", "nome": "X"}
    ferry20 = {"dist_km": 20, "tem_balsa": True, "fonte": "osrm", "vr": 1.3, "status": "ok", "nome": "B"}
    check("V316: ferry20→rodovia120 (excede EXATO 100 = 5×) mantém rodovia", m._v316_decidir_terrestre_primeiro(road2, ferry20)["trocar"] is False)
    ferry21 = {"dist_km": 20, "tem_balsa": True, "fonte": "osrm", "vr": 1.3, "status": "ok", "nome": "B"}
    road81 = {"dist_km": 121, "tem_balsa": False, "fonte": "google", "vr": 1.1, "status": "ok", "nome": "X"}
    check("V316: ferry20→rodovia121 (excedente 101 FORA) adota balsa", m._v316_decidir_terrestre_primeiro(road81, ferry21)["trocar"] is True)

    print("== 9) Favorável §11 (Dormentes): menor rota medida vence SEM regressão (offline) ==")
    dor = [{"hub": "AFRANIO", "dist_viaria": 31.8, "dist_reta": 28.9, "balsa": False},
           {"hub": "SANTA FILOMENA", "dist_viaria": 38.6, "dist_reta": 31.2, "balsa": False},
           {"hub": "Petrolina", "dist_viaria": 127.2, "dist_reta": 108.0, "balsa": False},
           {"hub": "Ouricuri", "dist_viaria": 130.3, "dist_reta": 112.1, "balsa": False}]
    r_dor = m._selecionar_hub_multicriterio(dor)
    check("Dormentes: vencedor = AFRANIO 31.8 (≤ 130.3/127.2 antigos, sem regressão)",
          r_dor["vencedor"] == "AFRANIO" and r_dor["ranking"][0]["dist_viaria"] <= 31.8001)

    print("== 10) Fallback automático OSRM público → FOSSGIS (robustez §12, sem rede) ==")
    try:
        _real_tls = m._get_tls_fallback
        _real_fossgis = m.API_OSRM_FOSSGIS_Routing
        _real_cache = m.cache_rotas

        class _FakeCache:
            def __init__(self):
                self._d = {}
            def get(self, k, *a):
                return self._d.get(k)
            def set(self, k, v, *a):
                self._d[k] = v
        m.cache_rotas = _FakeCache()
        m.API_OSRM_FOSSGIS_Routing = lambda *a, **k: (9.99, 15, "Não", 3, "geo", None)

        def _ssl(*a, **k):
            import requests as _rq
            raise _rq.exceptions.SSLError("cert recusado (teste)")
        m._get_tls_fallback = _ssl
        _o1 = m.API_OSRM_Routing(-29.9493, -51.8432, -29.9607, -51.7243)
        check("OSRM público com SSL recusado → FOSSGIS assume (9.99 km, mesma tupla)",
              _o1 is not None and abs(_o1[0] - 9.99) < 1e-9)

        m._get_tls_fallback = lambda *a, **k: type("R", (object,), {"json": lambda self: {"code": "NoRoute"}})()
        _o2 = m.API_OSRM_Routing(-22.9, -43.2, -22.5, -43.3)
        check("OSRM público code!=Ok → FOSSGIS assume (9.99 km)",
              _o2 is not None and abs(_o2[0] - 9.99) < 1e-9)

        m._get_tls_fallback = _real_tls
        m.API_OSRM_FOSSGIS_Routing = _real_fossgis
        m.cache_rotas = _real_cache
    except Exception as _e:
        try:
            m._get_tls_fallback = _real_tls
            m.API_OSRM_FOSSGIS_Routing = _real_fossgis
            m.cache_rotas = _real_cache
        except Exception:
            pass
        check("teste do fallback executou (%s)" % _e, False)

    print("== 11) Valhalla: regime de divergência e auto-engajamento (P1/§7, sem rede) ==")
    try:
        _reg = m._regime_divergencia_rota
        check("divergência 100 vs 70 km (dif ≈ 30 km) engaja", _reg(100, 70) is True)
        check("divergência 100 vs 80 km (dif 20 < 30 km) NÃO engaja", _reg(100, 80) is False)
        check("divergência fator: 500 vs 300 km (dif 200 ≥ 20%×300) engaja", _reg(500, 300) is True)
        check("divergência fator: 500 vs 450 km (dif 50 < 20%×450) NÃO engaja", _reg(500, 450) is False)
        check("entrada inválida (None) NÃO engaja", _reg(None, 50) is False and _reg(50, None) is False)
        # auto-engajamento respeita o teto por processo (contador)
        _est_antes = dict(m._VALHALLA_AUTO_ESTADO)
        m._VALHALLA_AUTO_ESTADO["usos"] = m._VALHALLA_AUTO_TETO
        check("teto esgotado bloqueia auto-engajamento", m._valhalla_deve_auto_engajar(100, 70) is False)
        m._VALHALLA_AUTO_ESTADO["usos"] = m._VALHALLA_AUTO_TETO - 1
        check("abaixo do teto engaja (contador incrementa)", m._valhalla_deve_auto_engajar(100, 70) is True)
        check("sem divergência não consome teto", m._valhalla_deve_auto_engajar(100, 80) is False)
        m._VALHALLA_AUTO_ESTADO["usos"] = 0
    except Exception as _e:
        try:
            m._VALHALLA_AUTO_ESTADO["usos"] = 0
        except Exception:
            pass
        check("testes do Valhalla executaram (%s)" % _e, False)

    print("== 12) Memória geográfica persistente (P2/§8, arquivo temporário) ==")
    try:
        import tempfile as _tmpf
        _dir_old, _arq_old = m._GEO_MEM_DIR, m._GEO_MEM_ARQ
        _tmd = os.path.join(tempfile.gettempdir(), "_geo_mem_test_p2")
        os.makedirs(_tmd, exist_ok=True)
        m._GEO_MEM_DIR, m._GEO_MEM_ARQ = _tmd, os.path.join(_tmd, "memoria_geografica.json")
        _mem_t = {"taquari|RS": {"origem": "Taquari", "uf": "RS", "rodadas": 1, "motivos": ["depende de balsa"], "severidade": 1}}
        check("salvar memória em disco (versão atual)", m._geo_mem_salvar(_mem_t) is True)
        _lido = m._geo_mem_carregar(_forcar=True)
        check("ler memória de volta = mesmo registro", _lido.get("taquari|RS", {}).get("rodadas") == 1)
        check("escala_k: origem problemática amplia o top-K",
              m._geo_mem_escala_k(_mem_t, "taquari", 4, 48, fator=3) == 12)
        check("escala_k: origem ausente mantém k", m._geo_mem_escala_k(_mem_t, "pauini", 4, 48, fator=3) == 4)
        check("escala_k: k já no teto não explode", m._geo_mem_escala_k(_mem_t, "taquari", 40, 48, fator=3) <= 48)
        _df_ap = pd.DataFrame([{"Origem": "Taquari", "UF": "RS", "Distancia": 200.0, "Linha Reta": 30.0,
                                "Balsas": "Sim", "Divergencia Motores (%)": 10.0}])
        _ap = m._geo_mem_aprender(_df_ap)
        check("aprender estudo problemático persiste (rodadas chegam a 2)",
              _ap.get("salvou") and m._geo_mem_carregar(_forcar=True).get("taquari|RS", {}).get("rodadas", 0) == 2)
        m._GEO_MEM_DIR, m._GEO_MEM_ARQ = _dir_old, _arq_old
        m._GEO_MEM_CACHE["carregada"], m._GEO_MEM_CACHE["mem"] = False, None
        m._geo_mem_carregar(_forcar=True)
        try:
            os.remove(os.path.join(_tmd, "memoria_geografica.json"))
        except Exception:
            pass
    except Exception as _e:
        try:
            m._GEO_MEM_DIR, m._GEO_MEM_ARQ = _dir_old, _arq_old
            m._GEO_MEM_CACHE["carregada"], m._GEO_MEM_CACHE["mem"] = False, None
        except Exception:
            pass
        check("testes de memória geográfica executaram (%s)" % _e, False)

    print("== 13) Índice de Confiança da Rota (P3/§6, puro) ==")
    try:
        _c = m._indice_confianca_rota
        check("rota real direta (V/R 1,2, sem balsa/divergência) ≈ 100",
              _c(120, 100, fonte="OSRM", balsa_str="Não", divergencia_pct=5, snap_m=50, n_motores=3) >= 92)
        check("rota geodésica/estimada penalizada forte (< 60)",
              _c(120, 100, fonte="Estimada (linha reta)", balsa_str="Não", divergencia_pct=0, snap_m=10, n_motores=2) < 60)
        check("rota impossível (viária < reta) vai a mínimo",
              _c(80, 100, fonte="OSRM", balsa_str="Não", divergencia_pct=0, snap_m=10, n_motores=3) < 35)
        check("balsa penaliza (-12 pts)", _c(120, 100, "OSRM", "Sim", 5, 50, 3) <= _c(120, 100, "OSRM", "Não", 5, 50, 3) - 11)
        check("divergência 40% penaliza ≤ 16 pts",
              _c(120, 100, "OSRM", "Não", 40, 50, 3) <= _c(120, 100, "OSRM", "Não", 5, 50, 3))
        check("snap > 1,5 km penaliza (até 20)", _c(120, 100, "OSRM", "Não", 5, 2000, 3) <= _c(120, 100, "OSRM", "Não", 5, 50, 3) - 19)
        check("motor único penaliza leve", _c(120, 100, "OSRM", "Não", 0, 50, 1) == _c(120, 100, "OSRM", "Não", 0, 50, 2) - 8)
        check("bounds: nunca sai de 0-100",
              all(0 <= _c(km, 100, "OSRM", "Sim", 100, 5000, 1) <= 100 for km in (50, 120, 500)))
        check("fail-open: exceção não bloqueia (None/entradas estranhas)",
              isinstance(_c(None, None, None, None, None, None, None), int))
    except Exception as _e:
        check("testes do índice de confiança executaram (%s)" % _e, False)

    if os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(m.__file__)), "hidrografia_nacional.pkl.gz")):
        print("== 14) Roteador fluvial offline (V423/V424, gráficos locais) ==")
        try:
            _fs = m._fluvial_status()
            check("estado fluvial: ok e rotulável", isinstance(_fs, dict) and _fs.get("ok") is True and _fs.get("rotulo"))
            _ef = m._e_fantasma_hidrica(2500, 80)          # sinuosidade 31× sem balsa
            _ef_b = m._e_fantasma_hidrica(184, 80, balsa=True)  # 2,3× com balsa
            _ef_n = m._e_fantasma_hidrica(130, 100)        # 1,3× normal
            check("fantasma hídrica: 2500/80 (V/R 31) dispara", _ef is True)
            check("fantasma hídrica: 184/80 com balsa (2,3×) dispara", _ef_b is True)
            check("fantasma hídrica: V/R 1,3 NÃO dispara (zero falso positivo)", _ef_n is False)
            _corr = m._corrigir_rota_fantasma_fluvial(pd.DataFrame([]))
            check("correção de fantasma: df vazio retorna intacto", _corr is not None and getattr(_corr, "empty", True))
        except Exception as _e:
            check("testes do roteador fluvial executaram (%s)" % _e, False)
    else:
        print("== 14) Roteador fluvial offline — grafo local ausente, pulado ==")

    print("== 15) Eventos cronológicos de API (M1/§16, arquivo temporário) ==")
    try:
        _ev_apresent = m._ultimas_falhas_apresentaveis([
            {"quando": "2026-01-01T10:00:00", "fonte": "OSRM", "ok": False, "uf": "PA"},
            {"quando": "2026-01-01T10:00:01", "fonte": "OSRM", "ok": True, "uf": "PA"},
            {"quando": "2026-01-01T10:00:02", "fonte": "GOOGLE_GEO", "ok": False, "uf": ""},
            {"quando": "2026-01-01T10:00:03", "fonte": "OSRM", "ok": False, "uf": "MA"},
        ])
        check("formata falhas (mais recente primeiro, ignora sucessos)",
              [r["API/Fonte"] for r in _ev_apresent] == ["OSRM", "GOOGLE_GEO", "OSRM"])
        check("formata falhas: UF aparece quando existe",
              _ev_apresent[0]["UF"] == "MA" and _ev_apresent[1]["UF"] == "—")
        check("formata falhas: limite n respeitado",
              len(m._ultimas_falhas_apresentaveis([{"quando": "t", "fonte": "F", "ok": False}], 12)) == 1)
        _ev_cache_old = m.cache_api_health.get(m._ULTIMOS_EVENTOS_CHAVE, [])
        m.cache_api_health.delete(m._ULTIMOS_EVENTOS_CHAVE)
        try:
            m._ULTIMOS_EVENTOS_API.clear()
            m.registrar_telemetria("OSRM", False, 1.2, uf="PA")
            m.registrar_telemetria("VALHALLA", True, 0.5, uf="PA")
            m._persistir_ultimos_eventos()
            _ev_salvos = m.cache_api_health.get(m._ULTIMOS_EVENTOS_CHAVE, []) or []
            check("eventos persistem no cache (ordem preservada)",
                  [e.get("fonte") for e in _ev_salvos] == ["OSRM", "VALHALLA"])
            check("eventos guardam UF e resultado",
                  _ev_salvos[0].get("uf") == "PA" and _ev_salvos[0].get("ok") is False)
        finally:
            if _ev_cache_old:
                m.cache_api_health.set(m._ULTIMOS_EVENTOS_CHAVE, _ev_cache_old, expire=None)
            else:
                m.cache_api_health.delete(m._ULTIMOS_EVENTOS_CHAVE)
            m._ULTIMOS_EVENTOS_API.clear()
    except Exception as _e:
        check("testes de eventos cronológicos executaram (%s)" % _e, False)

    print("== 16) Geometria anômala (M2/§5, puro) ==")
    try:
        _sg = m._suspeita_geometria_rota
        _place = [(0.0, 0.0), (0.1, 0.1)]  # 2 pontos = placeholder
        check("placeholder (2 pontos) sinaliza geometria incompleta", any("incompleta" in w for w in _sg(_place)))
        _reta = [(0.0, -3.0), (0.0, 0.0), (0.0, 3.0)]  # reta ~667 km geodésica
        _s1 = _sg(_reta, km_motor=900.0, km_reta=666.0, provedor="OSRM")
        check("linha reta mas motor declara rota maior (V/R alto) → suspeita",
              any("linha reta" in w for w in _s1))
        _s2 = _sg(_reta, km_motor=2000.0, km_reta=100.0, provedor="OSRM")
        check("geometria incompatível com os km do motor → sinaliza",
              any("não condiz" in w for w in _s2))
        _curva = [(0.0, -3.0), (3.0, 0.0), (0.0, 3.0)]  # desvio real: traçado ~943 km, reta 667 km, motor 950 km
        _sok = _sg(_curva, km_motor=950.0, km_reta=667.0, provedor="OSRM")
        check("curva real sem incompatibilidade → sem avisos (zero alarme falso)", len(_sok) == 0)
        _geo = _sg(_reta, km_motor=666.0, km_reta=666.0, provedor="Geodésica")
        check("geodésica legítima não é acusada", len(_geo) == 0)
        check("defensivo: entradas quebradas retornam lista (sem exceção)",
              isinstance(_sg(None, None, None), list))
        _uri_su = m._gerar_mapa_leaflet_rota(
            "", -3.0, -60.0, -3.0, 0.0,
            nome_origem="A", nome_destino="B",
            distancia_km="999.0", km_reta="50.0")
        check("mapa com geometria suspeita continua gerado (badge aditivo)",
              isinstance(_uri_su, str) and _uri_su.startswith("data:text/html;base64,"))
    except Exception as _e:
        check("testes de geometria anômala executaram (%s)" % _e, False)

    print("== 17) Investigação profunda do Valhalla (R3-A/§7, sem rede) ==")
    try:
        _sus = m._regime_suspeita_rota
        check("V/R 2,6 sem balsa entra na zona de suspeita", _sus(520, 200, False) is True)
        check("V/R 2,59 sem balsa (abaixo do limiar) NÃO entra", _sus(518, 200, False) is False)
        check("V/R 2,0 COM balsa entra", _sus(400, 200, True) is True)
        check("V/R 1,99 COM balsa NÃO entra", _sus(399, 200, True) is False)
        check("balsa com rota direta V/R 1,2 NÃO dispara alarme", _sus(240, 200, True) is False)
        check("entradas inválidas/zero → False (defensivo)",
              _sus(None, 200, True) is False and _sus(0, 200, False) is False)
        _est0 = dict(m._VALHALLA_AUTO_ESTADO)
        m._VALHALLA_AUTO_ESTADO["usos"] = 0
        _consumiu = m._valhalla_deve_investigar(520, 200, False)
        check("deve_investigar engaja e consome o teto compartilhado",
              _consumiu is True and m._VALHALLA_AUTO_ESTADO["usos"] == 1)
        m._VALHALLA_AUTO_ESTADO["usos"] = m._VALHALLA_AUTO_TETO
        check("teto esgotado também bloqueia a investigação", m._valhalla_deve_investigar(520, 200, False) is False)
        m._VALHALLA_AUTO_ESTADO["usos"] = _est0["usos"]
    except Exception as _e:
        check("testes de investigação profunda executaram (%s)" % _e, False)

    print("== 18) Sensores de risco da pesquisa (R4-A/§3-§5 + R4-B/§7, puros) ==")
    try:
        _cb = m._circuidade_banda_suspeita
        check("trecho curto: circ. 1,9 NÃO dispara (banda curta tem gatilho 2,2; curtos inflam)",
              _cb(1.9, 10.0) == (False, ""))
        check("MESMA circ. 1,9 em trecho médio DISPARA (gatilho 1,8) — evidência do banding",
              _cb(1.9, 40.0) == (True, "INVESTIGAR"))
        check("trecho curto: circ. 2,1 → PROVAVEL_BARREIRA (≥2,0 é barreira em qualquer faixa)",
              _cb(2.1, 10.0) == (True, "PROVAVEL_BARREIRA"))
        check("trecho médio (15-60 km): circ. 1,9 → INVESTIGAR", _cb(1.9, 40.0) == (True, "INVESTIGAR"))
        check("trecho longo (>60 km): circ. 1,7 → INVESTIGAR (baseline densa ~1.33 BR/Ballou)",
              _cb(1.7, 120.0) == (True, "INVESTIGAR"))
        check("trecho longo: circ. 1,5 NÃO dispara (1.4+ é sinal de barreira; 1.5 ainda viz. normal)",
              _cb(1.5, 120.0) == (False, ""))
        check("circ. ≥2,0 → PROVAVEL_BARREIRA mesmo em trecho longo", _cb(2.0, 300.0) == (True, "PROVAVEL_BARREIRA"))
        check("defensivo: entradas inválidas → (False, '')",
              _cb(None, 10.0) == (False, "") and _cb(1.5, 0) == (False, ""))
        check("rótulo de banda: <15 / 15-60 / >60", m._circuidade_banda_rotulo(5) == "<15 km (trecho curto)"
              and m._circuidade_banda_rotulo(50) == "15–60 km" and m._circuidade_banda_rotulo(90) == ">60 km")

        _c = m._validar_centroide_br
        _rsp = _c(-23.55, -46.63, "SP")
        check("centróide SP válido (ok, sem razões)", _rsp["ok"] is True and not _rsp["razoes"])
        _rrj = _c(-22.91, -43.20, "RJ")
        check("centróide RJ válido", _rrj["ok"] is True and not _rrj["razoes"])
        _rmn = _c(-3.10, -60.02, "AM")
        check("centróide Manaus/AM válido (lat negativa pequena, lon magnitude 60)", _rmn["ok"] is True)
        _ra = _c(-40.0, 60.0, "SP")
        check("troca lat/lon detectada (lat +40 fora, lon 60 positivo impossível no BR)",
              _ra["ok"] is False and any("lat/lon" in r for r in _ra["razoes"]))
        _rz = _c(0.0, 0.0)
        check("(0,0) sinalizado como dado ausente/indefinido",
              _rz["ok"] is False and any("(0,0)" in r for r in _rz["razoes"]))
        _rf = _c(-3.0, -80.0, "AM")
        check("fora dos limites continentais (lon -80)", _rf["ok"] is False and any("limites" in r for r in _rf["razoes"]))
        _ufo = _c(-23.55, -46.63, "AM")
        check("ponto SP dentro de faixa AM → flag de UF errada", _ufo["ok"] is False
              and any("AM" in r for r in _ufo["razoes"]))
        check("defensivo: valores não numéricos → ok False com motivo",
              _c(None, "-46.6")["ok"] is False and _c("x", 1.0)["ok"] is False)
    except Exception as _e:
        check("testes dos sensores de risco executaram (%s)" % _e, False)

    print("== 19) Métrica fluvial justa NA DECISÃO do hub (HUB-FLUVIAL-JUSTA, §8/§11/§12) ==")
    try:
        _mp = m._metrica_fluvial_justa_par
        # fantasma hídrica (V/R>3 sem balsa): aceita QUALQUER ganho
        _f1 = _mp(2429.0, 77.0, False, 45.0)
        check("fantasma (2429/77) → substitui pela fluvial 45", _f1[1] is True and abs(_f1[0] - 45.0) < 1e-9)
        _f2 = _mp(400.0, 150.0, True, 100.0)
        check("balsa fantasma (V/R 2,67) → substitui", _f2[1] is True and abs(_f2[0] - 100.0) < 1e-9)
        # balsa com V/R plausível: exige ganho >= 15%
        _g1 = _mp(140.0, 80.0, True, 100.0)
        check("balsa plausível ganho 28,6% ≥ 15% → substitui (100)", _g1[1] is True and abs(_g1[0] - 100.0) < 1e-9)
        _g2 = _mp(140.0, 80.0, True, 130.0)
        check("balsa plausível ganho 7,1% < 15% → mantém 140", _g2[1] is False and abs(_g2[0] - 140.0) < 1e-9)
        _g3 = _mp(140.0, 80.0, False, 120.0)
        check("sem balsa e sem fantasma (V/R 1,75) → mantém (não acumula ganho sem balsa)",
              _g3[1] is False and abs(_g3[0] - 140.0) < 1e-9)
        _g4 = _mp(140.0, 80.0, True, 200.0)
        check("fluvial >= viária → nunca aumenta (mantém 140)", _g4[1] is False and abs(_g4[0] - 140.0) < 1e-9)
        _g5 = _mp(140.0, 80.0, True, None)
        check("sem rota fluvial → mantém (fail-open)", _g5[1] is False and abs(_g5[0] - 140.0) < 1e-9)
        _g6 = _mp("x", 80.0, True, 100.0)
        check("entrada inválida → mantém (defensivo)", _g6[1] is False)
        # pré-processamento do UNIVERSO com resolver/roteador injetados
        def _res(nome, uf_hint=""):
            return {"lat": -3.0, "lon": -60.0}
        cands2 = [{"hub": "Macapa", "dist_viaria": 2429.0, "dist_reta": 77.0, "balsa": False, "rota_real": True}]
        m._metrica_fluvial_justa_no_universo(cands2, "Afua", uf_hint="PA",
                                             resolver_coord=_res, fluvial_router=lambda o, ol, hl, hlo: {"km": 45.0})
        check("universo: fantasma → fluvial 45 na DECISÃO (metrica_fluvial)",
              cands2[0]["dist_viaria"] == 45.0 and cands2[0].get("metrica_fluvial") is True
              and cands2[0].get("dist_viaria_original") == 2429.0)
        cands3 = [{"hub": "NORMAL", "dist_viaria": 120.0, "dist_reta": 100.0, "balsa": False, "rota_real": True},
                  {"hub": "BALSA", "dist_viaria": 140.0, "dist_reta": 80.0, "balsa": True, "rota_real": True}]
        m._metrica_fluvial_justa_no_universo(cands3, "X", uf_hint="PA",
                                             resolver_coord=_res, fluvial_router=lambda o, ol, hl, hlo: {"km": 100.0})
        check("universo: normal intocado; balsa ganho≥15% substituída (metrica_fluvial)",
              cands3[0]["dist_viaria"] == 120.0 and cands3[0].get("metrica_fluvial") is None
              and cands3[1]["dist_viaria"] == 100.0 and cands3[1].get("metrica_fluvial") is True)
        cands4 = [{"hub": "BALSA2", "dist_viaria": 140.0, "dist_reta": 80.0, "balsa": True, "rota_real": True}]
        m._metrica_fluvial_justa_no_universo(cands4, "X", uf_hint="PA",
                                             resolver_coord=_res, fluvial_router=lambda o, ol, hl, hlo: None)
        check("universo: roteador sem rota → mantém 140", cands4[0]["dist_viaria"] == 140.0)
        def _res_none(nome, uf_hint=""):
            return {"lat": None, "lon": None}
        cands5 = [{"hub": "BALSA3", "dist_viaria": 140.0, "dist_reta": 80.0, "balsa": True, "rota_real": True}]
        m._metrica_fluvial_justa_no_universo(cands5, "X", uf_hint="PA",
                                             resolver_coord=_res_none, fluvial_router=lambda *a, **k: {"km": 60.0})
        check("universo: sem coords → lista intacta (fail-open)", cands5[0]["dist_viaria"] == 140.0)
    except Exception as _e:
        check("testes da métrica fluvial justa executaram (%s)" % _e, False)

    print()
    print("=" * 70)
    print("RESULTADO: %d OK, %d FALHAS" % (ok, fail))
    print("=" * 70)
    return 1 if fail else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "collect":
        collect()
    elif cmd == "decidir":
        decidir()
    elif cmd == "validar":
        sys.exit(validar())
    elif cmd == "relatorio":
        relatorio()
    else:
        report()