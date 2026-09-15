# -*- coding: utf-8 -*-
"""Rede de segurança para a MARGEM DE SAÍDA RECOMENDADA (MARGEM-SAIDA): converte tempo de viagem + risco
operacional numa folga de segurança e no horário de saída sugerido. Portões de exame fecham no horário —
o cálculo tem de ser conservador, explicável e robusto. Núcleo 100% PURO.

Roda via pytest a partir da raiz: `python3 -m pytest test_margem_saida.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402


def test_base_minima_sem_risco():
    r = m._margem_saida_recomendada(60, risco=None)
    # base 30 + 10% de 60 = 6 → 36 de folga; lead = 60 + 36
    assert r["margem_min"] == 36
    assert r["lead_total_min"] == 96


def test_balsa_aumenta_muito_a_folga():
    risco = {"componentes": [{"fator": "Travessia por balsa", "pontos": 30}]}
    sem = m._margem_saida_recomendada(120, risco=None)
    com = m._margem_saida_recomendada(120, risco=risco)
    assert com["margem_min"] > sem["margem_min"]
    assert com["margem_min"] - sem["margem_min"] == 45   # acréscimo fixo da balsa


def test_proporcional_tem_teto():
    # viagem de 20h (1200 min): 10% = 120, mas o teto é 60.
    r = m._margem_saida_recomendada(1200, risco=None)
    # base 30 + teto 60 = 90
    assert r["margem_min"] == 90


def test_robusto_a_tempo_invalido():
    r = m._margem_saida_recomendada(None)
    assert r["margem_min"] >= 30 and r["lead_total_min"] >= 30
    rneg = m._margem_saida_recomendada(-50)
    assert rneg["lead_total_min"] >= 30


def test_horario_saida_basico():
    # prova 13:00, lead 96 min → sair 11:24
    assert m._horario_saida_sugerido("13:00", 96) == "11:24"


def test_horario_saida_cruza_meia_noite():
    # prova 06:00, lead 480 min (8h) → 22:00 do dia anterior
    r = m._horario_saida_sugerido("06:00", 480)
    assert r.startswith("22:00") and "véspera" in r


def test_horario_saida_aceita_formato_h():
    assert m._horario_saida_sugerido("08h30", 90) == "07:00"


def test_horario_saida_invalido_retorna_vazio():
    assert m._horario_saida_sugerido("", 60) == ""
    assert m._horario_saida_sugerido("25:99", 60) == ""
    assert m._horario_saida_sugerido("abc", 60) == ""


def test_resumo_com_e_sem_hora():
    r = m._margem_saida_recomendada(90, risco=None)
    txt = m._margem_saida_resumo(r)
    assert "Antecedência recomendada" in txt
    txt2 = m._margem_saida_resumo(r, hora_prova="13:00")
    assert "sair até" in txt2
    assert m._margem_saida_resumo(None) == ""
