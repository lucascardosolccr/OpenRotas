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

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

BASE = "http://telemetriaws1.ana.gov.br/ServiceANA.asmx"

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
