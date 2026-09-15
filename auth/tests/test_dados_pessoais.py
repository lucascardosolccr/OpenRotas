# -*- coding: utf-8 -*-
"""Testes de auth/dados_pessoais.py — o NÚCLEO PURO da portabilidade LGPD (montagem do pacote e
serialização JSON, com remoção defensiva de campos sensíveis). A coleta na rede (`coletar`) usa os
caminhos com RLS do auth_service e é fail-open — sem cobertura automatizada aqui."""
import json
import logging

logging.disable(logging.WARNING)

from auth import dados_pessoais as dp  # noqa: E402


def test_montar_pacote_estrutura_e_resumo():
    p = dp.montar_pacote(
        {"user_id": "u1", "email": "a@b.com"},
        perfil={"nome_completo": "Fulano", "telefone": "119..."},
        anotacoes=[{"titulo": "x"}, {"titulo": "y"}],
        estudos=[{"nome": "estudo 1"}],
        recebidos=[],
        gerado_em="2026-01-01T00:00:00",
    )
    assert p["titular"] == {"user_id": "u1", "email": "a@b.com"}
    assert p["resumo"] == {"estudos_salvos": 1, "anotacoes": 2, "estudos_recebidos": 0}
    assert p["gerado_em"] == "2026-01-01T00:00:00"
    assert "LGPD" in p["aviso_lgpd"] and "Art. 18" in p["aviso_lgpd"]
    assert p["perfil"]["nome_completo"] == "Fulano"


def test_montar_pacote_remove_campos_sensiveis():
    p = dp.montar_pacote(
        {"user_id": "u1", "email": "a@b.com"},
        perfil={"nome_completo": "F", "access_token": "SEGREDO", "senha_hash": "x", "api_key": "k"},
        anotacoes=[{"titulo": "t", "refresh_token": "RT"}],
        estudos=[], recebidos=[],
    )
    assert "access_token" not in p["perfil"] and "senha_hash" not in p["perfil"]
    assert "api_key" not in p["perfil"]
    assert "refresh_token" not in p["anotacoes"][0]
    # e não escapa na serialização
    _txt = dp.serializar_json(p).decode("utf-8")
    assert "SEGREDO" not in _txt and "RT" not in _txt


def test_montar_pacote_defensivo_com_none():
    p = dp.montar_pacote(None, perfil=None, anotacoes=None, estudos=None, recebidos=None)
    assert p["perfil"] == {} and p["estudos_salvos"] == [] and p["anotacoes"] == []
    assert p["resumo"] == {"estudos_salvos": 0, "anotacoes": 0, "estudos_recebidos": 0}
    assert p["titular"] == {"user_id": "", "email": ""}


def test_sanear_datas_e_tipos_exoticos():
    from datetime import datetime
    from decimal import Decimal
    _s = dp._sanear({"quando": datetime(2026, 1, 2, 3, 4, 5), "valor": Decimal("1.5"),
                     "lista": [Decimal("2"), "ok"]})
    assert _s["quando"] == "2026-01-02T03:04:05"
    assert _s["valor"] == "1.5" and _s["lista"] == ["2", "ok"]


def test_serializar_json_valido_e_utf8():
    p = dp.montar_pacote({"user_id": "u1", "email": "a@b.com"},
                         perfil={"nome": "Ação Coração"}, anotacoes=[], estudos=[], recebidos=[])
    _b = dp.serializar_json(p)
    assert isinstance(_b, bytes)
    _d = json.loads(_b.decode("utf-8"))          # round-trip válido
    assert _d["perfil"]["nome"] == "Ação Coração"  # acentos preservados
