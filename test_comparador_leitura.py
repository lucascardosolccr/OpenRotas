# -*- coding: utf-8 -*-
"""[COMPARADOR - leitura robusta] Regressão de `_ler_planilha_referencia`.

Bug de produção: anexar uma planilha de referência no Comparador de Estudos "dava problema" quando o
arquivo era um CSV brasileiro típico (separador ';' e acentos em latin-1/cp1252) — `pd.read_csv` padrão
levantava UnicodeDecodeError (ou lia tudo numa coluna só), e a exceção virava a mensagem "Não consegui
processar a planilha de referência" na cara do usuário.

Estes testes NÃO sobem o Streamlit: extraem apenas a função `_ler_planilha_referencia` do
streamlit_app.py (por regex) e a exercitam com os formatos reais que os usuários enviam. Assim travam a
correção sem depender do runtime de UI."""
import io
import re

import pandas as pd


def _carregar_leitor():
    _src = open("streamlit_app.py", encoding="utf-8").read()
    _m = re.search(r"\ndef _ler_planilha_referencia\(_arquivo\):.*?\n\n\n@st\.cache_data", _src, re.S)
    assert _m, "função _ler_planilha_referencia não encontrada em streamlit_app.py"
    _code = _m.group(0).replace("\n\n\n@st.cache_data", "")
    _ns = {"pd": pd}
    exec(_code, _ns)
    return _ns["_ler_planilha_referencia"]


_LER = _carregar_leitor()


def _arq(raw, name):
    _b = io.BytesIO(raw)
    _b.name = name
    return _b


def test_csv_brasileiro_ponto_e_virgula_latin1_nao_quebra():
    # o caso EXATO que quebrava: ';' + acentos latin-1
    raw = ("NO_MUNICIPIO;UF;NO_MUN_PROX;DISTANCIA_KM;INSCRITOS\r\n"
           "São Paulo;SP;Campinas;95.4;120\r\n"
           "Rio Branco;AC;Rio Branco;0.0;30\r\n").encode("latin-1")
    df, aviso = _LER(_arq(raw, "referencia.csv"))
    assert list(df.columns) == ["NO_MUNICIPIO", "UF", "NO_MUN_PROX", "DISTANCIA_KM", "INSCRITOS"]
    assert len(df) == 2
    assert aviso is None
    # acento preservado (decodificação correta, não "S\xe3o")
    assert df.iloc[0]["NO_MUNICIPIO"] == "São Paulo"


def test_csv_virgula_utf8():
    raw = "origem,uf,destino,dist_km,inscritos\nManaus,AM,Manaus,0,50\n".encode("utf-8")
    df, aviso = _LER(_arq(raw, "r.csv"))
    assert list(df.columns) == ["origem", "uf", "destino", "dist_km", "inscritos"]
    assert len(df) == 1 and aviso is None


def test_csv_utf8_bom_ponto_e_virgula():
    # Excel BR costuma exportar CSV com BOM utf-8 e ';'
    raw = "﻿MUNICIPIO;UF;POLO;KM\r\nBelém;PA;Belém;0\r\n".encode("utf-8")
    df, aviso = _LER(_arq(raw, "excel_br.csv"))
    assert list(df.columns) == ["MUNICIPIO", "UF", "POLO", "KM"]
    assert df.iloc[0]["MUNICIPIO"] == "Belém"


def test_tsv_tabulacao():
    raw = "origem\tuf\tdestino\tdist\nX\tSP\tY\t10\n".encode("utf-8")
    df, aviso = _LER(_arq(raw, "r.tsv"))
    assert list(df.columns) == ["origem", "uf", "destino", "dist"] and aviso is None


def test_xlsx_calamine():
    buf = io.BytesIO()
    pd.DataFrame({"origem": ["A"], "uf": ["SP"], "destino": ["B"], "dist": [12.0]}).to_excel(buf, index=False)
    buf.seek(0)
    buf.name = "r.xlsx"
    df, aviso = _LER(buf)
    assert list(df.columns) == ["origem", "uf", "destino", "dist"]
    assert len(df) == 1 and aviso is None


def test_csv_coluna_unica_gera_aviso():
    # separador inesperado (nenhum delimitador conhecido) -> 1 coluna -> aviso claro (não exceção)
    raw = "coluna_unica_sem_separador\nvalor1\nvalor2\n".encode("utf-8")
    df, aviso = _LER(_arq(raw, "estranho.csv"))
    assert len(df.columns) == 1
    assert aviso and "1 coluna" in aviso
