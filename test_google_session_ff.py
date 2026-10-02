# -*- coding: utf-8 -*-
"""[HOTFIX-GOOGLE-RETRY] O scraper do Google passa a usar uma sessão FAIL-FAST dedicada (session_google_ff) com
0 retries no urllib3 — o retry inteligente é o laço manual de rotação de User-Agent. Guardas de não-regressão:
a sessão existe, é isolada da sessão geral, não faz retry-storm, e o pool keep-alive foi preservado (32)."""
import streamlit_app as m


def test_sessao_google_ff_existe_e_isolada():
    assert m.session_google_ff is not None
    assert m.session_google_ff is not m.session               # isolada da sessão geral (geocoders)
    assert m.session_google_ff is not m.session_osrm_publico
    assert m.session_google_ff is not m.session_fossgis_ff


def test_sessao_google_ff_sem_retry_storm():
    # 0 retries no urllib3 → nenhuma espera morta de backoff; o laço manual (UA rotativo) é quem retenta.
    _ad = m.session_google_ff.get_adapter("https://www.google.com/")
    _max = _ad.max_retries
    _total = getattr(_max, "total", _max)
    assert int(_total) == 0


def test_pool_keepalive_preservado():
    # mantém o pool keep-alive dimensionado p/ os workers (reuso de conexão, menos handshake TLS)
    _ad = m.session_google_ff.get_adapter("https://www.google.com/")
    # o HTTPAdapter guarda o tamanho do pool no PoolManager
    assert _ad._pool_maxsize == 32
