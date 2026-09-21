# -*- coding: utf-8 -*-
"""[ROBUSTEZ-XLSX] `_read_excel_robusto`: leitura de .xlsx com calamine + fallback openpyxl.

O leitor principal de planilhas de candidatos (`_ler_planilha_upload`, origens e polos da Alocação)
usava só o engine calamine, sem rede de segurança: um .xlsx válido porém atípico (gerador incomum,
.xlsm/.xls renomeado, estilos/shared-strings fora do padrão) derrubava o fluxo principal com um
traceback. Estes testes garantem o caminho feliz e que o fallback openpyxl realmente entra quando o
calamine falha, sem deixar de propagar um arquivo genuinamente ilegível."""
import io

import pandas as pd
import pytest

import streamlit_app as m


def _xlsx_bytes(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf


def test_le_xlsx_normal_via_calamine():
    df = m._read_excel_robusto(_xlsx_bytes(pd.DataFrame({"Origem": ["A", "B"], "Destino": ["C", "D"]})))
    assert list(df.columns) == ["Origem", "Destino"] and len(df) == 2


def test_fallback_openpyxl_quando_calamine_falha(monkeypatch):
    # força o calamine a falhar; o openpyxl tem de assumir e ler normalmente
    _orig = pd.read_excel
    _fonte = _xlsx_bytes(pd.DataFrame({"Origem": ["Z"], "Destino": ["W"]}))

    def _fake_read_excel(fonte, *a, **k):
        if k.get("engine") == "calamine":
            raise RuntimeError("calamine tropeçou (simulado)")
        return _orig(fonte, *a, **k)

    monkeypatch.setattr(pd, "read_excel", _fake_read_excel)
    df = m._read_excel_robusto(_fonte)
    assert list(df.columns) == ["Origem", "Destino"] and df.iloc[0]["Origem"] == "Z"


def test_arquivo_ilegivel_propaga_excecao():
    # nem calamine nem openpyxl leem -> tem de levantar (o chamador mostra a mensagem amigável)
    with pytest.raises(Exception):
        m._read_excel_robusto(io.BytesIO(b"isto nao e um xlsx"))


def test_ler_planilha_upload_usa_o_robusto(monkeypatch):
    # o leitor de upload da Alocação deve herdar o fallback
    _orig = pd.read_excel
    _bytes = _xlsx_bytes(pd.DataFrame({"Origem": ["M"], "Destino": ["N"]})).getvalue()

    def _fake(fonte, *a, **k):
        if k.get("engine") == "calamine":
            raise RuntimeError("calamine simulado")
        return _orig(fonte, *a, **k)

    monkeypatch.setattr(pd, "read_excel", _fake)
    df = m._ler_planilha_upload(_bytes)
    assert list(df.columns) == ["Origem", "Destino"]
