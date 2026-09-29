# -*- coding: utf-8 -*-
"""[SINGLE-FLIGHT HALF-OPEN] Disjuntor por motor: no estado de recuperação (meio_aberto) só UMA chamada de
teste passa por ciclo — as demais threads pulam na hora, evitando a "manada" de workers batendo juntos num
motor caído (cada um pagando o timeout inteiro). Transparente quando o motor está são. Determinístico via
`agora=` (relógio injetado). Cada teste isola o estado do motor usado."""
import streamlit_app as m


def _reset(nome):
    with m._LOCK_MOTOR_CB:
        m._MOTOR_CB_ESTADO.pop(nome, None)


def test_saudavel_libera_todas_as_chamadas():
    _reset("T_HEALTHY")
    # fechado: qualquer nº de checagens concorrentes é permitido (single-flight não interfere)
    assert all(m._motor_pode_chamar("T_HEALTHY", agora=1000.0) for _ in range(10))


def test_abre_apos_3_falhas_e_pula_todas():
    _reset("T_OPEN")
    for _ in range(3):
        m._motor_registrar("T_OPEN", False, agora=1000.0)
    # aberto: dentro do cooldown, todas as chamadas são puladas
    assert m._motor_pode_chamar("T_OPEN", agora=1001.0) is False
    assert m._motor_pode_chamar("T_OPEN", agora=1005.0) is False


def test_meio_aberto_permite_apenas_um_probe_por_ciclo():
    _reset("T_PROBE")
    for _ in range(3):
        m._motor_registrar("T_PROBE", False, agora=1000.0)
    _t = 1000.0 + 45.0 + 1.0   # depois do cooldown → entra em meio_aberto
    # 1º chamador leva o teste; os concorrentes seguintes (mesmo ciclo) são pulados
    assert m._motor_pode_chamar("T_PROBE", agora=_t) is True
    assert m._motor_pode_chamar("T_PROBE", agora=_t + 0.1) is False
    assert m._motor_pode_chamar("T_PROBE", agora=_t + 0.2) is False


def test_probe_sucesso_fecha_e_reabre_geral():
    _reset("T_OK")
    for _ in range(3):
        m._motor_registrar("T_OK", False, agora=2000.0)
    _t = 2000.0 + 45.0 + 1.0
    assert m._motor_pode_chamar("T_OK", agora=_t) is True     # probe reservado
    m._motor_registrar("T_OK", True, agora=_t + 1.0)          # teste OK → fecha
    # fechado de novo: todos liberados
    assert all(m._motor_pode_chamar("T_OK", agora=_t + 2.0) for _ in range(5))


def test_probe_falha_reabre_e_proximo_ciclo_testa_de_novo():
    _reset("T_REOPEN")
    for _ in range(3):
        m._motor_registrar("T_REOPEN", False, agora=3000.0)
    _t1 = 3000.0 + 45.0 + 1.0
    assert m._motor_pode_chamar("T_REOPEN", agora=_t1) is True    # 1º probe
    m._motor_registrar("T_REOPEN", False, agora=_t1 + 1.0)        # teste falhou → reabre
    assert m._motor_pode_chamar("T_REOPEN", agora=_t1 + 2.0) is False   # dentro do novo cooldown
    _t2 = _t1 + 1.0 + 45.0 + 1.0                                  # após novo cooldown
    assert m._motor_pode_chamar("T_REOPEN", agora=_t2) is True    # novo ciclo → testa de novo (1×)
    assert m._motor_pode_chamar("T_REOPEN", agora=_t2 + 0.1) is False


def test_probe_ttl_expira_se_resultado_nunca_registrar():
    _reset("T_TTL")
    for _ in range(3):
        m._motor_registrar("T_TTL", False, agora=4000.0)
    _t = 4000.0 + 45.0 + 1.0
    assert m._motor_pode_chamar("T_TTL", agora=_t) is True        # reserva o probe (sem registrar resultado)
    assert m._motor_pode_chamar("T_TTL", agora=_t + 1.0) is False  # ainda em andamento
    # passado o TTL do probe, o próximo ciclo pode testar de novo (defensivo contra registrar perdido)
    assert m._motor_pode_chamar("T_TTL", agora=_t + m._MOTOR_PROBE_TTL_S + 0.1) is True
