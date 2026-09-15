# -*- coding: utf-8 -*-
"""Rede de segurança END-TO-END da UI (SMOKE-PAINEL): sobe o app REAL na engine do Streamlit
(`AppTest`) e verifica que ele renderiza SEM EXCEÇÕES — a única classe de teste que pega erros no
caminho de render (uso indevido de `st.*`, coluna quebrada, um fragmento que deixou de executar) que os
testes de função pura não alcançam. Complementa a extração do painel de Analytics para `@st.fragment`:
trava que o fragmento (e o fragmento aninhado do Data Explorer) continuam executando de ponta a ponta.

ISOLAMENTO POR SUBPROCESSO (importante): o `AppTest` compartilha estado GLOBAL do Streamlit. Vários
outros arquivos da suíte fazem `import streamlit_app` em modo "bare" (sem ScriptRunContext), o que
executa o app inteiro e deixa o contexto de `st.form` sujo nesse estado global — fazendo o AppTest
reportar um falso "st.button dentro de st.form". Para ficar imune à ordem de coleta da suíte, cada
cenário roda num PROCESSO PYTHON NOVO (este mesmo arquivo, invocado como script), que nunca importa
`streamlit_app` em bare mode. Sob pytest, os testes apenas disparam o subprocesso e conferem o código
de saída.

Roda: `python3 -m pytest test_smoke_painel.py`."""
import os
import subprocess
import sys

import pytest

_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_app.py")
_DIR = os.path.dirname(os.path.abspath(__file__))
_GRUPO_ANALISAR = "📊 Analisar"
_SECAO_PAINEL = "📊 Painel Estratégico"
_SEC_KEY = "nav_sec_g2"  # grupo "📊 Analisar" = índice 2 em _GRUPOS_NAV (Consultar=0, Decidir=1, Analisar=2)

try:
    import streamlit.testing.v1  # noqa: F401
    _APPTEST_OK = True
except Exception:  # pragma: no cover
    _APPTEST_OK = False

pytestmark = pytest.mark.skipif(not _APPTEST_OK, reason="streamlit.testing indisponível")


# ---------------------------------------------------------------------------
# Driver (executa num processo próprio; NÃO importa streamlit_app em bare mode)
# ---------------------------------------------------------------------------
def _build_df(n=12):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(7)
    ufs = rng.choice(["AM", "SP", "PA", "BA", "MG"], n)
    reg = {"AM": "Norte", "PA": "Norte", "SP": "Sudeste", "MG": "Sudeste", "BA": "Nordeste"}
    dist = rng.uniform(5, 600, n).round(1)
    tmin = rng.uniform(20, 700, n).round(0)
    return pd.DataFrame({
        "Origem": [f"Origem {i}" for i in range(n)],
        "Destino": [f"Polo {i % 5}" for i in range(n)],
        "Endereco Oficial Origem": [f"Cidade {i} - {u}" for i, u in enumerate(ufs)],
        "Municipio Origem": [f"Municipio {i}" for i in range(n)],
        "Municipio Destino": [f"Polo {i % 5}" for i in range(n)],
        "Endereco Oficial Destino": [f"Rua X, Polo {i % 5}" for i in range(n)],
        "UF_Sintetica_Origem": ufs,
        "Regiao_Sintetica_Origem": [reg[u] for u in ufs],
        "Distancia": dist,
        "Linha Reta": (dist * rng.uniform(0.6, 0.95, n)).round(1),
        "Tempo": [f"{int(t)} min" for t in tmin],
        "Tempo_Minutos": tmin,
        "Tempo_Horas": (tmin / 60.0).round(2),
        "Score Final Global": rng.uniform(45, 100, n).round(1),
        "Status da Rota": rng.choice(["OK", "Estimada", "Erro"], n, p=[.7, .25, .05]),
        "Status Linha Reta": rng.choice(["OK", "Suspeita"], n, p=[.9, .1]),
        "Fonte Geocoding Origem": rng.choice(["IBGE", "ArcGIS", "Nominatim"], n),
        "Confianca Origem": rng.choice(["ALTA", "BAIXA", "ALTISSIMA"], n),
        "Confianca Destino": rng.choice(["ALTA", "ALTISSIMA"], n),
        "Balsas": rng.choice(["Sim", "Não"], n, p=[.15, .85]),
        "Risco Operacional": rng.choice(["crítico (80)", "alto (55)", "baixo (10)"], n, p=[.1, .2, .7]),
        "Antecedência Recomendada": rng.choice(["1 dia", "2 dias", "—"], n),
        "Link da Rota": ["https://maps.google.com/?q=x"] * n,
        "Motivo Roteamento": rng.choice(["Rota real", "Estimativa geodésica"], n),
        "Inscritos": rng.integers(1, 3000, n),
        "Lat Origem": rng.uniform(-33, 5, n).round(4),
        "Lon Origem": rng.uniform(-73, -34, n).round(4),
        "Lat Destino": rng.uniform(-33, 5, n).round(4),
        "Lon Destino": rng.uniform(-73, -34, n).round(4),
    })


def _authenticate(at):
    at.session_state["auth_user_id"] = "smoke-user"
    at.session_state["auth_email"] = "smoke@test.local"
    at.session_state["auth_access_token"] = "smoke-token"
    at.session_state["auth_refresh_token"] = "smoke-refresh"
    at.session_state["auth_last_check_ts"] = 9e18
    at.session_state["_onboarding_dispensado"] = True


def _drive(scenario):
    import logging
    logging.disable(logging.WARNING)
    os.chdir(_DIR)
    sys.path.insert(0, _DIR)
    from streamlit.testing.v1 import AppTest

    if scenario == "gate":
        at = AppTest.from_file(_APP, default_timeout=180)
        at.run()
        assert at.exception == [], f"exceções no portão de login: {[str(e.value) for e in at.exception]}"
        print("SMOKE_OK gate")
        return

    if scenario == "painel":
        at = AppTest.from_file(_APP, default_timeout=240)
        _authenticate(at)
        at.session_state["df_processado"] = _build_df()
        at.run()
        assert at.exception == [], f"exceções no boot autenticado: {[str(e.value) for e in at.exception]}"
        at.selectbox(key="nav_grupo").set_value(_GRUPO_ANALISAR).run()
        at.radio(key=_SEC_KEY).set_value(_SECAO_PAINEL).run()
        assert at.exception == [], f"exceções no painel: {[str(e.value) for e in at.exception]}"
        _md = " ".join(getattr(x, "value", "") for x in at.markdown)
        assert "Enterprise Analytics Dashboard" in _md, "não aterrissou no Painel Estratégico"
        assert "Estudo de Impacto nos Candidatos" in _md, "seção de impacto ausente"
        assert "Data Explorer" in _md, "Data Explorer ausente"
        assert len(at.dataframe) >= 3, f"poucas tabelas renderizadas: {len(at.dataframe)}"
        # flip do rádio de risco -> rerun do FRAGMENTO ANINHADO do Data Explorer
        at.radio(key="filtro_risco_explorer").set_value("🔴 Só risco crítico").run()
        assert at.exception == [], f"exceções no rerun do fragmento aninhado: {[str(e.value) for e in at.exception]}"
        print("SMOKE_OK painel")
        return

    raise SystemExit(f"cenário desconhecido: {scenario}")


def _run(scenario):
    """Dispara o cenário num processo novo (isolado do estado global sujo da suíte)."""
    r = subprocess.run([sys.executable, os.path.abspath(__file__), scenario],
                       cwd=_DIR, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and f"SMOKE_OK {scenario}" in r.stdout, (
        f"cenário '{scenario}' falhou (rc={r.returncode}).\n"
        f"--- STDOUT ---\n{r.stdout[-3000:]}\n--- STDERR ---\n{r.stderr[-3000:]}")


# ---------------------------------------------------------------------------
# Testes pytest (cada um roda seu cenário isolado por subprocesso)
# ---------------------------------------------------------------------------
def test_app_sobe_sem_excecao_no_portao_de_login():
    _run("gate")


def test_painel_estrategico_e_fragmentos_sem_excecao():
    _run("painel")


if __name__ == "__main__":
    _drive(sys.argv[1] if len(sys.argv) > 1 else "gate")
