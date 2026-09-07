# inteligencia_geoespacial/tests/test_enrichment.py
import pytest

from inteligencia_geoespacial import bases_locais as bl
from inteligencia_geoespacial import enrichment_engine as ee

DATAS_DISPONIVEIS = bool(bl.camadas_disponiveis())

pytestmark = pytest.mark.skipif(
    not DATAS_DISPONIVEIS,
    reason="Camadas derivadas ausentes. Gere com construir_bases_locais_ibge.py",
)


def test_enriquecer_ponto_manaus():
    r = ee.enriquecer_ponto(-3.1190, -60.0217, raio_km=40.0, limite=5)
    assert r["municipio"]["geocodigo"] == "1302603"
    assert r["confianca"]["pontuacao"] >= 40
    assert isinstance(r["balsas_confirmadas"], list)
    assert isinstance(r["pontes_encontradas"], list)


def test_enriquecer_rota_campos_obrigatorios():
    r = ee.enriquecer_rota((-3.1190, -60.0217), (-22.9068, -43.1729), raio_km=50.0)
    obrigatorios = [
        "rios_detectados", "bacia_hidrografica", "pontes_encontradas",
        "infraestrutura_aquaviaria", "balsas_confirmadas", "alternativa_sem_balsa",
        "confianca_geral", "fontes_concordam", "motivo_decisao",
    ]
    for campo in obrigatorios:
        assert campo in r
    assert 0 <= r["confianca_geral"] <= 100
    assert r["origem"]["municipio"]["nome"] == "Manaus"
    assert r["destino"]["municipio"]["nome"] == "Rio de Janeiro"
    assert r["motivo_decisao"]


def test_enriquecer_rota_rios_detectados_sao_do_trecho():
    r = ee.enriquecer_rota((-3.1190, -60.0217), (-22.9068, -43.1729), raio_km=50.0)
    assert all(x["referencia"] in ("origem", "destino") for x in r["rios_detectados"])
    if r["rios_detectados"]:
        assert r["rios_detectados"][0]["distancia_km"] <= 50.0


def test_enriquecer_rota_ponto_fora_do_brasil():
    r = ee.enriquecer_rota((0.0, -30.0), (-22.9068, -43.1729), raio_km=50.0)
    assert r["origem"]["municipio"] is None
    assert r["confianca_geral"] < 100