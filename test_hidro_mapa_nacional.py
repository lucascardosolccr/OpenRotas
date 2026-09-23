# -*- coding: utf-8 -*-
"""[MAPA HIDROGRÁFICO NACIONAL] O mapa precisa COBRIR O BRASIL INTEIRO. Antes ele só desenhava uma janela e
truncava por ordem de arquivo (regiões inteiras sumiam) — e a drenagem densa (451 MB) nem está no repo (é
baixada sob demanda), então na nuvem o mapa ficava vazio. Agora há um OVERVIEW nacional pré-computado e
versionado no repo (amostragem espacial: os rios mais extensos por célula de grade), que cobre de Roraima ao
Chuí e funciona sempre. Estes testes travam essa cobertura e o recorte regional de fallback."""
import itertools
import streamlit_app as m


def _spread(linhas):
    pts = list(itertools.chain.from_iterable(linhas))
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    return min(lats), max(lats), min(lons), max(lons)


def test_overview_nacional_carrega_e_cobre_o_brasil_inteiro():
    ov = m._hidrografia_overview_nacional()
    assert ov, "o overview nacional (asset versionado) deve carregar"
    assert ov["n_rios"] > 1000, "poucos rios para uma visão nacional"
    assert ov["n_massas"] > 100
    la0, la1, lo0, lo1 = _spread(ov["rios"])
    # extremos do país: norte (Roraima ~ +5), sul (Chuí ~ -33), oeste (Acre ~ -73), leste (~ -35)
    assert la1 > 3.5, "não alcança o extremo NORTE (Roraima/Amapá)"
    assert la0 < -29.0, "não alcança o extremo SUL (Rio Grande do Sul)"
    assert lo0 < -66.0, "não alcança o extremo OESTE (Acre/Amazonas)"
    assert lo1 > -40.0, "não alcança o extremo LESTE (litoral nordeste)"


def test_overview_coordenadas_sao_tuplas_latlon_plausiveis():
    ov = m._hidrografia_overview_nacional()
    p = ov["rios"][0][0]
    assert isinstance(p, tuple) and len(p) == 2
    # dentro do Brasil continental
    for _ln in ov["rios"][:200]:
        for (_la, _lo) in _ln:
            assert -34.5 <= _la <= 6.0 and -74.5 <= _lo <= -34.0


def test_recorte_regional_nao_fica_vazio_sem_o_parquet_pesado():
    # o recorte do overview cobre qualquer janela do país, mesmo sem baixar a drenagem densa
    for (la0, la1, lo0, lo1) in [(-33.0, -26.0, -57.0, -49.0),   # Sul
                                 (-6.0, 0.5, -64.0, -56.0),      # Norte/Amazônia
                                 (-12.0, -6.0, -44.0, -36.0)]:   # Nordeste/São Francisco
        rec = m._hidrografia_overview_recortado(la0, la1, lo0, lo1)
        assert rec and rec["n_rios"] > 0, f"janela {la0,la1,lo0,lo1} ficou sem rios"


def test_recorte_no_meio_do_atlantico_e_vazio():
    # oceano aberto (longe da costa) → sem hidrografia terrestre, mas sem erro
    rec = m._hidrografia_overview_recortado(-20.0, -18.0, -30.0, -28.0)
    assert rec is not None and rec["n_rios"] == 0
