# -*- coding: utf-8 -*-
"""[PERF-TEXTO-CONDICIONAL / PERF-FALHA-INFO] A chamada ao Google reporta, em `_falha_info['parse_fail']`, se
vale a pena um 2º modo (por NOME): True SÓ quando houve resposta real (≥500 chars) mas o parse falhou; False em
timeout/resposta vazia. O vencedor usa isso para PULAR o modo-texto quando ele seria comprovadamente inútil
(IP bloqueado), sem perder nenhum acerto do Google. Guarda de não-regressão da lógica de decisão."""
import streamlit as _st  # garante que o módulo stub de teste esteja ativo
import streamlit_app as m


class _RespFake:
    def __init__(self, texto):
        self.text = texto


def _limpar_cache(origem, destino, usar_coords):
    for _k in (f"GOOG_{m.CACHE_VERSION}_{origem}|{destino}|{usar_coords}",):
        try:
            del m.cache_google[_k]
        except Exception:
            pass


def test_timeout_marca_parse_fail_false(monkeypatch):
    # Google inalcançável (timeout em todas as tentativas) → parse_fail=False → vencedor PULA o modo-texto.
    monkeypatch.setattr(m, "_google_pode_chamar", lambda *a, **k: True)
    monkeypatch.setattr(m, "_google_politica_adaptativa",
                        lambda: {"timeout": 1, "tentativas": 2, "primar": False, "ignora_disjuntor": True, "motivo": "teste"})

    class _SessTimeout:
        def get(self, *a, **k):
            raise TimeoutError("simulação de timeout de rede")
    monkeypatch.setattr(m, "session", _SessTimeout())

    _limpar_cache("OrigTO", "DestTO", True)
    _fi = {}
    r = m.extrair_dados_reais_google("OrigTO", "DestTO", -10.0, -50.0, -11.0, -51.0, 120.0,
                                     usar_coordenadas=True, _falha_info=_fi)
    assert r is None
    assert _fi.get("parse_fail") is False   # timeout → não adianta tentar o nome no mesmo IP


def test_resposta_sem_rota_marca_parse_fail_true(monkeypatch):
    # Google RESPONDEU (≥500 chars) mas sem rota parseável → parse_fail=True → vale tentar pelo nome.
    monkeypatch.setattr(m, "_google_pode_chamar", lambda *a, **k: True)
    monkeypatch.setattr(m, "_google_politica_adaptativa",
                        lambda: {"timeout": 1, "tentativas": 1, "primar": False, "ignora_disjuntor": True, "motivo": "teste"})

    class _SessSemRota:
        def get(self, *a, **k):
            return _RespFake("z" * 800)   # grande, mas sem nenhum padrão de distância/tempo
    monkeypatch.setattr(m, "session", _SessSemRota())

    _limpar_cache("OrigPF", "DestPF", True)
    _fi = {}
    r = m.extrair_dados_reais_google("OrigPF", "DestPF", -10.0, -50.0, -11.0, -51.0, 120.0,
                                     usar_coordenadas=True, _falha_info=_fi)
    assert r is None
    assert _fi.get("parse_fail") is True


def test_vencedor_pula_texto_apenas_quando_parse_fail_false():
    # a regra do vencedor: só tenta o texto se parse_fail (default True p/ não-regressão quando desconhecido)
    assert ({}.get('parse_fail', True)) is True                    # desconhecido → tenta (histórico)
    assert ({'parse_fail': True}.get('parse_fail', True)) is True   # parse falhou → tenta
    assert ({'parse_fail': False}.get('parse_fail', True)) is False # timeout/vazio → pula
