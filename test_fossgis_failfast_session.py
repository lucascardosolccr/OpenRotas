# -*- coding: utf-8 -*-
"""[HOTFIX-FOSSGIS-RETRY] O FOSSGIS (throttled ≤1 req/s) passou a usar uma sessão FAIL-FAST (Retry total=1),
como o OSRM público, em vez da sessão geral (total=5) — que fazia retry-storm num servidor já throttled,
custando dezenas de segundos por chamada sob falha. Guarda de regressão da configuração das sessões."""
import streamlit_app as m


def _total(sess):
    return sess.get_adapter("https://x").max_retries.total


def test_sessao_fossgis_e_fail_fast():
    assert _total(m.session_fossgis_ff) == 1        # fail-fast: no máximo 1 tentativa extra


def test_sessao_osrm_publico_continua_fail_fast():
    assert _total(m.session_osrm_publico) == 1        # não regrediu


def test_sessao_geral_mantem_retries_para_google_e_geocoding():
    # a sessão geral (Google/geocodificação) MANTÉM os 5 retries — só o FOSSGIS saiu dela
    assert _total(m.session) == 5


def test_fossgis_e_geral_sao_sessoes_distintas():
    assert m.session_fossgis_ff is not m.session
