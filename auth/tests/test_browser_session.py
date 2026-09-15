# -*- coding: utf-8 -*-
"""Testes de auth/browser_session.py — o NÚCLEO PURO da persistência de sessão no navegador
(serialização base64/JSON e a validação defensiva do que volta da sessionStorage). As chamadas ao
componente `streamlit_js_eval` (salvar/limpar/tentar_restaurar) dependem do navegador e não têm
cobertura automatizada aqui — são fail-open por construção (qualquer erro vira no-op/None)."""
import logging

logging.disable(logging.WARNING)

from auth import browser_session as bs  # noqa: E402


def test_roundtrip_serializar_desserializar():
    _orig = {"user_id": "u1", "email": "a@b.com", "access_token": "AT.123", "refresh_token": "RT.456"}
    _blob = bs._serializar(_orig)
    assert isinstance(_blob, str) and "'" not in _blob and '"' not in _blob  # seguro p/ expressão JS
    assert bs._desserializar(_blob) == _orig


def test_serializar_ignora_campos_extras_e_mantem_o_contrato():
    _blob = bs._serializar({"user_id": "u1", "email": "e", "access_token": "AT", "refresh_token": "RT",
                            "lixo": "nao deve aparecer"})
    _d = bs._desserializar(_blob)
    assert set(_d.keys()) == set(bs._CAMPOS) and "lixo" not in _d


def test_desserializar_rejeita_entradas_invalidas():
    assert bs._desserializar(None) is None
    assert bs._desserializar("") is None
    assert bs._desserializar("@@@nao-base64@@@") is None
    assert bs._desserializar(123) is None


def test_desserializar_rejeita_json_incompleto():
    import base64 as _b64
    import json as _json
    # falta refresh_token -> inválido (não dá pra reidratar sessão)
    _incompleto = _b64.urlsafe_b64encode(
        _json.dumps({"user_id": "u1", "access_token": "AT"}).encode()).decode()
    assert bs._desserializar(_incompleto) is None
    # não-dict -> inválido
    _lista = _b64.urlsafe_b64encode(_json.dumps([1, 2, 3]).encode()).decode()
    assert bs._desserializar(_lista) is None


def test_recurso_ativo_devolve_bool_sem_levantar():
    # sem secrets/componente configurados, nunca deve estourar — só devolver True/False
    assert isinstance(bs.recurso_ativo(), bool)
