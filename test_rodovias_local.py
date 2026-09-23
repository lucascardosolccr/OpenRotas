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


# ---- geo_kdtree: vizinho mais próximo EXATO na esfera (corrige o viés 2D no Sul) --------------
def test_geo_kdtree_distancia_bate_com_haversine():
    import math
    from inteligencia_geoespacial import geo_kdtree as gk
    # dois pontos separados por ~111 km (1° de latitude)
    tree = gk.build([-30.0, -20.0], [-51.0, -47.0])
    i, dk = gk.nearest(tree, -29.9, -51.0)     # perto do 1º ponto
    assert i == 0
    # haversine de referência
    R = 6371.0088
    a = (math.sin(math.radians(0.1) / 2) ** 2)
    hav = 2 * R * math.asin(math.sqrt(a))
    assert abs(dk - hav) < 0.05                 # bate com a geodésica (sub-100 m)


def test_geo_kdtree_escolhe_vizinho_correto_no_sul():
    # No extremo Sul (lat -33, cos≈0.84), caso em que 2D-radiano e 3D DISCORDAM:
    #  A = separado só em longitude por 0.10° → no terreno 0.10°·cos(33)·111 ≈ 9,3 km
    #  B = separado só em latitude por 0.09°  → no terreno 0.09°·111 ≈ 10,0 km
    # No terreno A é mais perto; mas o 2D-radiano (que ignora cos(lat)) veria A "mais longe" (0.10 > 0.09)
    # e escolheria B, errado. O 3D acerta A.
    from inteligencia_geoespacial import geo_kdtree as gk
    tree = gk.build([-33.09, -33.00], [-55.00, -55.10])   # [0]=B (norte), [1]=A (leste)
    i, dk = gk.nearest(tree, -33.00, -55.00)              # consulta na origem
    assert i == 1                                          # 3D escolhe A (o mais próximo no terreno)
    assert dk < 9.6                                        # ~9,3 km


def test_geo_kdtree_fail_open_sem_scipy_no_chamador():
    # o índice de rios devolve None quando o asset/scipy faltam — chamador degrada sem quebrar
    from inteligencia_geoespacial import ana_hidroweb as a
    assert a.rio_mais_proximo_local(-20.0, -30.0) is None   # oceano → None de qualquer forma
