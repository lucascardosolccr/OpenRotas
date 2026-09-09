"""
route_context.py — Motor de Contexto Geográfico da Rota (GeoIntelligenceEngine).

Missão "Aprimoramento máximo da aba de Inteligência":
  Rodada 3 — integração hidrográfica real (rios/corpos d'água pela GEOMETRIA
             da rota, não só quando o motor de roteamento reporta balsa; bacia
             hidrográfica oficial ANA/SNIRH).
  Rodada 4 — integração aquaviária (travessias/balsas reais do IBGE, hidrovias,
             portos/terminais/eclusas; índice de dependência aquaviária).
  Rodada 5 — pontes NO cruzamento hidrográfico (§8 da missão): para cada rio/
             corpo d'água detectado, verifica se há uma ponte cadastrada
             naquele ponto — nunca varre pontes genéricas "perto da rota".

Tudo consultando as camadas locais derivadas do IBGE (`bases_locais.py`) —
sem GDAL, sem geopandas, sem rede.

Este módulo é ADITIVO: não substitui nem altera `enrichment_engine.py` (usado
hoje pelos dois botões manuais já em produção nas abas "Rotas com Balsa" e
"Geoespacial IBGE"). Ele é o novo motor que, em rodada futura (integração ao
motor de rotas), passará a alimentar automaticamente cada rota calculada
pela aplicação.

Contrato principal:

    from inteligencia_geoespacial import route_context as geo_ctx

    ctx = geo_ctx.analisar_rota(origem=(lat, lon), destino=(lat, lon),
                                 geometria=lista_de_(lat,lon)_ou_None,
                                 distancia_km=distancia_real_ou_None)

    ctx.rios_detectados          # list[CruzamentoHidrografico]
    ctx.corpos_dagua             # list[CruzamentoHidrografico]
    ctx.bacia_hidrografica       # str | None (nunca inventado — só nome oficial ANA/SNIRH)
    ctx.pontes                   # list[Feicao] — pontes reais encontradas NOS cruzamentos
    ctx.travessias               # list[Feicao] — balsas reais (IBGE BC250/BC100)
    ctx.hidrovias_proximas       # list[Feicao]
    ctx.portos_terminais         # list[Feicao] — atracadouros/terminais/portos/eclusas
    ctx.dependencia_aquaviaria   # 0-100
    ctx.confianca_geral          # 0-100
    ctx.avisos                   # incerteza explícita, nunca fabricação

`alternativa_sem_balsa` continua reservado no contrato mas é responsabilidade
de quem já tem as duas distâncias medidas pelo motor de rotas (este módulo
não faz roteamento nem chamadas de rede) — ver `montar_alternativa_sem_balsa`,
uma função pura de formatação para ser usada quando o pipeline principal
integrar este motor (rodada de integração ao motor de rotas).
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


def bacia_do_rio(nome_rio) -> str | None:
    """Nome oficial da bacia hidrográfica (ANA/SNIRH) para um nome de rio,
    ou None se não houver correspondência exata (nunca inferido/inventado)."""
    if not nome_rio:
        return None
    return _carregar_mapa_rio_bacia().get(_unorm(nome_rio))


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


@dataclass
class Feicao:
    """Ponte/travessia/hidrovia/porto próximo a um cruzamento."""
    nome: str
    tipo: str
    distancia_eixo_km: float | None
    km_desde_origem: float | None
    fonte: str


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
    nivel_analise: int = 1


# ==============================================================================
# Níveis adaptativos (§32 da missão) — reaproveita sinais já existentes no
# motor de rotas (razão V/R suspeita, balsa) em vez de inventar uma nova
# heurística. Nesta rodada só o nível básico é usado por analisar_rota
# (níveis 4+ ficam reservados para quando a camada aquaviária existir).
# ==============================================================================

_RAIO_POR_NIVEL = {1: 3.0, 2: 5.0, 3: 6.0, 4: 8.0, 5: 8.0, 6: 12.0}
_PASSO_KM_POR_NIVEL = {1: 40.0, 2: 15.0, 3: 15.0, 4: 10.0, 5: 10.0, 6: 8.0}
_N_PONTOS_MIN, _N_PONTOS_MAX = 3, 60


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


def _detectar_cruzamentos_hidro(pontos: list, repo: GeoIntelligenceRepository,
                                 raio_km: float, distancia_total_km: float) -> list:
    """Consulta as camadas hidrográficas em cada ponto amostrado e deduplica
    por (camada, nome normalizado), mantendo a MENOR distância ao eixo da
    rota e o km acumulado (desde a origem) daquele ponto de amostra."""
    achados: dict = {}
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
                    "fonte": ("IBGE BC250/BC100 (drenagem)" if camada == "drenagem"
                              else "IBGE BC250/BC100 (massas d'água)"),
                    "confianca": ("alta" if (dist is not None and dist <= max(0.5, raio_km * 0.15))
                                  else "media"),
                    "lat": la,
                    "lon": lo,
                }
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


def _detectar_feicoes(pontos: list, repo: GeoIntelligenceRepository, camada: str,
                       raio_km: float, tipo_rotulo: str, fonte: str,
                       filtros: dict | None = None, limite: int = 5) -> list:
    """Generaliza a deduplicação de `_detectar_cruzamentos_hidro` para
    qualquer camada de feições pontuais/lineares (travessias, hidrovias,
    portos, eclusas), devolvendo `Feicao` já ordenadas pela posição no
    trajeto. Nome ausente na base vira rótulo explícito, nunca None solto
    (mesma convenção já usada em enrichment_engine.py)."""
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
            achados[chave] = Feicao(nome=nome, tipo=tipo_rotulo, distancia_eixo_km=dist,
                                     km_desde_origem=round(km_o, 1), fonte=fonte)
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
            pontos, repo, camada, raio_km, rotulo, "IBGE BC250/BC100 (%s)" % camada))
    portos.sort(key=lambda f: (f.km_desde_origem or 0.0))
    return travessias, hidrovias, portos


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
        pontes[chave] = Feicao(nome=rotulo, tipo="ponte", distancia_eixo_km=dist,
                                km_desde_origem=cz.km_desde_origem,
                                fonte="IBGE BC250/BC100 (pontes)")
    return sorted(pontes.values(), key=lambda f: (f.km_desde_origem or 0.0))


# ==============================================================================
# Entrada principal
# ==============================================================================

def analisar_rota(origem: tuple, destino: tuple, geometria: list | None = None,
                   distancia_km: float | None = None, raio_km: float | None = None,
                   nivel: int | None = None, suspeita: bool = False,
                   repo: GeoIntelligenceRepository | None = None) -> ContextoGeograficoRota:
    """Motor de contexto geográfico da rota: hidrografia real por geometria
    + bacia oficial ANA/SNIRH (Rodada 3) e travessias/hidrovias/infra
    aquaviária reais + índice de dependência aquaviária (Rodada 4).
    Fail-open honesto: qualquer falha de dados vira aviso explícito em
    `avisos`, nunca um valor fabricado. Nunca lança exceção."""
    try:
        lat_o, lon_o = float(origem[0]), float(origem[1])
        lat_d, lon_d = float(destino[0]), float(destino[1])
    except Exception:
        return ContextoGeograficoRota(
            origem={}, destino={},
            avisos=["Coordenadas de origem/destino inválidas — análise geográfica não executada."])

    repo = repo or repositorio_padrao()

    dist_total = distancia_km
    if dist_total is None:
        try:
            dist_total = _haversine_km(lat_o, lon_o, lat_d, lon_d)
        except Exception:
            dist_total = None

    nivel_ef = int(nivel) if nivel is not None else nivel_automatico(dist_total, suspeita=suspeita)
    raio_ef = float(raio_km) if raio_km is not None else _raio_para_nivel(nivel_ef)
    n_pontos = _n_pontos_para_nivel(nivel_ef, dist_total)

    try:
        pontos = pontos_amostrados(lat_o, lon_o, lat_d, lon_d, geometria=geometria, n_pontos=n_pontos)
    except Exception:
        pontos = [(lat_o, lon_o, 0.0), (lat_d, lon_d, dist_total or 0.0)]

    try:
        achados = _detectar_cruzamentos_hidro(pontos, repo, raio_ef, dist_total or 0.0)
    except Exception:
        achados = []

    rios = [CruzamentoHidrografico(**a) for a in achados if a["camada"] == "drenagem"]
    corpos = [CruzamentoHidrografico(**a) for a in achados if a["camada"] == "massas_dagua"]

    bacias = sorted({r.bacia for r in rios if r.bacia})
    bacia_principal = bacias[0] if bacias else None
    sub_bacia = None  # Sem fonte oficial de sub-bacia por trecho na base atual — não inventado.

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
    if rios:
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
        bacia_hidrografica=bacia_principal,
        sub_bacia=sub_bacia,
        dependencia_aquaviaria=dependencia,
        confianca_geral=conf,
        confianca_nivel=nivel_conf,
        fontes_concordam=fontes,
        motivo_decisao=" ".join(motivo_partes),
        avisos=avisos,
        nivel_analise=nivel_aqua,
    )
