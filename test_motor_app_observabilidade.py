# -*- coding: utf-8 -*-
"""[MOTOR-APP] O diagnóstico do Comparador mostrava "Motor Aplicação: —" em TODAS as linhas. Causa: a
conciliação lia a chave "Fonte Rota" (sem "da") para o NOSSO estudo, mas a coluna real é "Fonte da Rota"
(com "da") — então "APP · Fonte da Rota" nunca era preenchida e o motor da app ficava sem atribuição. Estes
testes travam o fim do vão: dada a coluna "APP · Fonte da Rota", o motor é atribuído corretamente (não "—")."""
import streamlit_app as m


def test_motor_curto_reconhece_motores():
    assert m._motor_curto("OSRM (menor de 3 alternativas)") == "OSRM"
    assert m._motor_curto("Google Maps (menor distância)") == "Google"
    assert m._motor_curto("Valhalla (shortest)") == "Valhalla"
    assert m._motor_curto("OpenRouteService") == "ORS"
    assert m._motor_curto("Geodésica de Karney") == "Geodésico"
    assert m._motor_curto("") == "—"


def test_fatos_app_atribui_motor_da_fonte_da_rota():
    # com "APP · Fonte da Rota" preenchida, o motor da app deixa de ser "—"
    _f = m._fatos_from_linha_app({"Destino Aplicacao": "Rio Branco", "Distancia Aplicacao": 267.0,
                                  "APP · Fonte da Rota": "OSRM (menor de 3 alternativas)"})
    assert _f["motor"] == "OSRM"


def test_fatos_app_sem_fonte_fica_traco():
    _f = m._fatos_from_linha_app({"Destino Aplicacao": "X", "Distancia Aplicacao": 100.0})
    assert _f["motor"] == "—"
