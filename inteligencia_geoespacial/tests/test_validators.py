# inteligencia_geoespacial/tests/test_validators.py
import pytest

from inteligencia_geoespacial import bases_locais as bl
from inteligencia_geoespacial import validators as va

DATAS_DISPONIVEIS = bool(bl.camadas_disponiveis())

pytestmark = pytest.mark.skipif(
    not DATAS_DISPONIVEIS,
    reason="Camadas derivadas ausentes. Gere com construir_bases_locais_ibge.py",
)


def test_municipio_sao_paulo():
    v = va.CoordinateValidator()
    m = v.municipio(-23.5505, -46.6333)
    assert m.get("nome") == "São Paulo"
    assert m.get("geocodigo") == "3550308"


def test_municipio_fora_do_brasil():
    v = va.CoordinateValidator()
    assert v.municipio(0.0, -30.0) == {}


def test_rio_mais_proximo_nomeado_manaus():
    v = va.CoordinateValidator(raio_km=50.0)
    r = v.rio_mais_proximo(-3.1190, -60.0217)
    assert r is not None
    assert r.get("nome") is not None and r["nome"].strip()
    assert 0.0 <= r["distancia_km"] <= 50.0


def test_perfil_estrutura_e_quantidades():
    v = va.CoordinateValidator(raio_km=30.0, limite=5)
    p = v.perfil(-3.1190, -60.0217)
    assert "municipio" in p and "feicoes" in p and "quantidades" in p
    assert p["quantidades"]["pontes"] >= 0
    assert p["municipio"]["nome"] == "Manaus"
    assert all(0.0 <= f["distancia_km"] <= 30.001 for f in p["feicoes"]["pontes"])


def test_confianca_alta_em_area_com_infraestrutura():
    v = va.CoordinateValidator(raio_km=30.0)
    p = v.perfil(-3.1190, -60.0217)
    c = v.confianca(p)
    assert 0 <= c["pontuacao"] <= 100
    assert c["nivel"] in ("alta", "media", "baixa")
    assert "IBGE (malha municipal)" in c["fontes_concordam"]


def test_confianca_baixa_no_oceano():
    v = va.CoordinateValidator(raio_km=30.0)
    p = v.perfil(0.0, -30.0)
    c = v.confianca(p)
    assert c["pontuacao"] <= 5
    assert c["fontes_concordam"] == []


def test_validar_trecho_manaus_rio():
    v = va.CoordinateValidator(raio_km=40.0)
    t = v.validar_trecho((-3.1190, -60.0217), (-22.9068, -43.1729))
    assert t["origem"]["perfil"]["municipio"]["nome"] == "Manaus"
    assert t["destino"]["perfil"]["municipio"]["nome"] == "Rio de Janeiro"
    assert set(t["fontes_comuns"]) <= set(t["origem"]["confianca"]["fontes_concordam"])