# -*- coding: utf-8 -*-
"""[CSV-EM-TODA-APP] O modelo de planilha do Lote passa a ser oferecido também em CSV. Este teste
garante que o CSV gerado é bem-formado E que ROUND-TRIPA pela própria leitura da app (_parse_csv_bytes):
o arquivo que entregamos ao usuário é lido de volta com as colunas certas — ';' + UTF-8-BOM, acentos
preservados. Fecha o ciclo 'baixe o modelo → preencha → reenvie'."""
import streamlit_app as m


def test_modelo_csv_gerado_e_valido():
    b = m._gerar_modelo_lote_csv()
    assert b and isinstance(b, (bytes, bytearray))
    assert b[:3] == b"\xef\xbb\xbf"          # UTF-8 BOM (Excel abre com acentos certos)
    assert b";" in b                         # separador brasileiro


def test_modelo_csv_roundtrip_pela_leitura_da_app():
    b = m._gerar_modelo_lote_csv()
    df, aviso = m._parse_csv_bytes(b)
    assert list(df.columns) == ["Origem", "Destino"]   # cabeçalho exato que o Lote exige
    assert len(df) == 3                                  # as 3 linhas de exemplo
    assert aviso is None                                 # não caiu em 1 coluna só
    # acento preservado no round-trip
    assert any("Ribeirão" in str(v) for v in df["Origem"].tolist())


def test_modelo_csv_passa_no_diagnostico_de_colunas():
    df, _ = m._parse_csv_bytes(m._gerar_modelo_lote_csv())
    ok, msg = m._diagnosticar_colunas_lote(df.columns)
    assert ok is True and msg == ""
