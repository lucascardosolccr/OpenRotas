# -*- coding: utf-8 -*-
"""OpenRotas Desktop — ESTIMATIVA DE DISTÂNCIA RODOVIÁRIA a partir da linha reta (PARIDADE COM O WEB).

Por que este módulo existe (o motivo nº 1 de o desktop "parecer pior" que a aplicação web):

  A aplicação WEB NUNCA apresenta a LINHA RETA (geodésica) como se fosse a distância de viagem.
  Quando não há roteamento viário real disponível (Google/OSRM/GraphHopper/Valhalla), ela ESTIMA a
  distância rodoviária multiplicando a linha reta por um FATOR DE DESVIO (sinuosidade) calibrado por
  faixa de distância — a função `obter_fator_desvio_rodoviario` do motor web (streamlit_app.py:37591),
  aplicada como `km_terrestre = linha_reta × fator` (streamlit_app.py:39734).

  O desktop, por outro lado, reportava a LINHA RETA CRUA no modo offline (matriz, isócronas, centro
  ótimo) — subestimando o deslocamento real em ~18–45% e parecendo, por isso, menos realista que o
  web. Este módulo traz o MESMO fator ao desktop, para que a estimativa offline do desktop seja IGUAL
  à estimativa de fallback do web — a paridade que o usuário sentia faltar.

Fatores por faixa (ESPELHO EXATO do web — pesquisa de circuidade; média nacional ~1,33, Ballou et al.
2002; trechos curtos inflam por acesso urbano/contorno, a malha tronco de longa distância é mais direta):

    linha reta < 5 km    → ×1,45
    5 – 20 km            → ×1,35
    20 – 100 km          → ×1,25
    ≥ 100 km             → ×1,18

Tempo estimado: mesmo modelo do web (streamlit_app.py:39735) — velocidade comercial de 45 km/h abaixo
de 50 km (acesso urbano/vicinal) e 65 km/h acima (malha tronco).

HONESTIDADE (§71): é ESTIMATIVA, não medição. A linha reta permanece como PISO FÍSICO — nenhuma estrada
é mais curta que o 'voo de pássaro' — e os relatórios declaram o modo ("estimado") e preservam a reta.
Puro (numpy opcional + stdlib): nunca levanta."""
from __future__ import annotations

# Limiares (km) e fatores de desvio — ESPELHO EXATO de obter_fator_desvio_rodoviario (web). Ordenado do
# menor limiar para o maior; a primeira faixa cujo teto a reta não alcança define o fator.
_BANDAS = ((5.0, 1.45), (20.0, 1.35), (100.0, 1.25))
_FATOR_LONGO = 1.18          # ≥ 100 km (malha tronco, mais direta)

# Modelo de tempo (idêntico ao web): velocidade comercial por porte da distância.
_V_CURTA_KMH = 45.0          # < 50 km: acesso urbano/vicinal
_V_LONGA_KMH = 65.0          # ≥ 50 km: malha tronco

# [CONSCIÊNCIA FLUVIAL] Fator de sinuosidade FLUVIAL para municípios de acesso só fluvial/aéreo (sem
# ligação rodoviária): o trajeto REAL é por rio, que meandra muito mais que estrada. A pesquisa de
# circuidade do web registra ~3,1× a linha reta nas regiões amazônicas fluviais; usamos 3,0 (conservador).
# Sem isto, o desktop estimava esses municípios por fator RODOVIÁRIO (~1,2×) — uma estrada que não existe.
_FATOR_FLUVIAL = 3.0
# Velocidade fluvial típica (barco/lancha regional) para o tempo estimado nesses trechos.
_V_FLUVIAL_KMH = 22.0

# Municípios de acesso SÓ fluvial (por RIO, sem ligação rodoviária), Códigos IBGE de 7 dígitos — base
# oficial IBGE REGIC 2018 ("Ligações Rodoviárias e Hidroviárias"). São os 17 amazônicos (15 AM + 2 PA)
# da lista do web; Fernando de Noronha/PE (2605459) foi DELIBERADAMENTE EXCLUÍDO: é ilha OCEÂNICA (acesso
# aéreo/marítimo em mar aberto ≈ linha reta), e o fator de sinuosidade FLUVIAL (~3× por meandro de rio)
# superestimaria muito o seu deslocamento. Para o rio amazônico o ~3× é fiel (circuidade observada ~3,1).
_MUNICIPIOS_ACESSO_FLUVIAL = frozenset({
    "1300029", "1300201", "1300409", "1300680", "1301605", "1302108", "1302207", "1302306",
    "1302801", "1303007", "1303601", "1303908", "1304104", "1304237", "1304260", "1500701",
    "1502509",
})


def _norm_ibge(cod) -> str:
    """Normaliza um Código IBGE para 7 dígitos (só dígitos, zero-padding). '' se vazio/inválido."""
    try:
        d = "".join(ch for ch in str(cod or "") if ch.isdigit())
    except Exception:
        return ""
    return d.zfill(7) if d else ""


def municipio_acesso_fluvial(cod_ibge, conjunto=None) -> bool:
    """O município (Código IBGE) consta na lista oficial de acesso só fluvial/isolado (sem ligação
    rodoviária)? Retorna bool. `conjunto` injetável para teste. PURA (paridade com o web)."""
    conjunto = _MUNICIPIOS_ACESSO_FLUVIAL if conjunto is None else conjunto
    c = _norm_ibge(cod_ibge)
    return bool(c) and c in (conjunto or frozenset())


def mascara_acesso_fluvial(geocodigos, conjunto=None) -> list:
    """Máscara booleana (lista) para um iterável de Códigos IBGE: True onde o município é de acesso
    só fluvial/isolado. Para aplicar o fator fluvial a muitos municípios de uma vez. Nunca levanta."""
    try:
        return [municipio_acesso_fluvial(g, conjunto) for g in (geocodigos or [])]
    except Exception:
        return []


def fator_desvio(reta_km) -> float:
    """Fator de desvio rodoviário (sinuosidade) para uma linha reta em km. Idêntico ao web.
    Defensivo: entrada não-numérica → fator de longa distância (o mais conservador)."""
    try:
        r = float(reta_km)
    except (TypeError, ValueError):
        return _FATOR_LONGO
    for ate, f in _BANDAS:
        if r < ate:
            return f
    return _FATOR_LONGO


def estimar_rodoviaria_km(reta_km, fluvial: bool = False) -> float:
    """Estimativa ESCALAR da distância (km) a partir da linha reta. Piso = a própria reta (fator ≥ 1).
    `fluvial=True` usa o fator de sinuosidade FLUVIAL (~3×, acesso só por rio) em vez do rodoviário.
    Entrada ≤ 0 ou inválida → 0,0. Nunca levanta."""
    try:
        r = float(reta_km)
    except (TypeError, ValueError):
        return 0.0
    if r <= 0:
        return 0.0
    return r * (_FATOR_FLUVIAL if fluvial else fator_desvio(r))


def estimar_rodoviaria_vetor(reta, fluvial=None):
    """Versão VETORIZADA (numpy) de estimar_rodoviaria_km — fator por faixa element-wise. `fluvial` pode
    ser None (tudo rodoviário), um bool (todo o vetor), ou uma máscara/array booleana por elemento
    (fluvial onde True). Devolve np.ndarray float64 (0,0 onde reta ≤ 0). Sem numpy, cai no map escalar."""
    try:
        import numpy as np
        a = np.asarray(reta, dtype="float64")
        f = np.full(a.shape, _FATOR_LONGO, dtype="float64")
        # Das faixas mais LARGAS para as mais ESTREITAS: a última a casar (a correta) sobrescreve.
        for ate, fat in reversed(_BANDAS):
            f = np.where(a < ate, fat, f)
        out = a * f
        if fluvial is not None:
            mask = np.asarray(fluvial, dtype=bool)
            out = np.where(mask, a * _FATOR_FLUVIAL, out)   # fluvial sobrescreve o fator rodoviário
        return np.where(a > 0.0, out, 0.0)
    except Exception:
        try:
            _fl = bool(fluvial) if not isinstance(fluvial, (list, tuple)) else False
            return [estimar_rodoviaria_km(x, fluvial=_fl) for x in (reta or [])]
        except Exception:
            return []


def estimar_tempo_min(km, fluvial: bool = False) -> float:
    """Tempo estimado (minutos) para uma distância em km. Rodoviário: 45 km/h < 50 km, 65 km/h acima
    (modelo do web). `fluvial=True`: velocidade fluvial típica (~22 km/h). 0,0 para km ≤ 0. Nunca levanta."""
    try:
        d = float(km)
    except (TypeError, ValueError):
        return 0.0
    if d <= 0:
        return 0.0
    if fluvial:
        v = _V_FLUVIAL_KMH
    else:
        v = _V_CURTA_KMH if d < 50.0 else _V_LONGA_KMH
    return round((d / v) * 60.0, 1)


def formatar_duracao(minutos) -> str:
    """Minutos → 'Xh YYmin' (ou 'YY min' abaixo de 1h). '' para None/0/inválido. Compartilhado por
    matriz/isócronas/centro para falarem a mesma língua sobre tempo estimado."""
    try:
        m = int(round(float(minutos)))
    except (TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    return "%dh%02dmin" % (m // 60, m % 60) if m >= 60 else "%d min" % m


# ---------------------------------------------------------------------------
#  Rótulos de MODO — compartilhados por matriz/isócronas/centro para que os três
#  relatórios falem a MESMA língua sobre a procedência da distância.
# ---------------------------------------------------------------------------
_ROTULO_CURTO = {
    "rodoviario": "rodoviário",
    "rodoviario-parcial": "rodoviário+estimado",
    "estimado": "estimado",
    "geodesico": "geodésico",
}
_DESCRICAO = {
    "rodoviario": "rodoviária (OSRM)",
    "rodoviario-parcial": "rodoviária (OSRM) onde refinada; estimada no restante",
    "estimado": "rodoviária ESTIMADA (linha reta × fator de sinuosidade ~1,18–1,45×; a reta é o piso)",
    "geodesico": "geodésica (linha reta)",
}


def rotulo_modo(modo) -> str:
    """Rótulo curto do modo para KPIs/cabeçalhos ('rodoviário' | 'estimado' | 'geodésico' | ...)."""
    return _ROTULO_CURTO.get(str(modo), str(modo))


def descricao_modo(modo) -> str:
    """Frase descritiva do modo para a nota de rodapé dos relatórios."""
    return _DESCRICAO.get(str(modo), str(modo))


def aviso_fluvial(n) -> str:
    """Frase padrão de aviso para N município(s) de acesso fluvial/isolado, compartilhada pelos
    relatórios (matriz/isócronas/centro). '' quando n ≤ 0."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return ("%d município(s) de acesso SÓ fluvial/isolado (sem ligação rodoviária, IBGE REGIC) — a "
            "distância é estimada por sinuosidade FLUVIAL (~%.0f×), não rodoviária." % (n, _FATOR_FLUVIAL))


# ---------------------------------------------------------------------------
#  HAVERSINE (geodésica honesta) — substitui a distância PLANAR (dlon²+dlat²) que
#  ignora que 1° de longitude é MENOR que 1° de latitude em km (fator cos(lat) ~
#  0,87–0,92 no Brasil). A planar distorce a seleção do vizinho mais próximo e
#  infla a distância leste-oeste em até ~15% no Sul. O web usa haversine; isto
#  traz a MESMA régua ao desktop (dossiê: município/rio/estação mais próximos).
# ---------------------------------------------------------------------------
_R_TERRA_KM = 6371.0


def haversine_km(lon0, lat0, lons, lats):
    """Distância geodésica (km) de UM ponto (lon0,lat0) a cada (lons,lats). Vetorizada (numpy) quando
    `lons`/`lats` são arrays; escalar quando são números. Nunca levanta — erro → 0.0 / zeros."""
    try:
        import numpy as np
        la1 = np.radians(float(lat0))
        la2 = np.radians(np.asarray(lats, dtype="float64"))
        dla = la2 - la1
        dlo = np.radians(np.asarray(lons, dtype="float64") - float(lon0))
        a = np.sin(dla / 2.0) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlo / 2.0) ** 2
        return 2.0 * _R_TERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    except Exception:
        import math
        try:
            la1 = math.radians(float(lat0)); la2 = math.radians(float(lats))
            dlo = math.radians(float(lons) - float(lon0))
            a = math.sin((la2 - la1) / 2.0) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2.0) ** 2
            return 2.0 * _R_TERRA_KM * math.asin(math.sqrt(max(0.0, min(1.0, a))))
        except Exception:
            return 0.0


# ---------------------------------------------------------------------------
#  VALIDAÇÃO DE COORDENADA (Brasil) — paridade com _validar_centroide_br do web.
#  O desktop aceita 'lon,lat' cru (matriz/isócronas/centro) SEM checar nada; o erro
#  mais comum é digitar 'lat,lon' TROCADO, ou um ponto fora do Brasil, e o relatório
#  sair inteiro errado em silêncio. Aqui sinalizamos (não bloqueamos) os casos óbvios.
# ---------------------------------------------------------------------------
_BR_LAT_MIN, _BR_LAT_MAX = -33.8, 5.3       # limites continentais do Brasil (lat)
_BR_LON_MIN, _BR_LON_MAX = -74.0, -34.8     # limites continentais do Brasil (lon)


def validar_coordenada_br(lon, lat):
    """Valida (lon,lat) como ponto plausível no Brasil. Devolve lista de MOTIVOS (vazia = ok). Detecta:
    não-numérico, (0,0), troca lat/lon (|lat|>=34 ou |lon|<34) e fora dos limites continentais. PURA."""
    try:
        lo = float(lon); la = float(lat)
    except (TypeError, ValueError):
        return ["coordenada não numérica"]
    r = []
    if lo == 0.0 and la == 0.0:
        r.append("coordenada em (0,0) — provável dado ausente")
    if abs(la) >= 34.0:
        r.append("|lat|≥34 — provável troca lat/lon (a latitude do Brasil não passa de ~34)")
    if abs(lo) < 34.0:
        r.append("|lon|<34 — provável troca lat/lon (a longitude do Brasil tem magnitude 34–74)")
    if not (_BR_LAT_MIN <= la <= _BR_LAT_MAX and _BR_LON_MIN <= lo <= _BR_LON_MAX):
        if "troca lat/lon" not in " ".join(r):   # não repete o diagnóstico quando o motivo já é a troca
            r.append("fora dos limites continentais do Brasil")
    return r
