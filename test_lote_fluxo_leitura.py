# -*- coding: utf-8 -*-
"""[LOTE-FLUXO] Guarda de integração do CAMINHO REAL de leitura+validação do Lote, exercitado com
DataFrames de verdade (columns = pandas Index). Reproduz a cadeia que roda na produção sem subir o
Streamlit: bytes → _ler_planilha_upload → .columns.str.strip().str.title() → _diagnosticar_colunas_lote
→ _valores_unicos_limpos. Motivado por uma regressão real: `_diagnosticar_colunas_lote(df.columns)`
quebrava com "truth value of a Index is ambiguous" — o teste anterior só passava listas, não o Index.
Esta guarda cobre a cadeia inteira, para Excel E CSV."""
import io

import pandas as pd

import streamlit_app as m


def _xlsx_bytes(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def _rodar_cadeia(conteudo_bytes):
    """Replica a validação da aba de Lote (a parte pura, sem st)."""
    df = m._ler_planilha_upload(conteudo_bytes)
    df.columns = df.columns.str.strip().str.title()   # exatamente como a produção
    ok, msg = m._diagnosticar_colunas_lote(df.columns)  # df.columns é um pandas Index
    return df, ok, msg


def test_cadeia_xlsx_valida():
    b = _xlsx_bytes(pd.DataFrame({"origem": ["Belem", "  ", "Manaus"], "destino": ["A", "B", "C"]}))
    df, ok, msg = _rodar_cadeia(b)
    assert ok is True and msg == ""
    # limpeza de origens: a célula em branco é descartada e contada
    origens, n_desc = m._valores_unicos_limpos(df["Origem"])
    assert "" not in origens and n_desc == 1


def test_cadeia_csv_valida():
    b = "Origem;Destino\nBelém;Ananindeua\nManaus;Manaus\n".encode("utf-8")
    df, ok, msg = _rodar_cadeia(b)
    assert ok is True and msg == ""
    assert list(df.columns) == ["Origem", "Destino"]


def test_cadeia_coluna_faltando_da_mensagem_acionavel():
    b = _xlsx_bytes(pd.DataFrame({"cidade": ["X"], "polo": ["Y"]}))
    df, ok, msg = _rodar_cadeia(b)
    assert ok is False
    assert "Cidade" in msg and "Polo" in msg      # mostra o que veio
    assert "Origem" in msg and "Destino" in msg    # e o que falta
