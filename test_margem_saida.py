# -*- coding: utf-8 -*-
"""Rede de segurança para a MARGEM DE SAÍDA RECOMENDADA (MARGEM-SAIDA): converte tempo de viagem + risco
operacional numa folga de segurança e no horário de saída sugerido. Portões de exame fecham no horário —
o cálculo tem de ser conservador, explicável e robusto. Núcleo 100% PURO.

Roda via pytest a partir da raiz: `python3 -m pytest test_margem_saida.py`."""
import logging

logging.disable(logging.WARNING)

import pandas as pd  # noqa: E402

import streamlit_app as m  # noqa: E402


def test_secao_html_relatorio():
    df = pd.DataFrame([
        {"Municipio Origem": "Barcelos", "Municipio Destino": "Manaus", "Tempo": "6 h 30 min",
         "Risco Operacional": "crítico (78)", "Margem de Saída (min)": 150, "Antecedência Recomendada": "9h00"},
        {"Municipio Origem": "Careiro", "Municipio Destino": "Manaus", "Tempo": "1 h",
         "Risco Operacional": "baixo (10)", "Margem de Saída (min)": 36, "Antecedência Recomendada": "1h36"},
    ])
    h = m._secao_risco_margem_html(df)
    assert h and "Antecedência" in h
    assert "Barcelos" in h and "Manaus" in h
    # ordenado por maior margem → a rota crítica (150 min) aparece antes da baixa (36 min)
    assert h.index("Barcelos") < h.index("Careiro")


def test_secao_html_sem_colunas_retorna_vazio():
    assert m._secao_risco_margem_html(pd.DataFrame([{"Distancia": 10}])) == ""
    assert m._secao_risco_margem_html(pd.DataFrame()) == ""


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
    # viagem de 20h (1200 min): 10% = 120, mas o teto é 60. + descanso (teto 45).
    r = m._margem_saida_recomendada(1200, risco=None)
    # base 30 + teto proporcional 60 + teto descanso 45 = 135
    assert r["margem_min"] == 135


def test_descanso_em_viagem_longa():
    curta = m._margem_saida_recomendada(120, risco=None)   # 2h: sem descanso
    longa = m._margem_saida_recomendada(300, risco=None)    # 5h: com descanso
    assert not any("descanso" in c["fator"].lower() for c in curta["componentes"])
    assert any("descanso" in c["fator"].lower() for c in longa["componentes"])
    assert longa["margem_min"] > curta["margem_min"]


def test_min_para_hhmm():
    assert m._min_para_hhmm(45) == "45 min"
    assert m._min_para_hhmm(96) == "1h36"
    assert m._min_para_hhmm(120) == "2h00"
    assert m._min_para_hhmm(None) == ""
    assert m._min_para_hhmm(-5) == ""


def test_margem_de_fatos_para_planilha():
    r = m._margem_de_fatos(dist_viaria_km=250.0, dist_reta_km=120.0, tempo_min=180,
                           balsa=True, n_travessias=1, hora_prova="13:00")
    assert r["margem_min"] > 0
    assert r["lead_total_min"] >= 180
    assert r["margem_rotulo"]           # formato HhMM/min
    assert r["risco_nivel"] in ("baixo", "moderado", "alto", "crítico")
    assert isinstance(r["risco_score"], int)
    assert r["horario_saida"]           # calculado a partir da hora da prova


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
