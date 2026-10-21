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


def estimar_rodoviaria_km(reta_km) -> float:
    """Estimativa ESCALAR da distância RODOVIÁRIA (km) a partir da linha reta. Piso = a própria reta
    (fator ≥ 1). Entrada ≤ 0 ou inválida → 0,0. Nunca levanta."""
    try:
        r = float(reta_km)
    except (TypeError, ValueError):
        return 0.0
    if r <= 0:
        return 0.0
    return r * fator_desvio(r)


def estimar_rodoviaria_vetor(reta):
    """Versão VETORIZADA (numpy) de estimar_rodoviaria_km — aplica o fator por faixa element-wise.
    Aceita array/lista de linhas retas (km); devolve np.ndarray float64 (0,0 onde reta ≤ 0). Sem numpy
    disponível, cai no map escalar (lista). Nunca levanta."""
    try:
        import numpy as np
        a = np.asarray(reta, dtype="float64")
        f = np.full(a.shape, _FATOR_LONGO, dtype="float64")
        # Das faixas mais LARGAS para as mais ESTREITAS: a última a casar (a correta) sobrescreve.
        for ate, fat in reversed(_BANDAS):
            f = np.where(a < ate, fat, f)
        out = a * f
        return np.where(a > 0.0, out, 0.0)
    except Exception:
        try:
            return [estimar_rodoviaria_km(x) for x in (reta or [])]
        except Exception:
            return []


def estimar_tempo_min(km) -> float:
    """Tempo estimado (minutos) para uma distância rodoviária em km, pelo mesmo modelo do web:
    45 km/h abaixo de 50 km, 65 km/h acima. 0,0 para km ≤ 0 ou inválido. Nunca levanta."""
    try:
        d = float(km)
    except (TypeError, ValueError):
        return 0.0
    if d <= 0:
        return 0.0
    v = _V_CURTA_KMH if d < 50.0 else _V_LONGA_KMH
    return round((d / v) * 60.0, 1)


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
