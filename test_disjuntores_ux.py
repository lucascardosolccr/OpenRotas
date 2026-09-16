# -*- coding: utf-8 -*-
"""Rede de segurança para a UX dos 'disjuntores' (DISJUNTORES-UX, 457ª geração). Garante que o painel
somente-informativo de saúde dos motores fala em LINGUAGEM SIMPLES (sem o jargão elétrico 'disjuntor'
voltado ao usuário) e continua defensivo. Núcleo puro — não depende de rede nem de Streamlit rodando.

Roda: `python3 -m pytest test_disjuntores_ux.py`."""
import logging

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402


def test_painel_saude_motores_em_linguagem_simples():
    google = {"status": "fechado", "falhas_seguidas": 0}
    motores = {"OSRM": {"status": "aberto", "skips": 7},
               "Valhalla": {"status": "meio_aberto", "skips": 2}}
    h = m._render_disjuntores_status(google, motores)
    assert h and "<table" in h
    # título e estados em português claro, sem o termo técnico "disjuntor" visível ao usuário
    assert "Saúde dos motores de rota" in h
    assert "Ativo" in h and "Suspenso" in h and "Testando" in h
    # o jargão elétrico não vaza para o texto visível (nomes de coluna/legenda)
    assert "disjuntor" not in h.lower()
    assert "Estado do disjuntor" not in h and "cooldown" not in h.lower()
    # colunas em linguagem simples
    assert "Situação" in h and "Chamadas puladas" in h


def test_painel_estado_geral_ativo_quando_ninguem_suspenso():
    h = m._render_disjuntores_status({"status": "fechado", "falhas_seguidas": 0},
                                     {"OSRM": {"status": "fechado", "skips": 0}})
    assert "Todos os motores estão" in h and "ativos" in h
    assert "disjuntor" not in h.lower()


def test_pill_traduz_estados_sem_jargao():
    assert "Ativo" in m._mnil_cb_pill("fechado")
    assert "Suspenso" in m._mnil_cb_pill("aberto") and "cooldown" not in m._mnil_cb_pill("aberto").lower()
    assert "Testando" in m._mnil_cb_pill("meio_aberto")


def test_painel_defensivo_sem_dados():
    # sem motores e com google default ainda desenha (só a linha do Google), nunca levanta
    assert isinstance(m._render_disjuntores_status(None, None), str)
    assert isinstance(m._render_disjuntores_status({}, {}), str)
