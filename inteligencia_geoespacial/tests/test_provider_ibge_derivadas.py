# inteligencia_geoespacial/tests/test_provider_ibge_derivadas.py
import pytest

from inteligencia_geoespacial import bases_locais as bl
from inteligencia_geoespacial.providers import (
    IBGEDerivadasProvider,
    ProviderFactory,
    ProviderValidationException,
    wkb_para_geojson,
)

DATAS_DISPONIVEIS = bool(bl.camadas_disponiveis())


# ---------------------------------------------------------------------- WKB
def test_wkb_ponto_eh_geojson_point():
    df = bl._ler("eclusas", colunas=["geometry_wkb", "lon", "lat"])
    geo = wkb_para_geojson(df.iloc[0].geometry_wkb)
    assert geo["type"] == "Point"
    assert len(geo["coordinates"]) == 2


def test_wkb_linha_eh_geojson_linestring():
    df = bl._ler("hidrovias", colunas=["geometry_wkb"])
    geo = wkb_para_geojson(df.iloc[0].geometry_wkb)
    assert geo["type"] == "LineString"
    assert isinstance(geo["coordinates"], list)


def test_wkb_none():
    assert wkb_para_geojson(None) is None


# ------------------------------------------------------------------ provider
@pytest.mark.skipif(not DATAS_DISPONIVEIS, reason="Camadas derivadas ausentes.")
def test_fetch_travessias_balsa_manaus():
    p = IBGEDerivadasProvider(source_id="ibge_der_travessias")
    r = p.fetch(lat=-3.119, lon=-60.0217, camada="travessias",
                raio_km=60, limite=10, filtros={"tipotraves": "Balsa"})
    assert isinstance(r, list)
    assert r and all("geometry_wkb" in x for x in r)
    p.validate(r)


@pytest.mark.skipif(not DATAS_DISPONIVEIS, reason="Camadas derivadas ausentes.")
def test_fetch_municipios_point_in_polygon():
    p = IBGEDerivadasProvider(source_id="ibge_der_municipios")
    r = p.fetch(lat=-23.5505, lon=-46.6333, camada="municipios")
    assert len(r) == 1
    assert r[0]["nome"] == "São Paulo"


def test_fetch_sem_coordenadas_levanta():
    p = IBGEDerivadasProvider()
    with pytest.raises(ProviderValidationException):
        p.fetch(camada="pontes")


def test_validate_rejeita_dado_invalido():
    p = IBGEDerivadasProvider()
    with pytest.raises(ProviderValidationException):
        p.validate([{"foo": 1}])


@pytest.mark.skipif(not DATAS_DISPONIVEIS, reason="Camadas derivadas ausentes.")
def test_transform_padroniza_esquema():
    p = IBGEDerivadasProvider(source_id="ibge_der_pontes")
    raw = p.fetch(lat=-3.119, lon=-60.0217, camada="pontes", raio_km=30, limite=3)
    t = p.transform(raw)
    assert len(t) == len(raw)
    for item in t:
        assert set(["id", "nome", "coordenadas", "geometria", "metadados", "source"]).issubset(item)
        assert item["source"] == "ibge_der_pontes"
        assert item["coordenadas"][0] == pytest.approx(-60.0217, abs=1.5)
        assert item["distancia_km"] >= 0


@pytest.mark.skipif(not DATAS_DISPONIVEIS, reason="Camadas derivadas ausentes.")
def test_to_geojson_featurecollection():
    p = IBGEDerivadasProvider(source_id="ibge_der_pontes")
    raw = p.fetch(lat=-3.119, lon=-60.0217, camada="pontes", raio_km=30, limite=3)
    fc = p.to_geojson(p.transform(raw))
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == len(raw)
    for f in fc["features"]:
        assert f["geometry"]["type"] in ("Point", "LineString", "Polygon")


@pytest.mark.skipif(not DATAS_DISPONIVEIS, reason="Camadas derivadas ausentes.")
def test_fetch_with_cache_consistente(tmp_path):
    p = IBGEDerivadasProvider(source_id="ibge_der_eclusas", cache_dir=tmp_path)
    a = p.fetch_with_cache(lat=-29.9, lon=-51.2, camada="eclusas", raio_km=120, limite=5)
    b = p.fetch_with_cache(lat=-29.9, lon=-51.2, camada="eclusas", raio_km=120, limite=5)
    assert a == b
    assert p.fetch_count == 1


# -------------------------------------------------------------------- factory
def test_factory_ibge_der_usa_ibge_derivadas():
    p = ProviderFactory.criar("ibge_der_pontes")
    assert isinstance(p, IBGEDerivadasProvider)
    assert p.source_id == "ibge_der_pontes"
    assert p.camada_padrao == "pontes"


def test_factory_unknown_source_levanta():
    with pytest.raises(Exception):
        ProviderFactory.criar("fonte_desconhecida_xyz")


def test_factory_lista():
    nomes = ProviderFactory.lista()
    assert "ibge_der_*" in nomes