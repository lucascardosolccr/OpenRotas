# -*- coding: utf-8 -*-
"""[RODOVIA DE REFERÊNCIA · local] Índice nacional de rodovias significativas (asset ~1 MB versionado) →
descobre a rodovia mais próxima de um ponto (sigla BR-/estadual, jurisdição, revestimento) sem o Parquet
pesado de 122 MB. Enriquece o contexto rodoviário das rotas. Fail-open."""
from inteligencia_geoespacial import rodovias_local as r


def test_rodovia_mais_proxima_traz_sigla_e_jurisdicao():
    rod = r.rodovia_mais_proxima(-3.119, -60.02)          # Manaus → AM-010
    assert rod is not None
    assert rod["via"] and rod["jurisdicao"]
    assert rod["distancia_km"] <= 5.0
    assert isinstance(rod["revestimento"], str)


def test_rodovia_fora_do_alcance_e_none():
    # meio do Atlântico → nenhuma rodovia dentro do raio
    assert r.rodovia_mais_proxima(-20.0, -30.0, max_km=5.0) is None


def test_indice_carrega_milhares_de_pontos():
    idx = r._indice()
    assert idx is not None
    _rows, _tree = idx
    assert len(_rows) > 10000


def test_enriquecimento_de_rota_recebe_rodovia():
    from inteligencia_geoespacial import enrichment_engine as e
    enr = e.enriquecer_ponto(-15.79, -47.88, raio_km=30, limite=5)   # Brasília
    assert enr.get("rodovia_ref") is not None
    assert enr["rodovia_ref"]["via"]


# ---- Ferrovia de referência (índice local) ---------------------------------------------------
def test_ferrovia_mais_proxima():
    from inteligencia_geoespacial import ferrovias_local as fl
    fer = fl.ferrovia_mais_proxima(-23.55, -46.63)     # São Paulo → há ferrovia perto
    assert fer is not None and fer["via"]
    assert fer["distancia_km"] <= 8.0
    # Amazônia central não tem ferrovia por perto
    assert fl.ferrovia_mais_proxima(-3.119, -60.02, max_km=8.0) is None


def test_enriquecimento_recebe_ferrovia_onde_existe():
    from inteligencia_geoespacial import enrichment_engine as e
    enr = e.enriquecer_ponto(-19.92, -43.94, raio_km=30, limite=5)   # Belo Horizonte
    assert enr.get("ferrovia_ref") is not None
