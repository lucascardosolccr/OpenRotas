# -*- coding: utf-8 -*-
"""[PERF-CANDIDATOS] calcular_matriz_competitiva_vetorizada monta topk_map / topk_map_completo por origem
(polos ordenados por linha reta). A extração foi vetorizada (np.round + .tolist em bloco em vez de
int()/float()/round() por elemento) — guarda de regressão: ordenação correta (mais próximo primeiro),
lista completa = todos os polos, top-K = prefixo, e o vencedor/runner-up coerentes com a linha reta."""
import math
import streamlit_app as m


def _haversine(la1, lo1, la2, lo2):
    R = 6371.0088
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1); dl = math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def test_topk_ordenado_e_completo():
    dest = {"O1": (-15.79, -47.88, "Brasília")}
    hubs = {"A": (-15.8, -47.9), "B": (-16.5, -49.3), "C": (-23.5, -46.6), "D": (-3.1, -60.0)}
    out = m.calcular_matriz_competitiva_vetorizada(dest, hubs)
    dest_to_hub, _, _, runner_up, topk, topk_completo = out
    # completo tem TODOS os polos; ordenado por distância crescente
    assert len(topk_completo["O1"]) == 4
    dists = [d for d, _n in topk_completo["O1"]]
    assert dists == sorted(dists)
    # vencedor por linha reta = 1º da lista; runner-up = 2º
    assert dest_to_hub["O1"] == topk_completo["O1"][0][1]
    assert runner_up["O1"][1] == topk_completo["O1"][1][1]
    # top-K é PREFIXO do completo
    assert topk["O1"] == topk_completo["O1"][: len(topk["O1"])]
    # distâncias batem com Haversine independente (arredondado a 3 casas)
    for d, nome in topk_completo["O1"]:
        hla, hlo = hubs[nome]
        assert abs(d - round(_haversine(-15.79, -47.88, hla, hlo), 3)) < 1e-6


def test_um_unico_polo():
    out = m.calcular_matriz_competitiva_vetorizada({"O": (-10.0, -50.0, "x")}, {"UNICO": (-11.0, -51.0)})
    assert out[0]["O"] == "UNICO"
    assert len(out[5]["O"]) == 1 and out[5]["O"][0][1] == "UNICO"


def test_sem_hubs_marca_falha():
    out = m.calcular_matriz_competitiva_vetorizada({"O": (-10.0, -50.0, "x")}, {})
    assert out[0]["O"] == "NENHUM_HUB_VALIDO"
