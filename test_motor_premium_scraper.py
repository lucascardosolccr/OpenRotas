# -*- coding: utf-8 -*-
"""[MOTOR-PREMIUM-CONFIG - 456ª geração] Quando um motor viário CONFIÁVEL está configurado (chave ORS/
GraphHopper, ou OSRM/GraphHopper/Valhalla self-hosted), o scraper keyless do Google passa a FAST-FAIL
(não paga mais a espera paciente por rota). SEM nenhum motor premium configurado, nada muda: o scraper
segue PACIENTE quando o Google está saudável — participação do Google 100% preservada no padrão.

Trava a não-regressão: o padrão (sem motor premium) continua idêntico, e o override manual 'google_agressivo'
continua tendo prioridade sobre tudo."""
import streamlit_app as m


def _isolar_globais(monkeypatch):
    """Zera os sinais de 'motor premium' para um ponto de partida limpo e determinístico."""
    monkeypatch.setattr(m, "ORS_API_KEY", "", raising=False)
    monkeypatch.setattr(m, "GRAPHHOPPER_API_KEY", "", raising=False)
    monkeypatch.setattr(m, "OSRM_URL", "http://router.project-osrm.org", raising=False)
    monkeypatch.setattr(m, "GRAPHHOPPER_URL", "https://graphhopper.com/api/1", raising=False)
    monkeypatch.setattr(m, "VALHALLA_URL", "https://valhalla1.openstreetmap.de", raising=False)


def test_premium_configurado_detecta_cada_fonte(monkeypatch):
    _isolar_globais(monkeypatch)
    assert m._motor_premium_configurado() is False  # só os públicos keyless → NÃO conta

    monkeypatch.setattr(m, "ORS_API_KEY", "chave-ors", raising=False)
    assert m._motor_premium_configurado() is True
    monkeypatch.setattr(m, "ORS_API_KEY", "", raising=False)

    monkeypatch.setattr(m, "GRAPHHOPPER_API_KEY", "chave-gh", raising=False)
    assert m._motor_premium_configurado() is True
    monkeypatch.setattr(m, "GRAPHHOPPER_API_KEY", "", raising=False)

    monkeypatch.setattr(m, "OSRM_URL", "http://meu-osrm-brasil:5000", raising=False)
    assert m._motor_premium_configurado() is True
    monkeypatch.setattr(m, "OSRM_URL", "http://router.project-osrm.org", raising=False)

    monkeypatch.setattr(m, "VALHALLA_URL", "https://valhalla.meuservidor.com", raising=False)
    assert m._motor_premium_configurado() is True


def test_padrao_sem_premium_mantem_paciencia(monkeypatch):
    """Sem motor premium e com Google saudável → PACIENTE (idêntico a hoje). Não-regressão."""
    _isolar_globais(monkeypatch)
    monkeypatch.setattr(m, "_ler_flag_runtime", lambda *_a, **_k: False)  # sem override manual
    monkeypatch.setattr(m, "_google_pode_chamar", lambda *_a, **_k: True)  # disjuntor saudável
    pol = m._google_politica_adaptativa()
    assert pol["tentativas"] == 3 and pol["timeout"] == 8 and pol["primar"] is True


def test_premium_configurado_forca_fast_fail(monkeypatch):
    """Com motor premium (ex.: chave ORS) e Google saudável → FAST-FAIL, mesmo com o disjuntor fechado."""
    _isolar_globais(monkeypatch)
    monkeypatch.setattr(m, "_ler_flag_runtime", lambda *_a, **_k: False)
    monkeypatch.setattr(m, "_google_pode_chamar", lambda *_a, **_k: True)  # saudável
    monkeypatch.setattr(m, "ORS_API_KEY", "chave-ors", raising=False)
    pol = m._google_politica_adaptativa()
    assert pol["tentativas"] == 1 and pol["timeout"] == 4 and pol["primar"] is False
    assert "premium" in pol["motivo"].lower()


def test_override_manual_vence_premium(monkeypatch):
    """O override manual 'google_agressivo' tem prioridade sobre o gate premium (paciência forçada)."""
    _isolar_globais(monkeypatch)
    monkeypatch.setattr(m, "ORS_API_KEY", "chave-ors", raising=False)  # premium presente
    monkeypatch.setattr(m, "_ler_flag_runtime", lambda *_a, **_k: True)  # override ligado
    pol = m._google_politica_adaptativa()
    assert pol["ignora_disjuntor"] is True and pol["tentativas"] == 3  # paciência forçada vence
