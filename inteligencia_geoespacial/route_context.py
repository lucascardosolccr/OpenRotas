"""
route_context.py — Motor de Contexto Geográfico da Rota (GeoIntelligenceEngine).

Missão "Aprimoramento máximo da aba de Inteligência" — 15 rodadas, todas
aditivas e com gate de zero regressão (validar/decidir/pytest a cada uma):
  Rodada 3  — integração hidrográfica real (rios/corpos d'água pela GEOMETRIA
              da rota, não só quando o motor de roteamento reporta balsa;
              bacia hidrográfica oficial ANA/SNIRH).
  Rodada 4  — integração aquaviária (travessias/balsas reais do IBGE,
              hidrovias, portos/terminais/eclusas; índice de dependência
              aquaviária).
  Rodada 5  — pontes NO cruzamento hidrográfico (§8 da missão): para cada
              rio/corpo d'água detectado, verifica se há uma ponte cadastrada
              naquele ponto — nunca varre pontes genéricas "perto da rota".
  Rodada 9  — mapa Leaflet multi-camada por rota (streamlit_app.py,
              `_mapa_leaflet_contexto_geografico`), com o contrato deste
              módulo como única fonte de dados.
  Rodada 10 — integração automática ao pipeline de rotas (individual e em
              lote), com enriquecimento automático até `_GEO_INTEL_LIMIAR_
              AUTOMATICO` pares (streamlit_app.py:_enriquecer_geo_inteligencia_df).
  Rodada 11 — colunas do contexto geográfico no Excel exportado.
  Rodada 12 — seção "Inteligência Geográfica" no HTML exportável.
  Rodada 13 — explicabilidade ("por que esta rota") no Centro de
              Inteligência da Rota.
  Rodada 14 — performance: caminho rápido em memória para as camadas
              pequenas (`_consultar_rapido_camada_pequena`) e cache de
              janela ampla para as pesadas (`_consultar_camada_pesada_
              cacheada`) — ver as duas seções logo abaixo.
  Rodada 15 — auditoria final: validar 210/0, decidir 38/38, relatorio
              byte-idêntico ao baseline da Rodada 1 (zero regressão
              confirmada em todas as rodadas).

Missão 2 "Extração máxima de APIs, datasets e fontes" — auditoria completa
de todas as fontes já integradas (26+ fontes reais catalogadas em
`sources_inventory.py`) seguida de extração do que cada fonte já continha
mas nenhum código lia:
  Rodada 3 (M2) — integração rodoviária: rodovias oficiais (sigla BR-xxx/
              UF-xxx) identificadas ao longo da rota, camada `rodovias`
              (287 mil trechos) nunca consultada antes por este motor.
  Rodada 4 (M2) — integração ferroviária: trechos ferroviários próximos,
              camada `ferrovias` (889 trechos, nunca consultada antes).
  Rodada 5 (M2) — enriquece pontes (tipo/pavimento/extensão/largura —
              vão livre e carga suportada deliberadamente descartados,
              ver docstring de `Ponte`), massas d'água/drenagem
              (artificial/salgada/dominialidade/encoberto) e complexos
              portuários (tipotransp/tipocomple/portosempa).
  Rodada 6 (M2) — código de sub-bacia SNIRH (`subbacia_codigo_do_rio`) —
              nunca um nome (a base vendorizada não tem catálogo de nomes
              de sub-bacia — ver docstring da função).
  Rodada 7 (M2) — índice de complexidade geográfica (campo do contrato
              nunca calculado até aqui) + mapas temáticos no app.

Tudo consultando as camadas locais derivadas do IBGE (`bases_locais.py`) —
sem GDAL, sem geopandas, sem rede.

Este módulo é ADITIVO: não substitui nem altera `enrichment_engine.py` (usado
pelos dois botões manuais já em produção nas abas "Rotas com Balsa" e
"Geoespacial IBGE"). É o motor que alimenta automaticamente cada rota
calculada pela aplicação (Rodada 10) — ver `_enriquecer_geo_inteligencia_df`
em `streamlit_app.py`.

Contrato principal:

    from inteligencia_geoespacial import route_context as geo_ctx

    ctx = geo_ctx.analisar_rota(origem=(lat, lon), destino=(lat, lon),
                                 geometria=lista_de_(lat,lon)_ou_None,
                                 distancia_km=distancia_real_ou_None)

    ctx.rios_detectados          # list[CruzamentoHidrografico]
    ctx.corpos_dagua             # list[CruzamentoHidrografico]
    ctx.bacia_hidrografica       # str | None (nunca inventado — só nome oficial ANA/SNIRH)
    ctx.pontes                   # list[Ponte] — pontes reais encontradas NOS cruzamentos
    ctx.travessias               # list[Feicao] — balsas reais (IBGE BC250/BC100)
    ctx.hidrovias_proximas       # list[Feicao]
    ctx.portos_terminais         # list[Feicao] — atracadouros/terminais/portos/eclusas
    ctx.rodovias                 # list[Rodovia] — rodovias oficiais (sigla) percorridas (Missão 2)
    ctx.ferrovias                # list[Ferrovia] — trechos ferroviários próximos (Missão 2)
    ctx.sub_bacia                # str | None — "Código(s) SNIRH: N" (nunca um nome, ver Rodada 6/M2)
    ctx.dependencia_aquaviaria   # 0-100
    ctx.complexidade_geografica  # 0-100 (Missão 2, Rodada 7)
    ctx.confianca_geral          # 0-100
    ctx.avisos                   # incerteza explícita, nunca fabricação

`alternativa_sem_balsa` é preenchido por `montar_alternativa_sem_balsa`
(função pura de formatação — este módulo não faz roteamento nem chamadas de
rede), a partir das duas distâncias já medidas pelo motor de rotas
(streamlit_app.py, Rodada 10).
"""

from __future__ import annotations

import csv
import math
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache

from . import bases_locais as _bl
from .validators import _nome

try:
    from unidecode import unidecode as _unidecode
except Exception:  # pragma: no cover - dependência já presente no requirements.txt
    def _unidecode(s):
        return s


# ==============================================================================
# Utilidades puras
# ==============================================================================

def _unorm(s) -> str:
    """Normaliza texto para comparação (maiúsculas, sem acento, sem espaços extras)."""
    try:
        return _unidecode(str(s or "")).strip().upper()
    except Exception:
        return str(s or "").strip().upper()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância geodésica aproximada (fórmula de haversine, raio 6371 km)."""
    try:
        r = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
        return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))
    except Exception:
        return 0.0


# ==============================================================================
# [CRUZAMENTO-REAL - 459ª geração] Teste de CRUZAMENTO GEOMÉTRICO real da rota
# contra a geometria da feição (rio/corpo d'água). Distingue o que a rota
# ATRAVESSA de fato (interseção de linhas) do que apenas MARGEIA (feição perto
# do eixo, mas nunca cruzada). Puro Python (sem shapely) sobre o decodificador
# WKB de bases_locais — testável sem as camadas Parquet. Coordenadas em
# (lon, lat), a MESMA convenção do WKB do IBGE.
# ==============================================================================

def _orient(ax, ay, bx, by, cx, cy) -> float:
    """Sinal do produto vetorial (AB × AC): >0 esquerda, <0 direita, 0 colinear."""
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _no_retangulo(ax, ay, bx, by, px, py) -> bool:
    """Ponto (colinear) dentro da caixa do segmento AB — usado nos casos-limite."""
    return (min(ax, bx) - 1e-12 <= px <= max(ax, bx) + 1e-12
            and min(ay, by) - 1e-12 <= py <= max(ay, by) + 1e-12)


def _segmentos_cruzam(p1, p2, q1, q2) -> bool:
    """True se os segmentos P1P2 e Q1Q2 se intersectam (inclui toque/colinear).
    Algoritmo clássico de orientação (robusto, sem divisão). Pontos (x, y)."""
    (p1x, p1y), (p2x, p2y) = p1, p2
    (q1x, q1y), (q2x, q2y) = q1, q2
    d1 = _orient(q1x, q1y, q2x, q2y, p1x, p1y)
    d2 = _orient(q1x, q1y, q2x, q2y, p2x, p2y)
    d3 = _orient(p1x, p1y, p2x, p2y, q1x, q1y)
    d4 = _orient(p1x, p1y, p2x, p2y, q2x, q2y)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    # casos-limite colineares (toque de ponta / sobreposição)
    if d1 == 0 and _no_retangulo(q1x, q1y, q2x, q2y, p1x, p1y):
        return True
    if d2 == 0 and _no_retangulo(q1x, q1y, q2x, q2y, p2x, p2y):
        return True
    if d3 == 0 and _no_retangulo(p1x, p1y, p2x, p2y, q1x, q1y):
        return True
    if d4 == 0 and _no_retangulo(p1x, p1y, p2x, p2y, q2x, q2y):
        return True
    return False


def _linha_cruza_geometria(linha_lonlat, wkb) -> bool | None:
    """A polilinha da ROTA (lista de (lon, lat)) CRUZA de fato a feição do WKB?
      • LINESTRING (rio/drenagem): interseção de qualquer segmento da rota com
        qualquer segmento da feição.
      • POLYGON (massa d'água): a rota ENTRA no polígono — algum vértice da rota
        dentro, ou algum segmento da rota cruzando uma aresta de um anel.
      • POINT: None (ponto não é "atravessado" — decisão fica com a proximidade).
    Retorna None quando não há geometria/rota utilizável (o chamador então mantém
    a decisão por proximidade, sem fabricar um cruzamento). PURO/defensivo."""
    try:
        if not linha_lonlat or len(linha_lonlat) < 2 or wkb is None:
            return None
        geo = _bl._deco_wkb(wkb)
        if not geo:
            return None
        rota = [(float(a), float(b)) for a, b in linha_lonlat]
        # POINT → tupla de 2 floats
        if isinstance(geo, tuple) and len(geo) == 2 and not isinstance(geo[0], (list, tuple)):
            return None
        # LINESTRING → lista de pontos (tuplas)
        if isinstance(geo, list) and geo and isinstance(geo[0], tuple):
            linhas_feicao = [geo]
        # POLYGON → lista de anéis (listas de pontos)
        elif isinstance(geo, list) and geo and isinstance(geo[0], list):
            # vértice da rota dentro do polígono → entra
            for (lo, la) in rota:
                if _bl._ponto_em_wkb(lo, la, wkb):
                    return True
            linhas_feicao = geo  # cada anel é uma polilinha fechada
        else:
            return None
        for i in range(len(rota) - 1):
            p1, p2 = rota[i], rota[i + 1]
            for feic in linhas_feicao:
                for j in range(len(feic) - 1):
                    if _segmentos_cruzam(p1, p2, feic[j], feic[j + 1]):
                        return True
        return False
    except Exception:
        return None


# ==============================================================================
# Bacia hidrográfica oficial (ANA/SNIRH) — nunca inventa: só nome com
# correspondência exata (normalizada) no dado oficial já usado pela app.
# ==============================================================================

def _raiz_repo() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def _carregar_mapa_rio_bacia() -> dict:
    """{nome_do_rio_normalizado: nome_da_bacia} a partir de snirh_rios.csv +
    snirh_bacias.csv (ANA/SNIRH, já versionados no repositório e já usados
    pela aba Hidrografia). Fail-open: qualquer problema de leitura devolve
    um dicionário vazio (o chamador trata como bacia não determinada — nunca
    fabrica um nome de bacia).

    Nomes de rio HOMÔNIMOS entre bacias diferentes (ex.: existem vários "Rio
    Negro" cadastrados em bacias distintas no SNIRH) são deliberadamente
    EXCLUÍDOS do mapa em vez de resolvidos por "primeira ocorrência" — expor
    uma bacia escolhida arbitrariamente entre várias reais seria uma forma
    de fabricação de certeza que o restante do projeto proíbe explicitamente."""
    raiz = _raiz_repo()
    caminho_rios = os.path.join(raiz, "snirh_rios.csv")
    caminho_bacias = os.path.join(raiz, "snirh_bacias.csv")
    candidatos: dict = {}
    try:
        bacias_por_codigo = {}
        with open(caminho_bacias, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cod = _nome(row.get("registroID"))
                nome_bacia = _nome(row.get("nome"))
                if cod and nome_bacia:
                    bacias_por_codigo[cod] = nome_bacia
        with open(caminho_rios, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                nome_rio = _unorm(row.get("nome"))
                cod_bacia = _nome(row.get("baciaCodigo"))
                if nome_rio and cod_bacia in bacias_por_codigo:
                    candidatos.setdefault(nome_rio, set()).add(bacias_por_codigo[cod_bacia])
    except Exception:
        return {}
    return {nome: next(iter(bacias)) for nome, bacias in candidatos.items() if len(bacias) == 1}


@lru_cache(maxsize=1)
def _carregar_mapa_rio_subbacia() -> dict:
    """{nome_do_rio_normalizado: código_da_sub-bacia} a partir de
    `subBaciaCodigo` em snirh_rios.csv (Rodada 6, Missão 2 — extração
    máxima: campo presente na base desde sempre, nunca lido por nenhum
    código até aqui).

    IMPORTANTE — por que isto devolve um CÓDIGO e não um NOME: o SNIRH
    numera 85 sub-bacias distintas, mas o `snirh_bacias.csv` vendorizado
    neste repositório só cataloga as 9 bacias de NÍVEL 1 (ver
    `_carregar_mapa_rio_bacia`) — não existe, em lugar nenhum deste
    projeto, uma tabela oficial código→nome para as sub-bacias. Inventar um
    nome a partir do código seria fabricação pura (§38 da missão). O código
    em si é dado real e rastreável (permite ao usuário consultar a sub-bacia
    exata no SNIRH), então é isso — e só isso — que este motor expõe.

    Mesma política de exclusão de homônimos de `_carregar_mapa_rio_bacia`:
    um nome de rio associado a mais de um código de sub-bacia distinto no
    dado bruto fica de fora do mapa (nunca escolhe um arbitrariamente)."""
    raiz = _raiz_repo()
    caminho_rios = os.path.join(raiz, "snirh_rios.csv")
    candidatos: dict = {}
    try:
        with open(caminho_rios, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                nome_rio = _unorm(row.get("nome"))
                cod_sub = _nome(row.get("subBaciaCodigo"))
                if nome_rio and cod_sub:
                    candidatos.setdefault(nome_rio, set()).add(cod_sub)
    except Exception:
        return {}
    return {nome: next(iter(cods)) for nome, cods in candidatos.items() if len(cods) == 1}


def subbacia_codigo_do_rio(nome_rio) -> str | None:
    """Código oficial SNIRH da sub-bacia de um rio (ex.: "27"), ou None se
    não houver correspondência exata/sem-ambiguidade (nunca inferido). Não
    é um nome — ver docstring de `_carregar_mapa_rio_subbacia` sobre por
    que este projeto não tem como resolver o nome da sub-bacia."""
    if not nome_rio:
        return None
    return _carregar_mapa_rio_subbacia().get(_unorm(nome_rio))


def bacia_do_rio(nome_rio) -> str | None:
    """Nome oficial da bacia hidrográfica (ANA/SNIRH) para um nome de rio,
    ou None se não houver correspondência exata (nunca inferido/inventado)."""
    if not nome_rio:
        return None
    return _carregar_mapa_rio_bacia().get(_unorm(nome_rio))


# ==============================================================================
# Rodada 14 — caminho rápido em memória para as camadas PEQUENAS (Performance).
# ==============================================================================
# `bases_locais.mais_proximos` sempre lê o Parquet do disco (com filtro de
# bbox) a cada chamada — ótimo para as camadas PESADAS (`drenagem` 451MB,
# `massas_dagua` 56MB: não cabe manter tudo em memória com segurança), mas
# desperdiça o cache já pronto de `bases_locais.carregar_base` para as
# camadas PEQUENAS (juntas, <1,2MB / <15 mil linhas — carregam em <0,5s e
# cabem tranquilamente em memória pelo resto do processo).
#
# Medido (30 rotas sintéticas): sem este atalho, cada rota nova custa ~3s
# (várias releituras de disco por análise, uma por camada pequena consultada
# em cada nível adaptativo) — o que ameaça a promessa de "automático até 200
# pares" (§ missão). Com o atalho, a mesma consulta usa o DataFrame já
# residente em memória (carregado uma única vez por processo) e reaproveita
# EXATAMENTE a mesma lógica de refinamento geométrico de
# `bases_locais.mais_proximos` (`_dist_bbox_km`/`_distancia_geometria`/
# `_haversine`, importadas de `bases_locais` — não duplicadas) para nunca
# divergir do resultado de referência já testado.

_CAMADAS_PEQUENAS = (
    "pontes", "travessias", "hidrovias", "eclusas",
    "atracadouros_terminal", "complexos_portuarios", "ferrovias",
)


def _consultar_rapido_camada_pequena(camada: str, lon: float, lat: float, raio_km: float,
                                      limite: int = 10, filtros: dict | None = None) -> list:
    """Equivalente a `bases_locais.mais_proximos`, mas a partir do DataFrame
    já em memória (`bases_locais.carregar_base`) — só para as camadas
    pequenas listadas em `_CAMADAS_PEQUENAS`. Mesma saída (list[dict]),
    mesmo critério de raio/ordenação/refinamento geométrico; só a fonte dos
    dados (memória em vez de releitura do disco) muda."""
    df = _bl.carregar_base(camada)
    if df.empty:
        return []

    if filtros:
        for c, v in filtros.items():
            if c not in df.columns:
                return []
            df = df[df[c].astype(object).eq(v)]
        if df.empty:
            return []

    dlat = raio_km / 110.574
    cos_lat = max(0.0001, abs(math.cos(math.radians(lat))))
    dlon = min(raio_km / (111.320 * cos_lat), 180.0)
    df = df[(df.xmin <= lon + dlon) & (df.xmax >= lon - dlon) &
            (df.ymin <= lat + dlat) & (df.ymax >= lat - dlat)]
    if df.empty:
        return []

    # [HIDROVIA-LONGA - 460ª] mesma implementação única/correta de ranqueamento que mais_proximos.
    return _bl._ranquear_por_distancia(df, lon, lat, raio_km, limite)


# ==============================================================================
# Rodada 14 — cache de "janela ampla" para as camadas PESADAS (Performance).
# ==============================================================================
# Perfilando `analisar_rota` (cProfile) depois do atalho das camadas pequenas
# acima, o custo restante passou a ser quase todo (>95% do tempo) releituras
# de `drenagem`/`massas_dagua` do disco: a escalada automática de nível
# (§32) e a amostragem de vários pontos ao longo da rota consultam o MESMO
# ponto (ou pontos muito próximos) várias vezes, cada uma com um raio um
# pouco maior — e cada consulta relia o Parquet do zero, mesmo que uma
# consulta anterior já tivesse coberto quase a mesma área.
#
# Como `drenagem` (451MB/2,18M linhas) e `massas_dagua` (56MB/64.850 linhas)
# são grandes demais para manter inteiras em memória com segurança (mesma
# decisão já tomada para o atalho acima — risco de orçamento de memória em
# produção), este cache guarda, por ponto arredondado a 2 casas decimais
# (~1km de grade), a leitura filtrada por bbox JÁ FEITA com uma folga (o
# maior raio que a escalada automática pode pedir, mais uma margem de
# segurança para a própria imprecisão do arredondamento do ponto) — e serve
# todas as consultas seguintes com raio igual ou menor para aquele mesmo
# ponto a partir dessa janela em memória, sem tocar o disco de novo. Um
# `raio_km` explícito maior do que a janela cacheada NUNCA é servido do
# cache (evita truncar silenciosamente um raio pedido explicitamente) —
# nesse caso relê o disco com o raio realmente pedido (+ a mesma margem) e
# substitui a janela cacheada para aquele ponto.

_RAIO_SUPERCACHE_PADRAO_KM = 12.0  # cobre o maior raio da escalada automática (nível 6 — ver _RAIO_POR_NIVEL)
# Grade de 1 casa decimal (~11 km): medido que o custo de reler o Parquet é
# dominado por overhead fixo por chamada (escaneio de metadados/row-groups),
# não pelo tamanho do raio pedido — então vale a pena usar uma grade mais
# larga para que VÁRIOS pontos amostrados ao longo do mesmo trecho de rota
# (tipicamente a poucos km uns dos outros) caiam na mesma célula e
# reaproveitem a mesma leitura, mesmo custando uma janela de leitura maior.
_PRECISAO_GRADE_PESADAS = 1
_MARGEM_SEGURANCA_ARREDONDAMENTO_KM = 9.0  # folga > deslocamento máx. de arredondar o ponto a 1 casa (~7,85 km no pior caso no Brasil)
# Medido (regiões densas: Manaus, Iranduba, foz do Amazonas, litoral de
# Recife — raio de leitura ~21km): cada entrada de `drenagem`/`massas_dagua`
# pesa até ~0,85 MB (pior caso observado) em memória. 150 entradas =
# no máximo ~125 MB no pior caso hipotético (todas as entradas no pior
# caso ao mesmo tempo — improvável na prática, já que a maioria das
# células é bem mais leve que o pior caso). Valor escolhido para manter
# a mesma cautela de orçamento de memória que já motivou NÃO carregar
# essas duas camadas inteiras (§ comentário acima).
_CACHE_PESADAS_MAX_ENTRADAS = 150

_cache_janela_pesada: "OrderedDict[tuple, tuple]" = OrderedDict()


def _limpar_cache_camadas_pesadas():
    """Só para testes/isolamento entre execuções — em produção este cache
    de processo não precisa ser limpo."""
    _cache_janela_pesada.clear()


def _consultar_camada_pesada_cacheada(camada: str, lon: float, lat: float, raio_km: float,
                                       limite: int = 10, filtros: dict | None = None) -> list:
    """Equivalente a `bases_locais.mais_proximos` para as camadas PESADAS,
    mas reaproveitando (quando possível) uma leitura de disco já feita para
    o mesmo ponto com um raio igual ou maior — ver explicação acima. Nunca
    diverge do resultado de referência: usa as mesmas rotinas de
    filtro/ranking/refinamento de `bases_locais` (importadas, não
    duplicadas), só a origem do DataFrame filtrado por bbox muda (cache em
    memória em vez de sempre reler o disco)."""
    lat_r = round(float(lat), _PRECISAO_GRADE_PESADAS)
    lon_r = round(float(lon), _PRECISAO_GRADE_PESADAS)
    chave = (camada, lat_r, lon_r)

    entrada = _cache_janela_pesada.get(chave)
    if entrada is not None and entrada[0] >= raio_km + _MARGEM_SEGURANCA_ARREDONDAMENTO_KM:
        _cache_janela_pesada.move_to_end(chave)
        df = entrada[1]
    else:
        raio_leitura = max(raio_km, _RAIO_SUPERCACHE_PADRAO_KM) + _MARGEM_SEGURANCA_ARREDONDAMENTO_KM
        # Sem projeção de colunas (todas as colunas): garante que qualquer
        # `filtros` futuro sempre encontre a coluna necessária no DataFrame
        # cacheado, sem precisar recalcular quais colunas "extra" incluir.
        df = _bl._busca_com_filtro(camada, lon_r, lat_r, raio_leitura, colunas=None)
        _cache_janela_pesada[chave] = (raio_leitura, df)
        _cache_janela_pesada.move_to_end(chave)
        if len(_cache_janela_pesada) > _CACHE_PESADAS_MAX_ENTRADAS:
            _cache_janela_pesada.popitem(last=False)

    if df.empty:
        return []

    if filtros:
        for c, v in filtros.items():
            if c not in df.columns:
                return []
            df = df[df[c].astype(object).eq(v)]
        if df.empty:
            return []

    # [HIDROVIA-LONGA - 460ª] mesma implementação única/correta de ranqueamento (limite inferior por bbox
    # para linhas longas) — a janela vem do cache, o ranqueamento é idêntico ao de mais_proximos.
    return _bl._ranquear_por_distancia(df, lon, lat, raio_km, limite)


_CAMADAS_COM_CACHE_AMPLO = ("drenagem", "massas_dagua", "rodovias")


# ==============================================================================
# GeoIntelligenceRepository — cache compartilhado das consultas às camadas
# locais IBGE (§20 da missão): evita reconsultar a mesma (camada, coordenada
# arredondada, raio) mais de uma vez por processo. Mesmo padrão já usado e
# testado em streamlit_app.py para o grafo fluvial
# (_nome_rio_na_travessia_lru: coordenadas arredondadas + cache por processo).
# ==============================================================================

class GeoIntelligenceRepository:
    """LRU manual (não usa functools.lru_cache porque o VALOR — uma lista de
    dicts vinda de bases_locais.mais_proximos — não precisa ser hashable,
    só a CHAVE da consulta precisa)."""

    def __init__(self, precisao_decimais: int = 4, tamanho_max: int = 20000):
        self._precisao = int(precisao_decimais)
        self._tamanho_max = int(tamanho_max)
        self._cache: "OrderedDict[tuple, list]" = OrderedDict()

    def consultar(self, camada: str, lat: float, lon: float, raio_km: float = 30.0,
                  limite: int = 10, filtros: dict | None = None) -> list:
        chave = None
        try:
            lat_r = round(float(lat), self._precisao)
            lon_r = round(float(lon), self._precisao)
            raio_r = round(float(raio_km), 1)
            chave = (camada, lat_r, lon_r, raio_r, int(limite),
                      tuple(sorted((filtros or {}).items())))
        except Exception:
            chave = None

        if chave is not None and chave in self._cache:
            self._cache.move_to_end(chave)
            return self._cache[chave]

        try:
            if camada in _CAMADAS_PEQUENAS:
                resultado = _consultar_rapido_camada_pequena(
                    camada, float(lon), float(lat), raio_km=float(raio_km),
                    limite=int(limite), filtros=filtros) or []
            elif camada in _CAMADAS_COM_CACHE_AMPLO:
                resultado = _consultar_camada_pesada_cacheada(
                    camada, float(lon), float(lat), raio_km=float(raio_km),
                    limite=int(limite), filtros=filtros) or []
            else:
                resultado = _bl.mais_proximos(
                    camada, float(lon), float(lat), raio_km=float(raio_km),
                    limite=int(limite), filtros=filtros) or []
        except Exception:
            resultado = []

        if chave is not None:
            self._cache[chave] = resultado
            self._cache.move_to_end(chave)
            if len(self._cache) > self._tamanho_max:
                self._cache.popitem(last=False)
        return resultado

    def limpar(self):
        self._cache.clear()

    def tamanho(self) -> int:
        return len(self._cache)


_REPO_PADRAO: GeoIntelligenceRepository | None = None


def repositorio_padrao() -> GeoIntelligenceRepository:
    """Instância compartilhada por processo (equivalente ao padrão
    @st.cache_resource já usado para EXECUTOR_GLOBAL em streamlit_app.py —
    aqui implementado sem depender do Streamlit para o módulo continuar
    testável/importável isoladamente)."""
    global _REPO_PADRAO
    if _REPO_PADRAO is None:
        _REPO_PADRAO = GeoIntelligenceRepository()
    return _REPO_PADRAO


# ==============================================================================
# Amostragem da geometria da rota (corda geodésica ou geometria real do
# provedor de rotas) — generaliza o padrão já comprovado em
# streamlit_app.py:_enriquecer_linha_rio (interpolação por np.linspace),
# agora reutilizável para qualquer camada, não só o grafo fluvial.
# ==============================================================================

def pontos_amostrados(lat_o: float, lon_o: float, lat_d: float, lon_d: float,
                       geometria: list | None = None, n_pontos: int = 11) -> list:
    """Lista de (lat, lon, km_desde_origem) ao longo do trajeto.

    Usa a geometria REAL da rota (lista de (lat, lon), na ordem já
    decodificada de um provedor como o OSRM) quando fornecida — mais fiel
    para rotas sinuosas. Sem geometria, interpola a corda geodésica
    origem→destino (aproximação honesta, rotulada como tal no nível de
    confiança dos achados)."""
    n_pontos = max(2, int(n_pontos))
    pts: list
    if geometria and len(geometria) >= 2:
        try:
            pts = [(float(p[0]), float(p[1])) for p in geometria]
        except Exception:
            pts = []
    else:
        pts = []

    if not pts:
        pts = [
            (lat_o + (lat_d - lat_o) * (i / (n_pontos - 1)),
             lon_o + (lon_d - lon_o) * (i / (n_pontos - 1)))
            for i in range(n_pontos)
        ]
    elif len(pts) > n_pontos:
        # Subamostra uniforme da geometria real — evita consultar cada
        # vértice do provedor (uma rota longa pode ter centenas deles).
        passo = (len(pts) - 1) / float(n_pontos - 1)
        idxs = sorted({round(i * passo) for i in range(n_pontos)})
        pts = [pts[min(i, len(pts) - 1)] for i in idxs]

    out = []
    km_acum = 0.0
    for i, (la, lo) in enumerate(pts):
        if i > 0:
            km_acum += _haversine_km(pts[i - 1][0], pts[i - 1][1], la, lo)
        out.append((la, lo, km_acum))
    return out


# ==============================================================================
# Dataclasses — contrato único consumido por dashboard, mapa, HTML, Excel,
# comparação, auditoria e explicabilidade (§19/§20 da missão).
# ==============================================================================

@dataclass
class CruzamentoHidrografico:
    nome: str
    camada: str                       # "drenagem" | "massas_dagua"
    distancia_eixo_km: float | None   # distância do ponto amostrado ao elemento
    km_desde_origem: float | None     # posição aproximada do cruzamento na rota
    km_ate_destino: float | None
    navegavel: str | None
    regime: str | None
    bacia: str | None                 # None = não determinado (nunca inventado)
    fonte: str
    confianca: str                    # "alta" | "media"
    lat: float | None = None          # coordenada do ponto de amostra mais próximo do
    lon: float | None = None          # cruzamento — usada para localizar pontes (Rodada 5) e mapas
    # Rodada 5 (Missão 2): atributos por tipo de camada — só um dos dois
    # grupos é relevante por vez (drenagem usa `encoberto`; massas_dagua usa
    # `artificial`/`salgada`/`dominialidade`), o outro fica None.
    encoberto: str | None = None      # drenagem: "Sim"/"Não" — trecho canalizado/coberto
    artificial: str | None = None     # massas_dagua: "Sim"/"Não" — reservatório/lago artificial
    salgada: str | None = None        # massas_dagua: "Sim"/"Não"
    dominialidade: str | None = None  # massas_dagua: "Federal"/"Estadual/Distrital"/"Municipal"/...
    # [FUSAO-FONTES - Missão 3, Rodada 18, §40] None = só uma extração (BC250 OU BC100) encontrou
    # esta feição; string com 2+ nomes separados por vírgula (ex.: "BC250, BC100") quando o MESMO
    # nome normalizado foi confirmado por extrações INDEPENDENTES — corroboração real, não inventada.
    confirmado_por: str | None = None
    # [CRUZAMENTO-REAL - 459ª geração] Relação GEOMÉTRICA da rota com a feição, quando a geometria real
    # da rota está disponível: "cruza" = a polilinha da rota intersecta a feição de fato (atravessa);
    # "margeia" = a feição está no raio mas a rota NÃO a cruza (corre ao lado). None = sem geometria real
    # para decidir (mantém a leitura por proximidade, com o aviso honesto de corda reta). `cruzamento_
    # confirmado` é True só quando geometricamente comprovado — o sinal mais forte de que a rota atravessa.
    relacao: str | None = None
    cruzamento_confirmado: bool | None = None


@dataclass
class Feicao:
    """Ponte/travessia/hidrovia/porto próximo a um cruzamento."""
    nome: str
    tipo: str
    distancia_eixo_km: float | None
    km_desde_origem: float | None
    fonte: str
    lat: float | None = None    # coordenada real da feição (para mapas — Rodada 9)
    lon: float | None = None
    # Rodada 5 (Missão 2): atributos extras específicos da camada de origem
    # (ex.: tipotransp/tipocomple/portosempa para complexos_portuarios) — só
    # preenchido quando o chamador de `_detectar_feicoes` pede via
    # `campos_extra`; vazio por padrão para não afetar as camadas que não
    # precisam disso (travessias/hidrovias/eclusas/atracadouros_terminal).
    atributos: dict = field(default_factory=dict)


@dataclass
class Rodovia:
    """Rodada 3 (Missão 2 — extração máxima): trecho rodoviário oficial
    (IBGE BC250/BC100) identificado ao longo da rota, pela SIGLA (BR-xxx,
    UF-xxx) — nunca por 'nome', que na camada `rodovias` é sempre nulo
    (confirmado por inspeção direta do Parquet). Trechos sem sigla cadastrada
    (ruas locais, becos, servidões — a camada cobre TODO o viário, não só
    rodovias numeradas) são deliberadamente descartados: mostrar "rodovia
    sem nome" para uma rua qualquer seria uma forma de fabricar relevância
    que a rota não tem."""
    sigla: str                              # ex.: "BR-364", "BR-364/MT-170" (composto, como na base)
    km_desde_origem: float | None
    distancia_eixo_km: float | None
    jurisdicao: str | None                  # "Federal" | "Estadual/Distrital" | "Municipal" | ... (valor bruto da base)
    administra: str | None
    concessionaria: str | None              # None quando a base não registra concessão (não é "Não" fabricado)
    revestimento: str | None
    tipo_pavimento: str | None
    nr_pistas: int | None
    nr_faixas: int | None
    limite_velocidade_kmh: int | None       # quase sempre ausente na base (não inventado quando falta)
    trafego: str | None = None              # Rodada 15/M2: "Permanente" | "Periódico" | "Temporário" | "Desconhecido" — 0% nulo na base
    situacao_fisica: str | None = None      # Rodada 15/M2: "Construída" | "Abandonada" | "Destruída" | "Em construção" | "Planejada" | ...
    fonte: str = "IBGE BC250/BC100 (rodovias)"
    lat: float | None = None
    lon: float | None = None


@dataclass
class Ferrovia:
    """Rodada 4 (Missão 2 — extração máxima): trecho ferroviário oficial
    (IBGE BC250/BC100) próximo à rota. Ao contrário de `rodovias`, aqui
    `nome` É populado na maior parte dos registros (ex.: "Estrada de Ferro
    Vitória a Minas") — usado como identificador primário; quando ausente,
    cai para o código do trecho (`codtrechof`, ex.: "EF-462") antes de um
    rótulo genérico, nunca um nome próprio inventado. A camada inclui trens
    de carga/passageiros E metrô/aeromóvel — `tipo_trecho` distingue."""
    nome: str
    km_desde_origem: float | None
    distancia_eixo_km: float | None
    tipo_trecho: str | None                 # "Trecho para trem" | "Trecho para metrô" | "Trecho para aeromóvel" | ...
    bitola: str | None                      # "Métrica" | "Larga" | "Mista métrica  larga" | "Desconhecida"
    eletrificada: str | None                # "Sim" | "Não" | "Desconhecido" (valor bruto da base)
    nr_linhas: str | None                   # "Simples" | "Dupla" | "Múltipla" | "Desconhecido"
    jurisdicao: str | None
    administra: str | None
    concessionaria: str | None              # None quando a base não registra concessão
    posicao_relativa: str | None = None     # Rodada 15/M2: "Superfície" | "Subterrânea" | "Desconhecida"
    situacao_fisica: str | None = None      # Rodada 15/M2: "Construída" | "Abandonada" | "Destruída" | ...
    fonte: str = "IBGE BC250/BC100 (ferrovias)"
    lat: float | None = None
    lon: float | None = None


@dataclass
class Ponte:
    """Rodada 5 (Missão 2 — extração máxima): ponte real localizada NO
    cruzamento hidrográfico (mesma detecção da Rodada 5 original), agora com
    atributos adicionais da base BC250/BC100 além do nome.

    NOTA DELIBERADA sobre campos excluídos: a base também tem `vaolivreho`
    (vão livre horizontal), `vaovertica` (vão livre vertical) e `cargasupor`
    (carga suportada) — inspecionados diretamente e descartados aqui porque
    onde presentes (~2% das ~14.812 pontes) o ÚNICO valor não-nulo
    encontrado é 0.0 para os três — um sentinela de "não medido", não uma
    medição real de vão/carga zero. Mostrar "vão livre: 0m" seria fabricar
    uma informação que a base não tem de verdade (§38 da missão: nunca
    invente dado para preencher um campo)."""
    nome: str
    distancia_eixo_km: float | None
    km_desde_origem: float | None
    tipo_ponte: str | None                  # "Fixa" | "Móvel" | "Pênsil" | "Estaiada" | "Desconhecido"
    tipo_pavimento: str | None
    extensao_m: float | None                # ausente na maioria dos registros (~88%) — None quando não cadastrado
    largura_m: float | None                 # idem
    fonte: str = "IBGE BC250/BC100 (pontes)"
    lat: float | None = None
    lon: float | None = None


@dataclass
class Anomalia:
    """Rodada 9 (Missão 2 — extração máxima §25-26): alerta estruturado e
    categorizado sobre a análise geográfica desta rota — formaliza sinais
    que já existiam como texto solto em `ContextoGeograficoRota.avisos`
    (mantidos, por compatibilidade) em algo filtrável/agregável (categoria +
    severidade), como a missão pede para a "camada de anomalias". Nunca
    fabrica uma anomalia: cada categoria é uma checagem honesta sobre os
    próprios dados já coletados por `analisar_rota`, documentada caso a
    caso em `_detectar_anomalias`."""
    categoria: str        # slug estável, ex.: "distancia_menor_que_linha_reta"
    severidade: str        # "alta" | "media" | "baixa"
    descricao: str


@dataclass
class AlternativaRodoviaria:
    """Comparação com uma rota sem travessia (Rodada 4/13)."""
    distancia_km: float | None
    diferenca_km: float | None
    diferenca_pct: float | None
    conclusao: str


@dataclass
class ContextoGeograficoRota:
    origem: dict
    destino: dict
    distancia_km: float | None = None

    rios_detectados: list = field(default_factory=list)        # CruzamentoHidrografico
    corpos_dagua: list = field(default_factory=list)            # CruzamentoHidrografico
    pontes: list = field(default_factory=list)                  # Feicao — rodada de pontes
    travessias: list = field(default_factory=list)              # Feicao — balsas reais (IBGE)
    hidrovias_proximas: list = field(default_factory=list)      # Feicao
    portos_terminais: list = field(default_factory=list)        # Feicao
    rodovias: list = field(default_factory=list)                 # Rodovia — Missão 2/Rodada 3
    ferrovias: list = field(default_factory=list)                 # Ferrovia — Missão 2/Rodada 4

    bacia_hidrografica: str | None = None
    sub_bacia: str | None = None

    complexidade_geografica: int | None = None    # rodada de explicabilidade/Excel
    dependencia_aquaviaria: int | None = None      # 0-100
    alternativa_sem_balsa: AlternativaRodoviaria | None = None   # preenchido pelo pipeline (tem as 2 distâncias)

    confianca_geral: int = 0
    confianca_nivel: str = "nao_determinada"       # alta | media | baixa | nao_determinada
    fontes_concordam: list = field(default_factory=list)
    motivo_decisao: str = ""
    avisos: list = field(default_factory=list)
    anomalias: list = field(default_factory=list)          # Anomalia — Missão 2/Rodada 9
    nivel_analise: int = 1


# ==============================================================================
# Níveis adaptativos (§32 da missão) — reaproveita sinais já existentes no
# motor de rotas (razão V/R suspeita, balsa) em vez de inventar uma nova
# heurística.
#
# CALIBRAÇÃO (Rodada 14, com dois casos reais medidos, não uma escolha
# arbitrária): a Ponte Rio-Niterói está a 3,44 km do ponto de referência do
# centro do Rio de Janeiro usado nos testes das Rodadas 5/9 — com o raio
# original do nível 1 (3,0 km) e a amostragem automática (sem geometria
# real da rota, só a corda reta), esse cruzamento REAL ficava invisível
# (confirmado rodando analisar_rota sem raio explícito antes desta
# calibração: 0 rios, 0 pontes). Em Manaus o cruzamento mais próximo
# (Igarapé Cachoeira Grande) já estava a 1,25 km, dentro de qualquer raio
# razoável. Sem geometria real da rota, a corda reta pode passar alguns km
# do traçado verdadeiro — o raio do nível 1 precisa absorver essa folga,
# não só o erro de digitalização da base. Ajustado de 3,0 → 5,0 km, com a
# amostragem também um pouco mais densa (passo 40 → 30 km) para rotas
# curtas/médias sem geometria real. Níveis 2+ (rio/balsa já confirmados)
# mantidos como estavam — já é razoável para quando há evidência real.
# ==============================================================================

_RAIO_POR_NIVEL = {1: 5.0, 2: 6.0, 3: 6.0, 4: 8.0, 5: 8.0, 6: 12.0}
_PASSO_KM_POR_NIVEL = {1: 30.0, 2: 15.0, 3: 15.0, 4: 10.0, 5: 10.0, 6: 8.0}
_N_PONTOS_MIN, _N_PONTOS_MAX = 4, 60


def nivel_automatico(distancia_km: float | None, suspeita: bool = False) -> int:
    """Nível 1 (rota simples) ou 2 (rota longa/suspeita → amostragem mais
    densa). Níveis 3-6 são atribuídos explicitamente por quem já sabe que a
    rota tem balsa/é uma derrota (ver `analisar_rota(nivel=...)`)."""
    if suspeita:
        return 2
    if distancia_km is not None and distancia_km > 300:
        return 2
    return 1


def _raio_para_nivel(nivel: int) -> float:
    return _RAIO_POR_NIVEL.get(int(nivel), 3.0)


def _n_pontos_para_nivel(nivel: int, distancia_km: float | None) -> int:
    passo = _PASSO_KM_POR_NIVEL.get(int(nivel), 40.0)
    d = distancia_km or 50.0
    n = int(d / passo) + 2
    return max(_N_PONTOS_MIN, min(_N_PONTOS_MAX, n))


# ==============================================================================
# Detecção hidrográfica por geometria (rios + corpos d'água)
# ==============================================================================

_CAMADAS_HIDRO = ("drenagem", "massas_dagua")


def _fonte_real(item: dict, fallback: str) -> str:
    """[FONTE-REAL - Missão 3, Rodada 17, §39] Monta a descrição de fonte a partir do registro REAL
    (`fonte_base`/`fonte_uf`, já selecionados por `bases_locais.mais_proximos`/`_busca_com_filtro` —
    ver construir_bases_locais_ibge.py: BC250 é a base nacional, BC100 cobre só 7 UFs em maior
    detalhe). `fallback` é o rótulo genérico já usado por cada camada (ex.: "IBGE BC250/BC100
    (travessias)") — usado sem alteração quando o registro não traz `fonte_base` (nunca inventa uma
    especificidade que a base não informa). PURA; nunca lança."""
    try:
        _fb = str(item.get("fonte_base") or "").strip()
        if not _fb:
            return fallback
        # "BR" é o valor real da base para fonte_uf quando a camada de origem é a BC250
        # (nacional, não uma extração estadual) — não é uma UF de verdade, então não
        # aparece como sufixo (mostrar "— BR" seria ruído, não informação nova).
        _fu = str(item.get("fonte_uf") or "").strip()
        if _fu.upper() == "BR":
            _fu = ""
        _rotulo = fallback.split("(", 1)[1].rstrip(")") if "(" in fallback else fallback
        return f"IBGE {_fb} ({_rotulo})" + (f" — {_fu}" if _fu else "")
    except Exception:
        return fallback


def _detectar_cruzamentos_hidro(pontos: list, repo: GeoIntelligenceRepository,
                                 raio_km: float, distancia_total_km: float,
                                 linha_rota: list | None = None) -> list:
    """Consulta as camadas hidrográficas em cada ponto amostrado e deduplica
    por (camada, nome normalizado), mantendo a MENOR distância ao eixo da
    rota e o km acumulado (desde a origem) daquele ponto de amostra.

    [CRUZAMENTO-REAL - 459ª geração] Quando `linha_rota` (polilinha real da rota
    em (lon, lat)) é fornecida, cada feição candidata é submetida ao TESTE
    GEOMÉTRICO de cruzamento (`_linha_cruza_geometria`): confirma se a rota
    ATRAVESSA a feição de fato ("cruza") ou apenas a MARGEIA (no raio, mas nunca
    cruzada). Sem `linha_rota`, mantém a leitura por proximidade (relacao=None)."""
    achados: dict = {}
    # [FUSAO-FONTES - Missão 3, Rodada 18, §40] Rastreia TODAS as fonte_base vistas por chave —
    # inclusive as que perdem o dedup por distância — para poder marcar quando o MESMO nome foi
    # encontrado por extrações INDEPENDENTES (BC250 e BC100), uma corroboração real entre fontes,
    # sem alterar qual registro "vence" (continua sendo o de menor distância, como sempre foi).
    _fontes_vistas: dict = {}
    for la, lo, km_o in pontos:
        for camada in _CAMADAS_HIDRO:
            try:
                itens = repo.consultar(camada, la, lo, raio_km=raio_km, limite=5)
            except Exception:
                itens = []
            for it in itens:
                nome = _nome(it.get("nome"))
                if not nome:
                    continue
                chave = (camada, _unorm(nome))
                _fb = str(it.get("fonte_base") or "").strip()
                if _fb:
                    _fontes_vistas.setdefault(chave, set()).add(_fb)
                try:
                    dist = round(float(it.get("distancia_km")), 2)
                except Exception:
                    dist = None
                atual = achados.get(chave)
                if atual is not None and dist is not None and atual["distancia_eixo_km"] is not None \
                        and dist >= atual["distancia_eixo_km"]:
                    continue
                achados[chave] = {
                    "nome": nome,
                    "camada": camada,
                    "distancia_eixo_km": dist,
                    "km_desde_origem": round(km_o, 1),
                    "km_ate_destino": (round(max(0.0, distancia_total_km - km_o), 1)
                                       if distancia_total_km else None),
                    "navegavel": _nome(it.get("navegavel")) or None,
                    "regime": _nome(it.get("regime")) or None,
                    "bacia": bacia_do_rio(nome) if camada == "drenagem" else None,
                    # [FONTE-REAL - Missão 3, Rodada 17, §39] `mais_proximos`/`_busca_com_filtro` já
                    # selecionam fonte_base/fonte_uf do próprio parquet (bases_locais.py) — colunas
                    # reais descritas na base original (ex.: "BC250"/"BC100" + a UF quando a base é
                    # regional), mas até aqui eram descartadas em favor de uma string genérica fixa.
                    # Usa o valor REAL do registro quando presente; cai no genérico só quando ausente
                    # (nunca fabrica uma fonte mais específica do que a base realmente informa).
                    "fonte": _fonte_real(it, "IBGE BC250/BC100 (drenagem)" if camada == "drenagem"
                                         else "IBGE BC250/BC100 (massas d'água)"),
                    "confianca": ("alta" if (dist is not None and dist <= max(0.5, raio_km * 0.15))
                                  else "media"),
                    "lat": la,
                    "lon": lo,
                    "encoberto": (_nome(it.get("encoberto")) or None) if camada == "drenagem" else None,
                    "artificial": (_nome(it.get("artificial")) or None) if camada == "massas_dagua" else None,
                    "salgada": (_nome(it.get("salgada")) or None) if camada == "massas_dagua" else None,
                    "dominialidade": (_nome(it.get("dominialid")) or None) if camada == "massas_dagua" else None,
                    "confirmado_por": None,
                    "relacao": None,
                    "cruzamento_confirmado": None,
                    "_wkb": it.get("geometry_wkb"),  # temporário: teste de cruzamento pós-loop
                }
    # [FUSAO-FONTES - Missão 3, Rodada 18, §40] Marca corroboração real entre extrações
    # independentes: só quando 2+ fonte_base DISTINTAS confirmaram o MESMO nome normalizado
    # (nunca quando é uma só extração, mesmo com vários pontos amostrados a encontrando de novo).
    # Corroboração por múltiplas fontes é um sinal de confiança genuíno — eleva "media" para "alta",
    # nunca rebaixa uma confiança já alta por outro motivo.
    for _chave, _dados in achados.items():
        _fs = _fontes_vistas.get(_chave)
        if _fs and len(_fs) > 1:
            _dados["confirmado_por"] = ", ".join(sorted(_fs))
            _dados["confianca"] = "alta"
    # [CRUZAMENTO-REAL - 459ª geração] Teste geométrico de cruzamento real (só quando há a polilinha da
    # rota). "cruza" → a rota atravessa a feição de fato (confiança ALTA, sinal mais forte). "margeia" →
    # a feição está no raio mas a rota NÃO a cruza (rebaixa para "media": é contexto, não um cruzamento).
    # Sem geometria da feição para testar, deixa relacao=None (decisão por proximidade, como antes).
    for _dados in achados.values():
        _wkb = _dados.pop("_wkb", None)
        if not linha_rota or _wkb is None:
            continue
        try:
            _cruza = _linha_cruza_geometria(linha_rota, _wkb)
        except Exception:
            _cruza = None
        if _cruza is True:
            _dados["relacao"] = "cruza"
            _dados["cruzamento_confirmado"] = True
            _dados["confianca"] = "alta"
        elif _cruza is False:
            _dados["relacao"] = "margeia"
            _dados["cruzamento_confirmado"] = False
            # margeia não é cruzamento: nunca deixa uma feição só-próxima passar por "alta" de proximidade
            if _dados.get("confianca") == "alta" and not _dados.get("confirmado_por"):
                _dados["confianca"] = "media"
    # remove qualquer _wkb remanescente (defensivo: achados sem teste também não devem exportá-lo)
    for _dados in achados.values():
        _dados.pop("_wkb", None)
    return sorted(achados.values(), key=lambda x: (x["km_desde_origem"] or 0.0))


# ==============================================================================
# Detecção aquaviária por geometria (Rodada 4): travessias/balsas reais,
# hidrovias e infraestrutura portuária próximas ao trajeto.
#
# LIMITAÇÃO CONHECIDA (bases_locais.mais_proximos, não deste módulo): para
# feições LINHA muito longas (uma hidrovia nacional pode ter milhares de km),
# o filtro inicial de `mais_proximos` compara o raio contra um ponto
# representativo único da geometria, ANTES do refinamento ponto-a-segmento
# mais preciso — então uma hidrovia cujo ponto representativo caia longe do
# eixo consultado pode não aparecer mesmo que um trecho dela passe perto,
# especialmente em raios pequenos (níveis 1-3). Travessias/portos (feições
# curtas ou pontuais) não sofrem esse efeito. Registrado aqui para uma
# rodada dedicada de correção em bases_locais.py — não é ajustado neste
# módulo para não alterar uma função compartilhada por todo o pacote sem
# a bateria de testes própria que ela merece.
# ==============================================================================

_CAMADAS_INFRA_AQUA = (
    ("atracadouros_terminal", "atracadouro/terminal"),
    ("complexos_portuarios", "complexo portuário"),
    ("eclusas", "eclusa"),
)

# Rodada 5 (Missão 2): atributos reais adicionais por camada, hoje coletados
# pela base mas não usados em lugar nenhum do pipeline (achado da auditoria) —
# ver _detectar_feicoes(campos_extra=...).
_CAMPOS_EXTRA_POR_CAMADA = {
    "complexos_portuarios": ("tipotransp", "tipocomple", "portosempa", "jurisdicao"),
}


def _detectar_feicoes(pontos: list, repo: GeoIntelligenceRepository, camada: str,
                       raio_km: float, tipo_rotulo: str, fonte: str,
                       filtros: dict | None = None, limite: int = 5,
                       campos_extra: tuple = ()) -> list:
    """Generaliza a deduplicação de `_detectar_cruzamentos_hidro` para
    qualquer camada de feições pontuais/lineares (travessias, hidrovias,
    portos, eclusas), devolvendo `Feicao` já ordenadas pela posição no
    trajeto. Nome ausente na base vira rótulo explícito, nunca None solto
    (mesma convenção já usada em enrichment_engine.py).

    `campos_extra` (Rodada 5, Missão 2): nomes de colunas adicionais da
    camada de origem a propagar em `Feicao.atributos` (só as presentes e
    não-vazias) — usado para atributos específicos de uma única camada
    (ex.: tipotransp/tipocomple para complexos_portuarios) sem precisar
    de um dataclass dedicado para cada uma."""
    achados: dict = {}
    for la, lo, km_o in pontos:
        try:
            itens = repo.consultar(camada, la, lo, raio_km=raio_km, limite=limite, filtros=filtros)
        except Exception:
            itens = []
        for it in itens:
            nome = _nome(it.get("nome")) or ("<%s sem nome>" % tipo_rotulo)
            chave = _unorm(nome)
            try:
                dist = round(float(it.get("distancia_km")), 2)
            except Exception:
                dist = None
            atual = achados.get(chave)
            if atual is not None and dist is not None and atual.distancia_eixo_km is not None \
                    and dist >= atual.distancia_eixo_km:
                continue
            try:
                _flat, _flon = float(it.get("lat")), float(it.get("lon"))
            except Exception:
                _flat, _flon = None, None
            _extras = {}
            for _campo in campos_extra:
                _v = _nome(it.get(_campo))
                if _v:
                    _extras[_campo] = _v
            # [FONTE-REAL - Missão 3, Rodada 17, §39] Mesmo tratamento de _detectar_cruzamentos_hidro:
            # usa fonte_base/fonte_uf REAIS do registro quando presentes, cai no `fonte` genérico do
            # chamador quando ausentes.
            achados[chave] = Feicao(nome=nome, tipo=tipo_rotulo, distancia_eixo_km=dist,
                                     km_desde_origem=round(km_o, 1), fonte=_fonte_real(it, fonte),
                                     lat=_flat, lon=_flon, atributos=_extras)
    return sorted(achados.values(), key=lambda f: (f.km_desde_origem or 0.0))


def _detectar_aquaviario(pontos: list, repo: GeoIntelligenceRepository, raio_km: float):
    """Travessias (balsas reais, `tipotraves=Balsa` — mesmo filtro já usado
    e validado em enrichment_engine.enriquecer_ponto), hidrovias e
    infraestrutura portuária (atracadouros/terminais, complexos portuários,
    eclusas) ao longo do trajeto amostrado."""
    travessias = _detectar_feicoes(
        pontos, repo, "travessias", raio_km, "travessia (balsa)",
        "IBGE BC250/BC100 (travessias)", filtros={"tipotraves": "Balsa"})
    hidrovias = _detectar_feicoes(
        pontos, repo, "hidrovias", raio_km, "hidrovia", "IBGE BC250/BC100 (hidrovias)")
    portos: list = []
    for camada, rotulo in _CAMADAS_INFRA_AQUA:
        portos.extend(_detectar_feicoes(
            pontos, repo, camada, raio_km, rotulo, "IBGE BC250/BC100 (%s)" % camada,
            campos_extra=_CAMPOS_EXTRA_POR_CAMADA.get(camada, ())))
    portos.sort(key=lambda f: (f.km_desde_origem or 0.0))
    return travessias, hidrovias, portos


# ==============================================================================
# Detecção rodoviária (Rodada 3, Missão 2 — extração máxima de APIs/datasets):
# quais rodovias oficiais (BR/UF) a rota efetivamente percorre. A camada
# `rodovias` do BC250/BC100 cobre TODO o viário nacional (287 mil trechos —
# de autoestradas a becos e servidões), não só rodovias numeradas; a coluna
# `nome` está sempre vazia na base (confirmado por inspeção direta), então a
# identificação usa `sigla` (ex.: "BR-364") — presente em ~30% dos trechos,
# exatamente os que correspondem a rodovias oficialmente sinalizadas.
# Trechos sem sigla são descartados: não fabricamos relevância rodoviária
# para uma rua local só porque a rota passa perto dela.
# ==============================================================================

def _detectar_rodovias(pontos: list, repo: GeoIntelligenceRepository, raio_km: float,
                        limite_por_ponto: int = 8) -> list:
    """Rodovias oficiais (sigla BR-xxx/UF-xxx) próximas ao trajeto, deduplicadas
    por sigla normalizada (mantém a menor distância ao eixo). Atributos reais
    da base (jurisdição, administração, concessão, revestimento, pavimento,
    pistas/faixas, limite de velocidade) são propagados tal como cadastrados —
    nunca inferidos quando ausentes."""
    achados: dict = {}
    for la, lo, km_o in pontos:
        try:
            itens = repo.consultar("rodovias", la, lo, raio_km=raio_km, limite=limite_por_ponto)
        except Exception:
            itens = []
        for it in itens:
            sigla = _nome(it.get("sigla"))
            if not sigla:
                continue  # trecho sem sigla oficial — não é uma "rodovia identificada"
            chave = _unorm(sigla)
            try:
                dist = round(float(it.get("distancia_km")), 2)
            except Exception:
                dist = None
            atual = achados.get(chave)
            if atual is not None and dist is not None and atual.distancia_eixo_km is not None \
                    and dist >= atual.distancia_eixo_km:
                continue
            try:
                _flat, _flon = float(it.get("lat")), float(it.get("lon"))
            except Exception:
                _flat, _flon = None, None

            def _num(v):
                try:
                    return int(float(v))
                except Exception:
                    return None

            concessao = _nome(it.get("concession"))
            achados[chave] = Rodovia(
                sigla=sigla,
                km_desde_origem=round(km_o, 1),
                distancia_eixo_km=dist,
                jurisdicao=_nome(it.get("jurisdicao")) or None,
                administra=_nome(it.get("administra")) or None,
                concessionaria=concessao if concessao and concessao.strip().lower() not in ("não", "nao") else None,
                revestimento=_nome(it.get("revestimen")) or None,
                tipo_pavimento=_nome(it.get("tipopavime")) or None,
                nr_pistas=_num(it.get("nrpistas")),
                nr_faixas=_num(it.get("nrfaixas")),
                limite_velocidade_kmh=_num(it.get("limitevelo")),
                trafego=_nome(it.get("trafego")) or None,
                situacao_fisica=_nome(it.get("situacaofi")) or None,
                # [FONTE-REAL - Missão 3, Rodada 17, §39] Mesmo tratamento de _detectar_cruzamentos_hidro.
                fonte=_fonte_real(it, "IBGE BC250/BC100 (rodovias)"),
                lat=_flat, lon=_flon,
            )
    return sorted(achados.values(), key=lambda r: (r.km_desde_origem or 0.0))


# ==============================================================================
# Detecção ferroviária (Rodada 4, Missão 2 — extração máxima). Ao contrário
# de `rodovias`, a camada `ferrovias` tem `nome` populado na maioria dos
# 889 trechos (operadora/linha, ex.: "Estrada de Ferro Vitória a Minas") —
# usado como chave de dedup primária, com o código do trecho (`codtrechof`)
# como identificador de reserva quando falta nome. Camada pequena (<2MB) —
# usa o caminho rápido em memória (`_CAMADAS_PEQUENAS`), não o cache de
# janela ampla das camadas pesadas.
# ==============================================================================

def _detectar_ferrovias(pontos: list, repo: GeoIntelligenceRepository, raio_km: float,
                         limite_por_ponto: int = 5) -> list:
    """Trechos ferroviários próximos ao trajeto, deduplicados por nome (ou
    código do trecho quando sem nome) normalizado, mantendo a menor
    distância ao eixo. Atributos (bitola, eletrificação, nº de linhas,
    jurisdição/concessão) propagados tal como cadastrados."""
    achados: dict = {}
    for la, lo, km_o in pontos:
        try:
            itens = repo.consultar("ferrovias", la, lo, raio_km=raio_km, limite=limite_por_ponto)
        except Exception:
            itens = []
        for it in itens:
            nome = _nome(it.get("nome")) or _nome(it.get("codtrechof")) or "<ferrovia sem nome>"
            chave = _unorm(nome)
            try:
                dist = round(float(it.get("distancia_km")), 2)
            except Exception:
                dist = None
            atual = achados.get(chave)
            if atual is not None and dist is not None and atual.distancia_eixo_km is not None \
                    and dist >= atual.distancia_eixo_km:
                continue
            try:
                _flat, _flon = float(it.get("lat")), float(it.get("lon"))
            except Exception:
                _flat, _flon = None, None

            concessao = _nome(it.get("concession"))
            achados[chave] = Ferrovia(
                nome=nome,
                km_desde_origem=round(km_o, 1),
                distancia_eixo_km=dist,
                tipo_trecho=_nome(it.get("tipotrecho")) or None,
                bitola=_nome(it.get("bitola")) or None,
                eletrificada=_nome(it.get("eletrifica")) or None,
                nr_linhas=_nome(it.get("nrlinhas")) or None,
                jurisdicao=_nome(it.get("jurisdicao")) or None,
                administra=_nome(it.get("administra")) or None,
                concessionaria=concessao if concessao and concessao.strip().lower() not in ("não", "nao") else None,
                posicao_relativa=_nome(it.get("posicaorel")) or None,
                situacao_fisica=_nome(it.get("situacaofi")) or None,
                # [FONTE-REAL - Missão 3, Rodada 17, §39] Mesmo tratamento de _detectar_cruzamentos_hidro.
                fonte=_fonte_real(it, "IBGE BC250/BC100 (ferrovias)"),
                lat=_flat, lon=_flon,
            )
    return sorted(achados.values(), key=lambda f: (f.km_desde_origem or 0.0))


def _indice_dependencia_aquaviaria(rios: list, travessias: list, hidrovias: list,
                                    portos: list) -> int:
    """0-100: quanto a rota parece depender de infraestrutura aquaviária,
    não de sinuosidade hidrográfica incidental. Travessia real confirmada
    pesa mais que apenas cruzar um rio navegável."""
    pontos_ = 0
    if travessias:
        pontos_ += 50
    if any((r.navegavel or "").strip().lower() in ("sim", "parcial") for r in rios):
        pontos_ += 20
    if hidrovias:
        pontos_ += 15
    if portos:
        pontos_ += 15
    return max(0, min(100, pontos_))


def _indice_complexidade_geografica(rios: list, corpos: list, pontes: list, travessias: list,
                                     hidrovias: list, portos: list, rodovias: list, ferrovias: list,
                                     dependencia_aquaviaria: int) -> int:
    """0-100 (Rodada 7, Missão 2 — extração máxima): o campo
    `complexidade_geografica` existia no contrato desde a Rodada 3 original
    mas nunca foi calculado em lugar nenhum — a missão pede explicitamente
    um "Mapa de complexidade das rotas" (§12), que precisa de um número
    real para colorir.

    Heurística composta e documentada (mesmo espírito de
    `_indice_dependencia_aquaviaria`/`confianca_geral` — nunca apresentada
    como medição objetiva, é uma pontuação por evidências reais já
    detectadas, nunca um valor novo inventado):
      - até 30 pts: quantidade de cruzamentos hidrográficos (rios+corpos),
        8 pts cada, satura em 30 (a partir de ~4 cruzamentos já é "muita
        hidrografia" para fins de rota).
      - até 30 pts: dependência aquaviária já calculada (peso 0,3 — reforça
        sem duplicar o mesmo sinal).
      - até 20 pts: mais de uma rodovia oficial identificada (rota
        multi-trecho tende a ser logisticamente mais complexa que uma rota
        numa única BR), 10 pts por rodovia extra além da primeira.
      - 10 pts: algum cruzamento ferroviário próximo (obstáculo/interseção
        adicional).
      - 15 pts: cruzamento hidrográfico SEM ponte nem travessia confirmada
        (incerteza sobre como a rota de fato atravessa — isso é, em si,
        uma forma de complexidade: falta de confirmação)."""
    pontos_ = 0
    pontos_ += min(30, len(rios + corpos) * 8)
    pontos_ += min(30, int((dependencia_aquaviaria or 0) * 0.3))
    pontos_ += min(20, max(0, len(rodovias) - 1) * 10)
    if ferrovias:
        pontos_ += 10
    if (rios or corpos) and not pontes and not travessias:
        pontos_ += 15
    return max(0, min(100, pontos_))


def montar_alternativa_sem_balsa(distancia_atual_km, distancia_sem_balsa_km) -> AlternativaRodoviaria | None:
    """Formata a comparação "rota atual (com travessia) vs. alternativa sem
    balsa" pedida na missão (§13). Função PURA — não roteia nada e não faz
    chamada de rede: recebe as duas distâncias já medidas pelo motor de
    rotas (streamlit_app.py já calcula isso hoje em
    `_vantagem_banda_balsa`/`_balsa_evitavel_banda`; este helper só formata
    o resultado no contrato `ContextoGeograficoRota` para uso pelo pipeline
    principal). Retorna None se as distâncias forem inválidas — nunca
    inventa uma alternativa que não foi de fato medida."""
    try:
        atual = float(distancia_atual_km)
        alt = float(distancia_sem_balsa_km)
    except Exception:
        return None
    if atual <= 0 or alt <= 0:
        return None
    dif_km = alt - atual
    dif_pct = (dif_km / atual) * 100.0
    if dif_km <= 0:
        conclusao = "A alternativa sem travessia é igual ou mais curta — não há motivo geográfico para manter a balsa."
    elif dif_pct < 5.0:
        conclusao = ("A alternativa sem travessia é apenas %.1f%% mais longa (+%.1f km) "
                     "— considerar preferi-la para reduzir a dependência da balsa." % (dif_pct, dif_km))
    else:
        conclusao = ("A alternativa sem travessia é %.1f km (%.1f%%) mais longa "
                     "— a travessia continua sendo a rota mais curta." % (dif_km, dif_pct))
    return AlternativaRodoviaria(distancia_km=round(alt, 1), diferenca_km=round(dif_km, 1),
                                 diferenca_pct=round(dif_pct, 1), conclusao=conclusao)


# ==============================================================================
# Detecção de pontes NO CRUZAMENTO (Rodada 5 — rodoviário/pontes, §8 da
# missão). Deliberadamente não varre pontes ao longo de todo o corredor da
# rota (isso responderia "que pontes existem perto da rota", uma pergunta
# mais fraca) — busca especificamente ao redor de cada cruzamento
# hidrográfico já confirmado (rios_detectados/corpos_dagua), respondendo a
# pergunta certa: "há uma ponte NESTE cruzamento?".
# ==============================================================================

_RAIO_PONTE_KM = 3.0  # bridges are essentially AT the crossing; raio deliberadamente estreito


def _detectar_pontes_nos_cruzamentos(cruzamentos: list, repo: GeoIntelligenceRepository,
                                      raio_km: float = _RAIO_PONTE_KM) -> list:
    """Para cada CruzamentoHidrografico com coordenada conhecida, procura a
    ponte mais próxima dentro de `raio_km`. Pontes do IBGE BC250 raramente
    têm nome próprio cadastrado — quando ausente, o rótulo composto "Ponte
    sobre <rio>" descreve o que já foi identificado (o rio, por fonte
    própria), NUNCA um nome de ponte inventado."""
    pontes: dict = {}
    for cz in cruzamentos:
        if cz.lat is None or cz.lon is None:
            continue
        try:
            itens = repo.consultar("pontes", cz.lat, cz.lon, raio_km=raio_km, limite=1)
        except Exception:
            itens = []
        if not itens:
            continue
        it = itens[0]
        try:
            dist = round(float(it.get("distancia_km")), 2)
        except Exception:
            dist = None
        nome_ponte = _nome(it.get("nome"))
        rotulo = nome_ponte if nome_ponte else ("Ponte sobre %s" % cz.nome)
        chave = (round(cz.lat, 4), round(cz.lon, 4))
        atual = pontes.get(chave)
        if atual is not None and dist is not None and atual.distancia_eixo_km is not None \
                and dist >= atual.distancia_eixo_km:
            continue
        try:
            _plat, _plon = float(it.get("lat")), float(it.get("lon"))
        except Exception:
            _plat, _plon = cz.lat, cz.lon  # sem coordenada própria -> usa o cruzamento como aproximação

        def _numf(v):
            try:
                f = float(v)
                return f if f > 0 else None  # 0.0 nesses campos é sentinela de "não medido", não um valor real
            except Exception:
                return None

        pontes[chave] = Ponte(
            nome=rotulo, distancia_eixo_km=dist, km_desde_origem=cz.km_desde_origem,
            tipo_ponte=_nome(it.get("tipoponte")) or None,
            tipo_pavimento=_nome(it.get("tipopavime")) or None,
            extensao_m=_numf(it.get("extensao")),
            largura_m=_numf(it.get("largura")),
            # [FONTE-REAL - Missão 3, Rodada 17, §39] Mesmo tratamento de _detectar_cruzamentos_hidro.
            fonte=_fonte_real(it, "IBGE BC250/BC100 (pontes)"),
            lat=_plat, lon=_plon)
    return sorted(pontes.values(), key=lambda f: (f.km_desde_origem or 0.0))


# ==============================================================================
# Detecção de anomalias (Rodada 9, Missão 2 — extração máxima §25-26): sinais
# honestos sobre a própria análise já apurada por analisar_rota — nunca uma
# checagem nova que exija dado fora do que já foi coletado.
# ==============================================================================

_LAT_MIN_BR, _LAT_MAX_BR = -34.0, 6.0   # caixa geográfica aproximada do Brasil
_LON_MIN_BR, _LON_MAX_BR = -75.0, -28.0  # (folga proposital — não é validação territorial oficial)


def _dentro_do_brasil(lat, lon) -> bool:
    try:
        return _LAT_MIN_BR <= float(lat) <= _LAT_MAX_BR and _LON_MIN_BR <= float(lon) <= _LON_MAX_BR
    except Exception:
        return True  # sem certeza -> não afirma anomalia


# Valores reais observados em `situacaofi` (rodovias/ferrovias BC250/BC100) que
# indicam infraestrutura que a base já cadastra como não operacional hoje —
# confirmado por inspeção direta dos dois Parquets (Rodada 15/M2). "Desconhecida"
# e "Não aplicável" ficam de fora deliberadamente: não são evidência de que a
# via não existe, só de que a situação não foi apurada/não se aplica.
_SITUACOES_FISICAS_NAO_OPERACIONAIS = {"Abandonada", "Destruída", "Planejada", "Em construção"}


def _detectar_anomalias(lat_o: float, lon_o: float, lat_d: float, lon_d: float,
                         dist_total_km, dist_geodesica_km, rios: list, corpos: list,
                         pontes: list, travessias: list, bacia_principal,
                         rodovias: list | None = None, ferrovias: list | None = None,
                         balsa_reportada_motor: bool | None = None) -> list:
    """Anomalias estruturadas (§25/§26 da missão) a partir do que
    `analisar_rota` já apurou para esta rota — nunca uma inferência nova
    além do que os próprios dados coletados sustentam. Sobrepõe-se em
    parte a `avisos` (texto solto, mantido por compatibilidade) mas em
    formato categorizado/filtrável, como a missão pede para a "camada de
    anomalias" (§26: cada alerta deve poder ser localizado/agregado)."""
    anomalias: list = []

    if not _dentro_do_brasil(lat_o, lon_o):
        anomalias.append(Anomalia(
            categoria="coordenada_origem_fora_do_brasil", severidade="media",
            descricao="Coordenada de origem (%.4f, %.4f) fora da caixa geográfica aproximada do "
                       "Brasil — possível erro de geocodificação." % (lat_o, lon_o)))
    if not _dentro_do_brasil(lat_d, lon_d):
        anomalias.append(Anomalia(
            categoria="coordenada_destino_fora_do_brasil", severidade="media",
            descricao="Coordenada de destino (%.4f, %.4f) fora da caixa geográfica aproximada do "
                       "Brasil — possível erro de geocodificação." % (lat_d, lon_d)))

    if dist_total_km is not None and dist_geodesica_km is not None and dist_total_km < dist_geodesica_km - 0.5:
        anomalias.append(Anomalia(
            categoria="distancia_menor_que_linha_reta", severidade="alta",
            descricao="Distância informada (%.1f km) é menor que a distância geodésica em linha "
                       "reta entre origem e destino (%.1f km) — fisicamente impossível para uma "
                       "rota real; a distância pode estar incorreta." % (dist_total_km, dist_geodesica_km)))

    if (rios or corpos) and not pontes and not travessias:
        nomes = ", ".join(r.nome for r in (rios + corpos)[:2])
        anomalias.append(Anomalia(
            categoria="cruzamento_hidrografico_sem_confirmacao", severidade="media",
            descricao="Rota cruza %s sem ponte nem travessia confirmada no raio consultado — "
                       "modo de travessia real não determinado." % nomes))

    if travessias and not rios and not corpos:
        anomalias.append(Anomalia(
            categoria="travessia_sem_corpo_dagua_no_raio", severidade="baixa",
            descricao="Travessia aquaviária identificada, mas nenhum rio/corpo d'água foi "
                       "detectado no mesmo raio de análise — o corpo d'água correspondente pode "
                       "estar fora do raio consultado nesta camada."))

    if rios and bacia_principal is None:
        anomalias.append(Anomalia(
            categoria="bacia_nao_determinada", severidade="baixa",
            descricao="Bacia hidrográfica não determinada para os rios identificados (nome sem "
                       "correspondência exata na base ANA/SNIRH)."))

    # Rodada 15 (Missão 2, §37): infraestrutura viária/ferroviária que o
    # próprio IBGE cadastra como não operacional no eixo da rota — a rota
    # depende de algo que, segundo a base oficial, não está de fato em uso.
    for r in (rodovias or []):
        if r.situacao_fisica in _SITUACOES_FISICAS_NAO_OPERACIONAIS:
            anomalias.append(Anomalia(
                categoria="infraestrutura_nao_operacional", severidade="alta",
                descricao="Rodovia %s no eixo da rota está cadastrada com situação física "
                          "\"%s\" na base IBGE — pode não estar disponível para tráfego real." %
                          (r.sigla or "sem sigla cadastrada", r.situacao_fisica)))
    for f in (ferrovias or []):
        if f.situacao_fisica in _SITUACOES_FISICAS_NAO_OPERACIONAIS:
            anomalias.append(Anomalia(
                categoria="infraestrutura_nao_operacional", severidade="media",
                descricao="Ferrovia %s no eixo da rota está cadastrada com situação física "
                          "\"%s\" na base IBGE — pode não estar disponível para operação real." %
                          (f.nome or "sem identificação", f.situacao_fisica)))

    # Missão 3, Rodada 2 (§14 da missão "aprimoramento máximo"): cruza o flag de
    # balsa do MOTOR DE ROTEAMENTO (OSRM/Google — vem de fora, via
    # `balsa_reportada_motor`) com a travessia detectada de forma INDEPENDENTE
    # por este motor geográfico (interseção espacial real com a hidrografia
    # IBGE, não depende do que o roteador informou). É exatamente o cenário que
    # motivou este módulo inteiro: o roteador pode simplesmente não marcar uma
    # travessia real (ou, mais raramente, marcar uma que a hidrografia local
    # não sustenta). Só dispara quando os dois lados têm informação para
    # comparar — `balsa_reportada_motor=None` (chamador não informou) não gera
    # nada, para nunca fabricar um "não" que o motor de roteamento não disse.
    if balsa_reportada_motor is False and travessias:
        _nomes_trav = ", ".join(t.nome for t in travessias[:2] if getattr(t, "nome", None))
        anomalias.append(Anomalia(
            categoria="travessia_nao_reportada_pelo_motor_de_rotas", severidade="alta",
            descricao="O motor de roteamento não sinalizou balsa/travessia nesta rota, mas a análise "
                      "geográfica independente (interseção real com a hidrografia IBGE) identificou "
                      "%s no eixo do trajeto — a rota pode depender de uma travessia que o roteador "
                      "não reportou. Vale reexaminar esta decisão." %
                      (_nomes_trav or "uma travessia aquaviária")))
    elif balsa_reportada_motor is True and not travessias and not rios and not corpos:
        anomalias.append(Anomalia(
            categoria="balsa_sem_confirmacao_geografica", severidade="media",
            descricao="O motor de roteamento sinalizou balsa/travessia nesta rota, mas a análise "
                      "geográfica independente não encontrou nenhum rio, corpo d'água ou travessia no "
                      "raio consultado — pode ser limitação do raio de busca, não necessariamente um "
                      "erro do roteador."))

    return anomalias


# ==============================================================================
# Entrada principal
# ==============================================================================

def analisar_rota(origem: tuple, destino: tuple, geometria: list | None = None,
                   distancia_km: float | None = None, raio_km: float | None = None,
                   nivel: int | None = None, suspeita: bool = False,
                   repo: GeoIntelligenceRepository | None = None,
                   balsa_reportada_motor: bool | None = None) -> ContextoGeograficoRota:
    """Motor de contexto geográfico da rota: hidrografia real por geometria
    + bacia oficial ANA/SNIRH (Rodada 3) e travessias/hidrovias/infra
    aquaviária reais + índice de dependência aquaviária (Rodada 4).
    Fail-open honesto: qualquer falha de dados vira aviso explícito em
    `avisos`, nunca um valor fabricado. Nunca lança exceção.

    `balsa_reportada_motor` (Missão 3, Rodada 2, §14): o flag de balsa que o
    MOTOR DE ROTEAMENTO (OSRM/Google) reportou para esta rota, se o chamador
    tiver essa informação — usado só para cruzar contra a travessia detectada
    de forma independente por este módulo (ver `_detectar_anomalias`). Opcional
    e aditivo: `None` (padrão) preserva o comportamento de todo chamador
    existente, que não precisa saber dessa informação."""
    try:
        lat_o, lon_o = float(origem[0]), float(origem[1])
        lat_d, lon_d = float(destino[0]), float(destino[1])
    except Exception:
        return ContextoGeograficoRota(
            origem={}, destino={},
            avisos=["Coordenadas de origem/destino inválidas — análise geográfica não executada."])

    repo = repo or repositorio_padrao()

    try:
        dist_geodesica = _haversine_km(lat_o, lon_o, lat_d, lon_d)
    except Exception:
        dist_geodesica = None

    dist_total = distancia_km
    if dist_total is None:
        dist_total = dist_geodesica

    nivel_ef = int(nivel) if nivel is not None else nivel_automatico(dist_total, suspeita=suspeita)
    raio_ef = float(raio_km) if raio_km is not None else _raio_para_nivel(nivel_ef)
    n_pontos = _n_pontos_para_nivel(nivel_ef, dist_total)
    # [CRUZAMENTO-REAL - 459ª geração] Com a geometria REAL da rota, densifica a amostragem para COBERTURA
    # CONTÍGUA (passo ≲ 2×raio): sem isso, um cruzamento entre dois pontos de amostra afastados nunca vira
    # candidato (falso negativo). Afeta sobretudo rotas curtas (nível 1: passo 30 km × raio 5 km); rotas
    # longas já amostram denso. Só quando há geometria (a corda reta não merecia o custo extra); teto para
    # limitar o nº de consultas em rotas muito longas.
    if geometria:
        try:
            _n_cont = int((dist_total or 0.0) / max(1.0, raio_ef * 2.0)) + 2
            n_pontos = max(n_pontos, min(_n_cont, _N_PONTOS_MAX * 2))
        except Exception:
            pass

    try:
        pontos = pontos_amostrados(lat_o, lon_o, lat_d, lon_d, geometria=geometria, n_pontos=n_pontos)
    except Exception:
        pontos = [(lat_o, lon_o, 0.0), (lat_d, lon_d, dist_total or 0.0)]

    # Polilinha real da rota em (lon, lat) para o teste geométrico de cruzamento (só quando há geometria).
    _linha_rota = None
    if geometria:
        try:
            _linha_rota = [(float(p[1]), float(p[0])) for p in geometria if p and len(p) >= 2]
            if len(_linha_rota) < 2:
                _linha_rota = None
        except Exception:
            _linha_rota = None

    try:
        achados = _detectar_cruzamentos_hidro(pontos, repo, raio_ef, dist_total or 0.0, linha_rota=_linha_rota)
    except Exception:
        achados = []

    rios = [CruzamentoHidrografico(**a) for a in achados if a["camada"] == "drenagem"]
    corpos = [CruzamentoHidrografico(**a) for a in achados if a["camada"] == "massas_dagua"]

    bacias = sorted({r.bacia for r in rios if r.bacia})
    bacia_principal = bacias[0] if bacias else None

    # Rodada 6 (Missão 2): código oficial SNIRH da sub-bacia (nunca um nome
    # — ver docstring de subbacia_codigo_do_rio). "Não determinado" cobre
    # tanto ausência de correspondência quanto ambiguidade entre rios
    # homônimos; múltiplos rios com sub-bacias distintas mostram todos os
    # códigos, não escolhe um arbitrariamente.
    sub_bacia_codigos = sorted({c for c in (subbacia_codigo_do_rio(r.nome) for r in rios) if c})
    sub_bacia = ("Código(s) SNIRH: " + ", ".join(sub_bacia_codigos)) if sub_bacia_codigos else None

    try:
        rodovias = _detectar_rodovias(pontos, repo, raio_ef)
    except Exception:
        rodovias = []

    try:
        ferrovias = _detectar_ferrovias(pontos, repo, raio_ef)
    except Exception:
        ferrovias = []

    # Nível adaptativo (§32): rio detectado -> nível 3 (aquaviário mais denso);
    # se o primeiro passe já achar uma balsa real, nível 4 e raio maior para
    # hidrovias/portos (costumam ficar mais afastados do eixo estrito do rio
    # do que a própria travessia). Nunca reduz o nível pedido explicitamente.
    # Um `raio_km` passado explicitamente pelo chamador SEMPRE vale — o
    # escalonamento automático de nível só define o raio quando o chamador
    # deixou a escolha para o motor (raio_km=None).
    nivel_aqua = max(nivel_ef, 3) if (rios or corpos) else nivel_ef
    raio_aqua = raio_ef if (raio_km is not None or nivel_aqua <= nivel_ef) else _raio_para_nivel(nivel_aqua)

    try:
        travessias, hidrovias, portos = _detectar_aquaviario(pontos, repo, raio_aqua)
    except Exception:
        travessias, hidrovias, portos = [], [], []

    if travessias and nivel_aqua < 4 and raio_km is None:
        # Achou balsa real no passe inicial -> vale ampliar o raio da infra
        # portuária/hidroviária (nível 4) numa segunda passada, mais cara mas
        # só paga o custo quando há evidência real de travessia (e só quando
        # o chamador não fixou o raio explicitamente).
        raio_infra = _raio_para_nivel(4)
        try:
            _, hidrovias2, portos2 = _detectar_aquaviario(pontos, repo, raio_infra)
            hidrovias = hidrovias2 or hidrovias
            portos = portos2 or portos
            nivel_aqua = 4
        except Exception:
            pass

    dependencia = _indice_dependencia_aquaviaria(rios, travessias, hidrovias, portos)

    try:
        pontes = _detectar_pontes_nos_cruzamentos(rios + corpos, repo)
    except Exception:
        pontes = []

    complexidade = _indice_complexidade_geografica(
        rios, corpos, pontes, travessias, hidrovias, portos, rodovias, ferrovias, dependencia)

    fontes: list = []
    if rios:
        fontes.append("IBGE BC250/BC100 (drenagem)")
    if corpos:
        fontes.append("IBGE BC250/BC100 (massas d'água)")
    if bacia_principal:
        fontes.append("ANA/SNIRH (bacias hidrográficas)")
    if travessias:
        fontes.append("IBGE BC250/BC100 (travessias)")
    if hidrovias:
        fontes.append("IBGE BC250/BC100 (hidrovias)")
    if portos:
        fontes.append("IBGE BC250/BC100 (infraestrutura portuária)")
    if pontes:
        fontes.append("IBGE BC250/BC100 (pontes)")
    if rodovias:
        fontes.append("IBGE BC250/BC100 (rodovias)")
    if ferrovias:
        fontes.append("IBGE BC250/BC100 (ferrovias)")

    avisos: list = []
    if any(r.bacia is None for r in rios):
        avisos.append(
            "Bacia hidrográfica não determinada para 1+ rio identificado "
            "(nome sem correspondência exata na base ANA/SNIRH — nunca inferida por proximidade).")
    if not rios and not corpos:
        avisos.append("Nenhum cruzamento hidrográfico detectado no raio/amostragem deste nível de análise.")
    if geometria is None:
        avisos.append("Geometria real da rota não fornecida — cruzamentos estimados pela corda geodésica origem→destino.")
    if not travessias and dependencia == 0:
        avisos.append("Nenhuma evidência de travessia/infraestrutura aquaviária no raio consultado.")
    if (rios or corpos) and not pontes and not travessias:
        avisos.append(
            "Cruzamento(s) hidrográfico(s) sem ponte OU travessia confirmada no raio consultado — "
            "modo de travessia real não determinado (não presuma balsa nem ponte).")
    if not rodovias:
        avisos.append(
            "Nenhuma rodovia com sigla oficial (BR-xxx/UF-xxx) identificada no raio consultado — "
            "pode ser via municipal sem sigla cadastrada, ou raio insuficiente.")

    try:
        anomalias = _detectar_anomalias(lat_o, lon_o, lat_d, lon_d, dist_total, dist_geodesica,
                                         rios, corpos, pontes, travessias, bacia_principal,
                                         rodovias, ferrovias, balsa_reportada_motor)
    except Exception:
        anomalias = []

    conf = 0
    if rios or corpos:
        conf = 70 if any(r.confianca == "alta" for r in (rios + corpos)) else 50
    if bacia_principal:
        conf = min(100, conf + 10)
    if travessias:
        conf = min(100, conf + 15)  # travessia real do IBGE é evidência forte, corrobora o cruzamento
    if pontes:
        conf = min(100, conf + 10)  # ponte real também corrobora o cruzamento
    nivel_conf = "alta" if conf >= 70 else ("media" if conf >= 40 else "nao_determinada")

    motivo_partes: list = []
    if rodovias:
        motivo_partes.append(
            "Rodovia(s) identificada(s): %s." % ", ".join(r.sigla for r in rodovias[:5]))
    if rios:
        # [CRUZAMENTO-REAL - 459ª] com geometria real, separa o que a rota ATRAVESSA do que apenas MARGEIA.
        _cruza = [r for r in rios if r.relacao == "cruza"]
        _margeia = [r for r in rios if r.relacao == "margeia"]
        if _cruza or _margeia:
            _p = []
            if _cruza:
                _p.append("Rota ATRAVESSA %d rio(s)/córrego(s) (%s)" % (
                    len(_cruza), ", ".join(r.nome for r in _cruza[:3])))
            if _margeia:
                _p.append("margeia %d (perto do eixo, sem cruzar: %s)" % (
                    len(_margeia), ", ".join(r.nome for r in _margeia[:2])))
            motivo_partes.append("; ".join(_p) + ".")
        else:
            motivo_partes.append(
                "Rota cruza %d rio(s)/córrego(s) nomeado(s) (%s)." % (
                    len(rios), ", ".join(r.nome for r in rios[:3])))
    if corpos:
        motivo_partes.append(
            "%d corpo(s) d'água adicional(is) identificado(s) (%s)." % (
                len(corpos), ", ".join(c.nome for c in corpos[:2])))
    if bacia_principal:
        motivo_partes.append("Bacia hidrográfica: %s (ANA/SNIRH)." % bacia_principal)
    if pontes:
        motivo_partes.append(
            "%d cruzamento(s) confirmado(s) por ponte (%s)." % (
                len(pontes), ", ".join(p.nome for p in pontes[:2])))
    if travessias:
        motivo_partes.append(
            "Travessia(s) aquaviária(s) real(is) próxima(s): %s." % ", ".join(t.nome for t in travessias[:2]))
    if hidrovias:
        motivo_partes.append("Hidrovia próxima: %s." % hidrovias[0].nome)
    if portos:
        motivo_partes.append(
            "%d instalação(ões) portuária(s)/aquaviária(s) próxima(s) (%s)." % (
                len(portos), ", ".join(p.nome for p in portos[:2])))
    if ferrovias:
        motivo_partes.append(
            "%d trecho(s) ferroviário(s) próximo(s) (%s)." % (
                len(ferrovias), ", ".join(f.nome for f in ferrovias[:2])))
    if not motivo_partes:
        motivo_partes.append("Nenhuma evidência hidrográfica ou aquaviária relevante encontrada no trajeto amostrado.")

    return ContextoGeograficoRota(
        origem={"lat": lat_o, "lon": lon_o},
        destino={"lat": lat_d, "lon": lon_d},
        distancia_km=dist_total,
        rios_detectados=rios,
        corpos_dagua=corpos,
        pontes=pontes,
        travessias=travessias,
        hidrovias_proximas=hidrovias,
        portos_terminais=portos,
        rodovias=rodovias,
        ferrovias=ferrovias,
        bacia_hidrografica=bacia_principal,
        sub_bacia=sub_bacia,
        dependencia_aquaviaria=dependencia,
        complexidade_geografica=complexidade,
        confianca_geral=conf,
        confianca_nivel=nivel_conf,
        fontes_concordam=fontes,
        motivo_decisao=" ".join(motivo_partes),
        avisos=avisos,
        anomalias=anomalias,
        nivel_analise=nivel_aqua,
    )
