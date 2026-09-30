# -*- coding: utf-8 -*-
"""[PERF-CONC-FASTGOOGLE] A validação do 2º colocado (concorrente) usa o Google em FAST-FAIL (4s, 1 tentativa),
sem segurar a rota, caindo no OSRM real quando o Google não responde. O vencedor NÃO é afetado (segue com o
Google paciente). Guardas: o parâmetro _fast_fail é aceito, não quebra o caminho de cache, e um cache-hit é
servido sem tocar a rede (nem no modo fast-fail)."""
import streamlit_app as m


def _boom(*a, **k):
    raise AssertionError("a rede NÃO deveria ser chamada num cache-hit")


def test_fast_fail_e_parametro_aceito_e_cache_hit_sem_rede(monkeypatch):
    _o = ("MunOrig", "PoloRunner", -10.0, -50.0, -11.0, -51.0, 120.0)
    _key = f"GOOG_{m.CACHE_VERSION}_MunOrig|PoloRunner|True"
    _payload = (150.0, "2 h 30 min", "http://maps/x", 85, "geo", "embed", "")
    m.cache_google[_key] = _payload
    try:
        monkeypatch.setattr(m, "session", _BoomSession())
        # cache-hit deve retornar sem tocar a rede, com e sem fast-fail
        r1 = m.extrair_dados_reais_google(*_o, usar_coordenadas=True, _fast_fail=True)
        r2 = m.extrair_dados_reais_google(*_o, usar_coordenadas=True, _fast_fail=False)
        assert r1 == _payload and r2 == _payload
    finally:
        try:
            del m.cache_google[_key]
        except Exception:
            pass


class _BoomSession:
    def get(self, *a, **k):
        raise AssertionError("cache-hit não deve chamar session.get")
    def post(self, *a, **k):
        raise AssertionError("cache-hit não deve chamar session.post")


def test_politica_adaptativa_mantem_paciencia_para_o_vencedor():
    # o vencedor (sem fast_fail) mantém a política adaptativa normal — paciência quando o Google está saudável
    pol = m._google_politica_adaptativa()
    assert pol["timeout"] >= 4 and pol["tentativas"] >= 1
