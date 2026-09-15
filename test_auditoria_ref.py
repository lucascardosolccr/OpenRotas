# -*- coding: utf-8 -*-
"""Rede de segurança para a AUDITORIA DA DISTÂNCIA DA REFERÊNCIA (AUDITORIA-REF-IMPOSSIVEL): aponta e
explica quando a distância do estudo de referência é fisicamente impossível (menor que a linha reta
geodésica, o piso físico absoluto). Núcleo 100% PURO — fixa o contrato, os limiares e a robustez.

Roda: `python3 -m pytest test_auditoria_ref.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402


def test_menor_que_a_linha_reta_e_impossivel():
    r = m._auditar_distancia_referencia(dist_ref=100.0, reta_ref_km=180.0,
                                        origem="A", destino_ref="B")
    assert r["veredito"] == "impossivel"
    assert r["rotulo"].startswith("IMPOSSÍVEL")
    assert "180" in r["explicacao"] and "100" in r["explicacao"]
    assert abs(r["deficit_km"] - 80.0) < 0.1


def test_distancia_nula_para_municipios_distintos_e_impossivel():
    r = m._auditar_distancia_referencia(dist_ref=0.0, reta_ref_km=120.0)
    assert r["veredito"] == "impossivel"
    assert "nula" in r["rotulo"].lower()


def test_praticamente_igual_a_reta_e_implausivel():
    # 102 km vs 100 de reta → fator 1.02 (< 1.05) → implausível
    r = m._auditar_distancia_referencia(dist_ref=102.0, reta_ref_km=100.0)
    assert r["veredito"] == "implausivel"
    assert r["rotulo"].startswith("Implausível")


def test_distancia_rodoviaria_normal_e_plausivel():
    # 260 km vs 180 de reta → fator 1.44 → plausível
    r = m._auditar_distancia_referencia(dist_ref=260.0, reta_ref_km=180.0)
    assert r["veredito"] == "plausivel"
    assert r["explicacao"] == ""


def test_tolerancia_nao_marca_igual_a_reta_como_impossivel():
    # exatamente igual à reta não deve ser 'impossivel' (é implausível, não impossível)
    r = m._auditar_distancia_referencia(dist_ref=200.0, reta_ref_km=200.0)
    assert r["veredito"] != "impossivel"


def test_corroboracao_com_rota_da_app_entra_na_explicacao():
    r = m._auditar_distancia_referencia(dist_ref=50.0, reta_ref_km=180.0, dist_app_viaria=210.0)
    assert "210" in r["explicacao"]  # menciona a rota real medida pela app


def test_unidade_trocada_metros_como_km():
    # 200000 "km" quando a reta é 180 km → fator ~1111 → impossível por troca de unidade
    r = m._auditar_distancia_referencia(dist_ref=200000.0, reta_ref_km=180.0)
    assert r["veredito"] == "impossivel"
    assert "unidade" in r["rotulo"].lower()
    assert "METROS" in r["explicacao"] or "metros" in r["explicacao"].lower()


def test_grosseiramente_inflada():
    # 40000 km entre municípios cuja reta é 180 km → fator ~222 (fora da faixa de troca de unidade)
    r = m._auditar_distancia_referencia(dist_ref=40000.0, reta_ref_km=180.0)
    assert r["veredito"] == "impossivel"
    assert "inflada" in r["rotulo"].lower()


def test_reta_curta_nao_dispara_inflacao_falsa():
    # reta < 3 km (salto intraurbano): mesmo fator alto NÃO é marcado como inflado impossível
    r = m._auditar_distancia_referencia(dist_ref=200.0, reta_ref_km=1.0)
    assert r["veredito"] != "impossivel"


def test_robusto_a_entradas_ausentes():
    assert m._auditar_distancia_referencia(None, 100.0)["veredito"] == "nao_avaliavel"
    assert m._auditar_distancia_referencia(100.0, None)["veredito"] == "nao_avaliavel"
    assert m._auditar_distancia_referencia(100.0, 0.0)["veredito"] == "nao_avaliavel"


def test_secao_html_lista_impossiveis():
    linhas = [
        {"Origem": "Barra", "UF": "BA", "Destino Referencia": "Bom Jesus",
         "Distancia Referencia": 40.0, "Linha Reta Referencia (km)": 150.0,
         "Distancia Aplicacao": 190.0, "Auditoria Distancia Referencia": "IMPOSSÍVEL — menor que a linha reta",
         "Explicacao Auditoria Referencia": "faltam 110 km abaixo do piso físico"},
        {"Origem": "OK", "UF": "SP", "Destino Referencia": "Campinas",
         "Distancia Referencia": 120.0, "Linha Reta Referencia (km)": 90.0,
         "Auditoria Distancia Referencia": "Plausível", "Explicacao Auditoria Referencia": ""},
    ]
    h = m._secao_ref_impossivel_html(linhas)
    assert h and "Barra" in h and "impossível" in h.lower()
    assert "Campinas" not in h  # o plausível não entra


def test_secao_html_vazia_sem_casos():
    assert m._secao_ref_impossivel_html([{"Auditoria Distancia Referencia": "Plausível"}]) == ""
    assert m._secao_ref_impossivel_html([]) == ""
