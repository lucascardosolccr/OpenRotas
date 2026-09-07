# inteligencia_geoespacial/tests/test_bases_locais.py
import pytest

from inteligencia_geoespacial import bases_locais as bl

DATAS_DISPONIVEIS = bool(bl.camadas_disponiveis())

pytestmark = pytest.mark.skipif(
    not DATAS_DISPONIVEIS,
    reason="Camadas derivadas ausentes. Gere com construir_bases_locais_ibge.py",
)


def test_camadas_carregam():
    for c in bl.camadas_disponiveis():
        df = bl._ler(c, colunas=["tipo_geom", "lon", "lat", "xmin", "ymin", "xmax", "ymax"])
        assert len(df) > 0
        assert (df.lon >= -76).all() and (df.lon <= -25).all()
        assert (df.lat >= -35).all() and (df.lat <= 6).all()


def test_municipio_do_ponto_sao_paulo():
    r = bl.municipio_do_ponto(-23.5505, -46.6333)
    assert r["nome"] == "São Paulo"
    assert r["geocodigo"] == "3550308"


def test_municipio_do_ponto_fora_do_brasil():
    assert bl.municipio_do_ponto(0.0, -30.0) == {}


def test_mais_proximos_pontes_manaus():
    r = bl.mais_proximos("pontes", -60.0217, -3.1190, raio_km=30, limite=5)
    assert 0 < len(r) <= 5
    assert all(0 <= x["distancia_km"] <= 30 for x in r)


def test_mais_proximos_filtro_balsa():
    r = bl.mais_proximos("travessias", -53.1, -22.9, raio_km=90, limite=5,
                         filtros={"tipotraves": "Balsa"})
    assert any(x["nome"] == "Pr-180/Sp-040" for x in r)


def test_wkb_pontos_coerentes():
    df = bl._ler("eclusas", colunas=["geometry_wkb", "lon", "lat"])
    for _, row in df.head(20).iterrows():
        pts = bl._deco_wkb(row.geometry_wkb)
        assert isinstance(pts, tuple)
        assert abs(pts[0] - row.lon) < 1e-6
        assert abs(pts[1] - row.lat) < 1e-6


def test_linhas_wkb():
    df = bl._ler("hidrovias", colunas=["geometry_wkb"])
    assert all(isinstance(bl._deco_wkb(w), list) for w in df.geometry_wkb.head(10))