# -*- coding: utf-8 -*-
"""[MENOR-ROTA-VALHALLA] O Valhalla é o ÚNICO motor de menor-distância que NÃO exige chave (público FOSSGIS
ou self-host). Antes, `API_Valhalla_Routing` mandava sempre `costing: auto` SEM opções → rota mais RÁPIDA,
ignorando a preferência de menor distância que ORS e GraphHopper já honravam. `_valhalla_costing_options`
fecha esse vão: liga `shortest: true` (opção keyless do Valhalla 3.x que usa a DISTÂNCIA como único custo)
quando a preferência está ativa. Como o vencedor é o MÍNIMO entre motores e o OSRM/rápido sempre concorre,
a rota shortest (que nunca é mais longa) só pode reduzir a km — monotônico. Estes testes travam o contrato."""
import streamlit_app as m


def test_sem_preferencia_payload_identico_ao_historico():
    # sem menor_distancia → {} → o payload do Valhalla fica byte-a-byte o histórico (zero regressão)
    assert m._valhalla_costing_options(False) == {}
    assert m._valhalla_costing_options(None) == {}
    assert m._valhalla_costing_options(0) == {}


def test_com_preferencia_liga_shortest_keyless():
    _co = m._valhalla_costing_options(True)
    assert _co == {"auto": {"shortest": True}}
    # é a opção do costing 'auto' (a que a chamada usa), keyless
    assert _co["auto"]["shortest"] is True


def test_default_da_app_e_menor_distancia_on():
    # a app passou a pedir menor distância por padrão (objetivo declarado do usuário: "menor rota")
    assert m._ROTA_MENOR_DISTANCIA is True
    # e, com o default ON, o costing do Valhalla já sai com shortest ligado
    assert m._valhalla_costing_options(m._ROTA_MENOR_DISTANCIA) == {"auto": {"shortest": True}}
