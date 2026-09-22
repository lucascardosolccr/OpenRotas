# -*- coding: utf-8 -*-
"""[HONESTIDADE-DADOS · Hidrografia] O catálogo real de estações da ANA/SNIRH (snirh_estacaos.csv, ~91 MB) é
baixado sob demanda; até lá a aba Hidrografia usava uma amostra que fabricava CÓDIGOS de estação ("12345000"…)
— isso quebrava a consulta à API ao vivo e induzia ao erro (parecia dado real). A amostra agora é HONESTA:
locais reais, código placeholder '—', e uma coluna `fonte` que a UI usa para avisar e desabilitar a consulta
ao vivo. Estes testes travam esse contrato."""
import streamlit_app as m


def test_amostra_estacoes_nao_fabrica_codigos():
    df = m._gerar_dados_estacoes_fallback()
    assert not df.empty
    # nenhum código numérico inventado — todos são o placeholder honesto
    assert set(df["codigo"].astype(str)) == {"—"}
    # a fonte identifica a amostra para a UI avisar
    assert "fonte" in df.columns
    assert "amostra" in str(df["fonte"].iloc[0]).lower()
    assert df["fonte"].nunique() == 1


def test_amostra_mantem_locais_reais():
    df = m._gerar_dados_estacoes_fallback()
    _nomes = " ".join(df["nome"].astype(str))
    # continua sendo uma amostra útil de locais REAIS (não fabricados)
    assert "Óbidos" in _nomes and "Pirapora" in _nomes
    # coordenadas plausíveis no Brasil
    assert df["lat"].between(-34, 6).all()
    assert df["lon"].between(-74, -34).all()
