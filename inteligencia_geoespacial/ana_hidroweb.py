# -*- coding: utf-8 -*-
"""
ana_hidroweb.py — cliente do WebService PÚBLICO da ANA/SNIRH (ServiceANA.asmx)
=============================================================================
Extrai o MÁXIMO de dados hidrológicos oficiais da ANA SEM autenticação, para qualquer estação do Brasil:

- HidroSerieHistorica  → séries históricas de COTAS, VAZÕES e CHUVAS (todas as estações fluviométricas).
  Cada registro é um MÊS com colunas diárias (Cota01..Cota31 / Vazao01..31 / Chuva01..31); aqui é
  "desempilhado" para uma série DIÁRIA [data, valor].
- DadosHidrometeorologicos → telemetria quase em tempo real (Nível, Vazão, Chuva) das estações telemétricas.
- HidroInfoanaSerieTelemetrica / inventário → metadados (opcional).

Base: http://telemetriaws1.ana.gov.br/ServiceANA.asmx  (Telemetria 1, pública até 30/06/2026).
Módulo PURO em relação à rede: os PARSERS não fazem I/O (testáveis com fixtures XML); só as funções
`*_online` chamam a rede via `requests`. Fail-open: qualquer falha devolve estrutura vazia, nunca levanta.
"""
from __future__ import annotations

import csv
import gzip
import math
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from functools import lru_cache

BASE = "http://telemetriaws1.ana.gov.br/ServiceANA.asmx"

# Rede nacional de estações fluviométricas (asset LOCAL versionado — sem rede). Usada para associar a
# estação ANA de referência a um ponto/rota no PROCESSAMENTO (enriquecimento), sem nenhuma chamada externa.
_REDE_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "brasil", "ibge", "derivadas", "estacoes_nacional_overview.csv.gz")
# Índice nacional de rios nomeados (asset LOCAL versionado): descobre o NOME do rio mais próximo de um ponto
# sem depender do Parquet pesado de drenagem (451 MB). Torna exata a estação ANA de referência (casa por rio).
_RIOS_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "brasil", "ibge", "derivadas", "rios_nomeados_index.parquet")


@lru_cache(maxsize=1)
def _rios_index():
    """(nomes:list[str], tree:cKDTree 3D) do índice de rios nomeados, ou None se indisponível. LOCAL, sem rede."""
    try:
        import pandas as _pd
        from . import geo_kdtree as _gk
        _df = _pd.read_parquet(_RIOS_INDEX, columns=["lat", "lon", "nome"])
        if _df is None or _df.empty:
            return None
        return (_df["nome"].astype(str).tolist(), _gk.build(_df["lat"].to_numpy(), _df["lon"].to_numpy()))
    except Exception:
        return None


def rio_mais_proximo_local(lat, lon, max_km=8.0):
    """Nome do rio SIGNIFICATIVO mais próximo de um ponto (índice local, sem rede). None se nada dentro do raio.
    Usado para dar exatidão à estação de referência quando a drenagem densa não está presente."""
    _idx = _rios_index()
    if _idx is None:
        return None
    try:
        from . import geo_kdtree as _gk
        _nomes, _tree = _idx
        _i, _dk = _gk.nearest(_tree, float(lat), float(lon))
        if max_km and _dk > float(max_km):
            return None
        return _nomes[_i]
    except Exception:
        return None


@lru_cache(maxsize=1)
def carregar_rede_nacional():
    """Lista de dicts das estações fluviométricas reais (código ANA, rio, uf, lat, lon, tipo). LOCAL, sem rede.
    Fail-open: se o asset não existir, devolve []."""
    try:
        with gzip.open(_REDE_CSV, "rt", encoding="utf-8") as _f:
            _rows = list(csv.DictReader(_f))
    except Exception:
        return []
    _out = []
    for _r in _rows:
        try:
            _r["lat"] = float(_r.get("lat"))
            _r["lon"] = float(_r.get("lon"))
        except Exception:
            continue
        _out.append(_r)
    return _out


def _haversine_km(la1, lo1, la2, lo2):
    _R = 6371.0088
    _p = math.pi / 180.0
    _a = (math.sin((la2 - la1) * _p / 2) ** 2
          + math.cos(la1 * _p) * math.cos(la2 * _p) * math.sin((lo2 - lo1) * _p / 2) ** 2)
    return 2 * _R * math.asin(min(1.0, math.sqrt(_a)))


_RIO_PREFIXOS = ("RIO ", "IGARAPE ", "CORREGO ", "RIBEIRAO ", "RIACHO ", "ARROIO ", "LAGO ",
                 "LAGOA ", "CANAL ", "REPRESA ", "ACUDE ", "BRACO ", "PARANA ")


def _sem_acento(s):
    import unicodedata
    return "".join(_c for _c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(_c) != "Mn")


def _norm_rio(s):
    """Normaliza nome de rio p/ casamento: sem acento, maiúsculas, sem o prefixo (Rio/Igarapé/…), 1 espaço."""
    if not s:
        return ""
    _t = _sem_acento(s).upper().strip()
    for _p in _RIO_PREFIXOS:
        if _t.startswith(_p):
            _t = _t[len(_p):]
            break
    return " ".join(_t.split())


def _rios_casam(a, b):
    """True se dois nomes de rio se referem ao mesmo curso (igual, ou um contém o outro; ex.: Solimões-Amazonas)."""
    _a = _norm_rio(a); _b = _norm_rio(b)
    if not _a or not _b:
        return False
    if _a == _b:
        return True
    return len(_a) >= 4 and len(_b) >= 4 and (_a in _b or _b in _a)


def _classificar_ref(mesmo_rio, dist_km):
    """direta = mede o MESMO rio e está perto (≤25 km); aproximada = mesmo rio porém distante (≤80 km) ou
    estação próxima (≤15 km) mesmo sem confirmar o rio; regional = distante e de outro curso d'água."""
    if mesmo_rio and dist_km <= 25:
        return "direta"
    if (mesmo_rio and dist_km <= 80) or dist_km <= 15:
        return "aproximada"
    return "regional"


def estacao_de_referencia(lat, lon, rio_nome=None, max_km=200.0):
    """Estação ANA fluviométrica de referência para um ponto — a MAIS EXATA possível: prefere a estação no
    MESMO RIO (quando o rio é conhecido) dentro do raio; senão, a mais próxima em linha reta. Devolve
    {codigo,nome,rio,uf,tipo,distancia_km,mesmo_rio,rio_consultado,classificacao} ou None. PURA, sem rede."""
    try:
        _la = float(lat); _lo = float(lon)
    except Exception:
        return None
    if not (-34.5 <= _la <= 6.0 and -74.5 <= _lo <= -34.0):
        return None
    # Sem o rio informado, descobre-o no ÍNDICE LOCAL de rios nomeados → referência mais exata (mesmo rio).
    if not _norm_rio(rio_nome):
        rio_nome = rio_mais_proximo_local(_la, _lo)
    _rio_conhecido = bool(_norm_rio(rio_nome))
    _b_rio = _d_rio = _b_any = _d_any = None
    for _r in carregar_rede_nacional():
        _d = _haversine_km(_la, _lo, _r["lat"], _r["lon"])
        if _d_any is None or _d < _d_any:
            _d_any = _d; _b_any = _r
        if _rio_conhecido and _rios_casam(rio_nome, _r.get("rio")):
            if _d_rio is None or _d < _d_rio:
                _d_rio = _d; _b_rio = _r
    if _b_rio is not None and _d_rio <= float(max_km):
        _best, _dist, _mesmo = _b_rio, _d_rio, True
    elif _b_any is not None and _d_any <= float(max_km):
        _best, _dist = _b_any, _d_any
        _mesmo = _rio_conhecido and _rios_casam(rio_nome, _best.get("rio"))
    else:
        return None
    return {"codigo": str(_best.get("codigo", "")).strip(), "nome": str(_best.get("nome", "")).strip(),
            "rio": str(_best.get("rio", "")).strip(), "uf": str(_best.get("uf", "")).strip(),
            "tipo": str(_best.get("tipo", "")).strip(), "distancia_km": round(_dist, 1),
            "mesmo_rio": bool(_mesmo), "rio_consultado": str(rio_nome or "").strip(),
            "classificacao": _classificar_ref(_mesmo, _dist)}


def estacao_mais_proxima(lat, lon, max_km=150.0):
    """Estação ANA mais próxima em linha reta (sem casar rio). Mantida para compatibilidade; prefira
    `estacao_de_referencia`, que casa pelo mesmo rio quando possível."""
    return estacao_de_referencia(lat, lon, rio_nome=None, max_km=max_km)

# HidroSerieHistorica: tipoDados 1=Cotas(cm), 2=Chuvas(mm), 3=Vazões(m³/s)
TIPO_DADOS = {"cotas": 1, "cota": 1, "chuvas": 2, "chuva": 2, "vazoes": 3, "vazões": 3, "vazao": 3, "vazão": 3}
PREFIXO_DIARIO = {1: "Cota", 2: "Chuva", 3: "Vazao"}
UNIDADE = {1: "cm", 2: "mm", 3: "m³/s"}


def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _num(txt):
    if txt is None:
        return None
    s = str(txt).strip().replace(",", ".")
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def parse_serie_historica(xml_text, tipo_dados):
    """XML do HidroSerieHistorica → lista de dicts [{'data': datetime, 'valor': float}] (série DIÁRIA).
    PURO. `tipo_dados` ∈ {1,2,3}. Desempilha as colunas diárias (Cota01..31 etc.) do mês de cada registro."""
    _pref = PREFIXO_DIARIO.get(int(tipo_dados), "Cota")
    _re_dia = re.compile(r"^%s(\d{2})$" % _pref)
    out = []
    if not xml_text:
        return out
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for el in root.iter():
        if _local(el.tag) != "SerieHistorica":
            continue
        _mes = None
        _dias = {}
        for ch in el:
            _n = _local(ch.tag)
            if _n == "DataHora":
                _mes = _parse_data(ch.text)
            else:
                m = _re_dia.match(_n)
                if m:
                    _v = _num(ch.text)
                    if _v is not None:
                        _dias[int(m.group(1))] = _v
        if _mes is None:
            continue
        for _d, _v in _dias.items():
            try:
                _data = _mes.replace(day=1) + timedelta(days=_d - 1)
            except Exception:
                continue
            out.append({"data": _data, "valor": _v})
    out.sort(key=lambda r: r["data"])
    return out


def parse_telemetria(xml_text):
    """XML do DadosHidrometeorologicos → lista de dicts [{'data','nivel','vazao','chuva'}]. PURO.
    (A ANA grafa o elemento como 'DadosHidrometereologicos' — casamos qualquer 'DadosHidromete...'.)"""
    out = []
    if not xml_text:
        return out
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for el in root.iter():
        if not _local(el.tag).startswith("DadosHidromete"):
            continue
        _rec = {"data": None, "nivel": None, "vazao": None, "chuva": None}
        for ch in el:
            _n = _local(ch.tag).lower()
            if _n in ("datahora", "data"):
                _rec["data"] = _parse_data(ch.text)
            elif _n == "nivel":
                _rec["nivel"] = _num(ch.text)
            elif _n == "vazao":
                _rec["vazao"] = _num(ch.text)
            elif _n == "chuva":
                _rec["chuva"] = _num(ch.text)
        if _rec["data"] is not None and any(_rec[k] is not None for k in ("nivel", "vazao", "chuva")):
            out.append(_rec)
    out.sort(key=lambda r: r["data"])
    return out


def parse_inventario(xml_text):
    """XML do HidroInventario/HidroInfoanaSerieTelemetrica → dict de metadados (1º registro). PURO."""
    if not xml_text:
        return {}
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return {}
    for el in root.iter():
        _n = _local(el.tag)
        if _n in ("Table", "DocumentElement"):
            continue
        filhos = list(el)
        if len(filhos) >= 3 and any(_local(f.tag) in ("NomeEstacao", "Estacao_Nome", "Codigo", "EstacaoCodigo") for f in filhos):
            return {_local(f.tag): (f.text or "").strip() for f in filhos}
    return {}


def _parse_data(txt):
    if not txt:
        return None
    s = str(txt).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
                "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:len(fmt) + 6] if "%z" in fmt else s[:19] if "T" in s or " " in s else s[:10], fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


# --------------------------------------------------------------------------- rede (online)
def serie_historica_online(codigo, tipo_serie, data_inicio, data_fim, consistencia=2, timeout=30, session=None):
    """Baixa e faz o parse da série histórica (cota/vazão/chuva). Datas em dd/MM/yyyy. Devolve
    {'ok','serie':[{data,valor}],'unidade','tipo_dados','url','erro'}. Fail-open."""
    import requests
    _td = TIPO_DADOS.get(str(tipo_serie).strip().lower(), 1)
    _url = BASE + "/HidroSerieHistorica"
    _par = {"codEstacao": str(codigo).strip(), "dataInicio": _fmt_data(data_inicio, "%d/%m/%Y"),
            "dataFim": _fmt_data(data_fim, "%d/%m/%Y"), "tipoDados": _td, "nivelConsistencia": int(consistencia)}
    try:
        _r = (session or requests).get(_url, params=_par, timeout=timeout)
        if _r.status_code != 200:
            return {"ok": False, "serie": [], "unidade": UNIDADE.get(_td, ""), "tipo_dados": _td,
                    "url": _r.url, "erro": "HTTP %d" % _r.status_code}
        _serie = parse_serie_historica(_r.text, _td)
        return {"ok": True, "serie": _serie, "unidade": UNIDADE.get(_td, ""), "tipo_dados": _td, "url": _r.url, "erro": None}
    except Exception as _e:
        return {"ok": False, "serie": [], "unidade": UNIDADE.get(_td, ""), "tipo_dados": _td,
                "url": _url, "erro": type(_e).__name__}


def telemetria_online(codigo, data_inicio, data_fim, timeout=30, session=None):
    """Baixa e faz o parse da telemetria (nível/vazão/chuva). Datas em yyyy-MM-dd. Fail-open."""
    import requests
    _url = BASE + "/DadosHidrometeorologicos"
    _par = {"codEstacao": str(codigo).strip(), "dataInicio": _fmt_data(data_inicio, "%Y-%m-%d"),
            "dataFim": _fmt_data(data_fim, "%Y-%m-%d")}
    try:
        _r = (session or requests).get(_url, params=_par, timeout=timeout)
        if _r.status_code != 200:
            return {"ok": False, "serie": [], "url": _r.url, "erro": "HTTP %d" % _r.status_code}
        return {"ok": True, "serie": parse_telemetria(_r.text), "url": _r.url, "erro": None}
    except Exception as _e:
        return {"ok": False, "serie": [], "url": _url, "erro": type(_e).__name__}


def _fmt_data(d, fmt):
    if isinstance(d, str):
        return d
    try:
        return d.strftime(fmt)
    except Exception:
        return str(d)
