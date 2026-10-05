# -*- coding: utf-8 -*-
"""Cobertura NACIONAL das bases geoespaciais (não só Amazônia).

Garante que as camadas nacionais (drenagem/rodovias) estão DECLARADAS e ficam DISPONÍVEIS por
reassembly sob demanda dos pedaços versionados em _bigparts/ — para a aba Inteligência →
Hidrografia/geoespacial cobrir TODO o Brasil."""
from pathlib import Path

from inteligencia_geoespacial import bases_locais as bl


def test_camadas_nacionais_declaradas():
    # drenagem (rios de todo o Brasil) e rodovias (malha nacional) são camadas de 1ª classe
    assert "drenagem" in bl.DISPONIVEIS and "rodovias" in bl.DISPONIVEIS


def test_garantir_derivada_quando_presente_ou_reassembla():
    # neste ambiente há o .parquet OU os pedaços em _bigparts/ → a nacional fica disponível
    tem_parquet = (bl._DERIVADAS / "drenagem.parquet").exists()
    tem_pedacos = bl._BIGPARTS.exists() and any(bl._BIGPARTS.glob("drenagem.parquet.part*"))
    if not (tem_parquet or tem_pedacos):
        import pytest
        pytest.skip("sem drenagem.parquet nem pedaços neste ambiente")
    assert bl._garantir_derivada("drenagem") is True
    assert (bl._DERIVADAS / "drenagem.parquet").exists()


def test_camadas_disponiveis_inclui_nacionais_quando_ha_dados():
    tem = (bl._DERIVADAS / "drenagem.parquet").exists() or \
          (bl._BIGPARTS.exists() and any(bl._BIGPARTS.glob("drenagem.parquet.part*")))
    if not tem:
        import pytest
        pytest.skip("sem dados nacionais neste ambiente")
    disp = bl.camadas_disponiveis()
    assert "drenagem" in disp and "rodovias" in disp


def test_garantir_derivada_degrada_sem_pedacos(tmp_path, monkeypatch):
    # sem .parquet e sem pedaços → False, sem levantar (zero regressão)
    monkeypatch.setattr(bl, "_DERIVADAS", tmp_path / "derivadas")
    monkeypatch.setattr(bl, "_BIGPARTS", tmp_path / "derivadas" / "_bigparts")
    monkeypatch.setattr(bl, "_MONTAGEM_TENTADA", False)
    (tmp_path / "derivadas").mkdir(parents=True, exist_ok=True)
    assert bl._garantir_derivada("drenagem") is False
