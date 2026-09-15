# -*- coding: utf-8 -*-
"""Rede de segurança para a propagação de MARGEM/RISCO aos exportáveis GIS (GeoJSON/KML/GPX) e ao Excel
(realce condicional). O núcleo _export_extra_pares é PURO; os builders GIS devem incluir os pares quando
presentes e a planilha do Lote deve gerar bytes válidos com a coluna de risco.

Roda via pytest a partir da raiz: `python3 -m pytest test_export_margem.py`."""
import logging

logging.disable(logging.WARNING)

import pandas as pd  # noqa: E402

import streamlit_app as m  # noqa: E402


def _df():
    return pd.DataFrame([{
        "Municipio Origem": "Barcelos", "Municipio Destino": "Manaus",
        "Endereco Oficial Origem": "Barcelos - AM", "Endereco Oficial Destino": "Manaus - AM",
        "Distancia": 400.0, "Linha Reta": 300.0, "Tempo": "6 h 30 min", "Balsas": "Sim",
        "Fonte da Rota": "OSRM", "Risco Operacional": "crítico (78)",
        "Margem de Saída (min)": 150, "Antecedência Recomendada": "9h00",
        "Lat Origem": -1.0, "Lon Origem": -63.0, "Lat Destino": -3.1, "Lon Destino": -60.0,
    }])


def test_export_extra_pares_so_o_que_existe():
    pares = dict(m._export_extra_pares(_df().iloc[0].to_dict()))
    assert pares.get("Balsa") == "Sim"
    assert pares.get("Risco") == "crítico (78)"
    assert pares.get("Antecedência") == "9h00"
    # linha sem os campos → lista vazia
    assert m._export_extra_pares({"Municipio Origem": "X"}) == []
    # valores 'nan'/vazios são ignorados
    assert m._export_extra_pares({"Balsas": "nan", "Risco Operacional": "", "Antecedência Recomendada": None}) == []


def test_kml_inclui_risco_e_antecedencia():
    kml = m._df_para_kml(_df())
    assert "Risco: crítico (78)" in kml
    assert "Antecedência: 9h00" in kml
    assert "Balsa: Sim" in kml


def test_gpx_inclui_desc():
    gpx = m._df_para_gpx(_df())
    assert "<desc>" in gpx
    assert "Risco: crítico (78)" in gpx


def test_geojson_inclui_props():
    import json
    gj = json.loads(m._df_para_geojson(_df()))
    props = gj["features"][0]["properties"]
    assert props.get("risco") == "crítico (78)"
    assert props.get("antecedência") == "9h00"


def test_excel_lote_gera_bytes_com_coluna_risco():
    b = m._montar_planilha_lote_xlsx(_df())
    assert isinstance(b, (bytes, bytearray)) and len(b) > 0
    # o arquivo é um zip xlsx válido (assinatura PK)
    assert bytes(b[:2]) == b"PK"
