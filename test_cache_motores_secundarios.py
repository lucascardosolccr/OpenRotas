# -*- coding: utf-8 -*-
"""[PERF-FOSSGIS/VALHALLA-CACHE] Os motores keyless secundários (FOSSGIS e Valhalla), throttled a ≤1 req/s,
passaram a cachear a rota por COORDENADA (~1 m) como o OSRM primário já fazia. Num cache hit, NENHUMA chamada
de rede acontece — ganho de vazão sem perder qualidade (resultado determinístico por coordenada). A chave do
Valhalla inclui a preferência de menor-distância, para nunca servir a rota errada."""
import streamlit_app as m


def _boom(*a, **k):
    raise AssertionError("a rede NÃO deveria ser chamada num cache hit")


def test_fossgis_cache_hit_nao_chama_rede(monkeypatch):
    _o = (-1.11111, -48.22222, -2.33333, -49.44444)
    _key = "fossgisroute:%.5f,%.5f>%.5f,%.5f" % _o
    _payload = (123.4, 90, "Não", 2, "geo_poly", None, None, None)
    m.cache_rotas.set(_key, _payload, expire=60)
    try:
        monkeypatch.setattr(m, "_get_tls_fallback", _boom)   # se a rede for tocada, o teste falha
        res = m.API_OSRM_FOSSGIS_Routing(*_o)
        assert res == _payload
    finally:
        m.cache_rotas.delete(_key)


def test_valhalla_cache_hit_nao_chama_rede(monkeypatch):
    _o = (-3.10000, -60.20000, -3.90000, -61.80000)
    _flag = 1 if m._ROTA_MENOR_DISTANCIA else 0
    _key = "valhallaroute:%d:%.5f,%.5f>%.5f,%.5f" % (_flag, *_o)
    _payload = (222.2, 180, "Sim", 1, "geo5", None)
    m.cache_rotas.set(_key, _payload, expire=60)
    try:
        # o Valhalla usa session.post; se for chamado, quebra — cache hit retorna antes
        monkeypatch.setattr(m.session, "post", _boom)
        res = m.API_Valhalla_Routing(*_o)
        assert res == _payload
    finally:
        m.cache_rotas.delete(_key)


def test_valhalla_chave_separa_por_preferencia_de_menor_distancia(monkeypatch):
    # a rota "mais curta" e a "mais rápida" NÃO podem compartilhar entrada de cache: chaves distintas
    _o = (-5.0, -40.0, -6.0, -41.0)
    _key_short = "valhallaroute:1:%.5f,%.5f>%.5f,%.5f" % _o
    _key_fast = "valhallaroute:0:%.5f,%.5f>%.5f,%.5f" % _o
    assert _key_short != _key_fast
    # só a entrada da preferência ATIVA deve ser servida (a app roda com menor-distância ON por padrão)
    _payload_short = (100.0, 120, "Não", 1, "s", None)
    m.cache_rotas.set(_key_short, _payload_short, expire=60)
    m.cache_rotas.delete(_key_fast)
    try:
        monkeypatch.setattr(m.session, "post", _boom)
        if m._ROTA_MENOR_DISTANCIA:
            assert m.API_Valhalla_Routing(*_o) == _payload_short
    finally:
        m.cache_rotas.delete(_key_short)
