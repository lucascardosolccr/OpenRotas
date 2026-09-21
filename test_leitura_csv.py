# -*- coding: utf-8 -*-
"""[CSV-EM-TODA-APP] Leitura unificada de planilhas por BYTES: `_parse_csv_bytes` (CSV/TXT/TSV
tolerante ao formato brasileiro — separador ';' e acentos latin-1) e `_parse_planilha_bytes` (Excel OU
CSV, detectado pela ASSINATURA do conteúdo). O Lote e a Alocação passam a aceitar CSV como o Comparador
já fazia. Estes testes travam o parsing por conteúdo, sem depender da extensão."""
import io

import pandas as pd

import streamlit_app as m


def _xlsx_bytes(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_csv_virgula():
    b = b"Origem,Destino\nBelem,Ananindeua\nManaus,Manaus\n"
    df, aviso = m._parse_csv_bytes(b)
    assert list(df.columns) == ["Origem", "Destino"] and len(df) == 2
    assert aviso is None


def test_csv_brasileiro_ponto_e_virgula_latin1():
    # ';' como separador e acento em latin-1 (o CSV brasileiro clássico)
    b = "Origem;Destino\nBelém;Ananindeua\nSão Paulo;Guarulhos\n".encode("latin-1")
    df, aviso = m._parse_csv_bytes(b)
    assert list(df.columns) == ["Origem", "Destino"]
    assert df.iloc[1]["Origem"] == "São Paulo"
    assert aviso is None


def test_csv_uma_coluna_avisa():
    b = b"Origem;Destino\nA;B\n"  # sniffer acha ';' -> 2 colunas; forca 1 coluna com separador improvavel
    df, aviso = m._parse_csv_bytes(b"OrigemDestino\nAB\nCD\n")
    assert len(df.columns) == 1 and aviso and "1 coluna" in aviso


def test_parse_planilha_detecta_excel_por_assinatura():
    df_in = pd.DataFrame({"Origem": ["A", "B"], "Destino": ["C", "D"]})
    df, aviso = m._parse_planilha_bytes(_xlsx_bytes(df_in))
    assert list(df.columns) == ["Origem", "Destino"] and len(df) == 2


def test_parse_planilha_detecta_csv_por_assinatura():
    df, aviso = m._parse_planilha_bytes(b"Origem;Destino\nX;Y\n")
    assert list(df.columns) == ["Origem", "Destino"] and df.iloc[0]["Destino"] == "Y"


def test_ler_planilha_upload_aceita_csv():
    df = m._ler_planilha_upload(b"Origem,Destino\nBelem,Ananindeua\n")
    assert list(df.columns) == ["Origem", "Destino"] and len(df) == 1


def test_ler_planilha_upload_ainda_le_xlsx():
    df_in = pd.DataFrame({"Origem": ["M"], "Destino": ["N"]})
    df = m._ler_planilha_upload(_xlsx_bytes(df_in))
    assert list(df.columns) == ["Origem", "Destino"]
