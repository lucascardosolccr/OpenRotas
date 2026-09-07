# inteligencia_geoespacial/tests/test_xai.py
import pytest

from inteligencia_geoespacial import bases_locais as bl
from inteligencia_geoespacial import enrichment_engine as ee
from inteligencia_geoespacial import xai_formatter as xf

DATAS_DISPONIVEIS = bool(bl.camadas_disponiveis())

# --------------------------------------------------------------------- fixtures
CONF_MOCK = {
    "pontuacao": 95,
    "nivel": "alta",
    "fontes_concordam": ["IBGE (malha municipal)", "IBGE BC250 (pontes)"],
    "motivo": "Válido em 2 fonte(s) independentes.",
}

ENR_MOCK = {
    "origem": {
        "municipio": {"nome": "Manaus", "geocodigo": "1302603"},
        "confianca": CONF_MOCK,
    },
    "destino": {
        "municipio": {"nome": "Rio de Janeiro", "geocodigo": "3304557"},
        "confianca": CONF_MOCK,
    },
    "rios_detectados": [
        {"nome": "Canal do Mangue", "distancia_km": 0.8, "navegavel": "Sim",
         "regime": "Permanente", "referencia": "destino"},
    ],
    "bacia_hidrografica": None,
    "pontes_encontradas": [
        {"nome": "Ponte Rio-Niterói", "distancia_km": 4.1, "tipo_geom": "LINHA",
         "referencia": "destino"},
    ],
    "infraestrutura_aquaviaria": {
        "complexos_portuarios": [
            {"nome": "Porto de Manaus", "distancia_km": 2.3, "tipo_geom": "PONTO",
             "referencia": "origem"},
        ],
    },
    "balsas_confirmadas": [
        {"nome": "Travessia BR-174", "distancia_km": 9.4, "referencia": "origem"},
    ],
    "alternativa_sem_balsa": None,
    "confianca_geral": 95,
    "confianca_nivel": "alta",
    "fontes_concordam": ["IBGE (malha municipal)", "IBGE BC250 (pontes)"],
    "motivo_decisao": "Origem em Manaus e destino em Rio de Janeiro (IBGE).",
    "raio_km": 40.0,
}

PONTO_MOCK = {
    "coordenadas": {"lat": -3.119, "lon": -60.0217},
    "municipio": {"nome": "Manaus", "geocodigo": "1302603"},
    "rio_mais_proximo": {"nome": "Igarapé Cachoeira Grande", "distancia_km": 1.25,
                         "navegavel": "Desconhecido", "regime": "Desconhecido"},
    "pontes_encontradas": [{"nome": "<sem nome>", "distancia_km": 5.51}],
    "balsas_confirmadas": [{"nome": "Travessia BR-174", "distancia_km": 9.38}],
    "confianca": CONF_MOCK,
    "fonte": "IBGE BC250 v2025 + BC100",
}


# --------------------------------------------------------------------- puro
def test_formatar_confianca():
    md = xf.formatar_confianca(CONF_MOCK)
    assert "95/100" in md and "alta" in md.lower()
    assert "IBGE (malha municipal)" in md


def test_formatar_confianca_vazia():
    assert "indisponível" in xf.formatar_confianca({})


def test_formatar_ponto():
    md = xf.formatar_ponto(PONTO_MOCK)
    assert "Manaus (1302603)" in md
    assert "Igarapé Cachoeira Grande" in md
    assert "Travessia BR-174" in md


def test_formatar_enriquecimento_contem_blocos():
    md = xf.formatar_enriquecimento(ENR_MOCK)
    assert "Confiança geral" in md
    assert "Canal do Mangue" in md
    assert "Ponte Rio-Niterói" in md
    assert "Porto de Manaus" in md
    assert "Travessia BR-174" in md
    assert "Motivo da decisão" in md


def test_formatar_enriquecimento_html_inline_safe():
    html = xf.formatar_enriquecimento_html(ENR_MOCK)
    assert "<b>Confiança geral:</b>" in html
    assert "95/100" in html
    assert "Travessia BR-174" in html


@pytest.mark.skipif(not DATAS_DISPONIVEIS, reason="Camadas derivadas ausentes.")
def test_formatar_integracao_rota_real():
    r = ee.enriquecer_rota((-3.1190, -60.0217), (-22.9068, -43.1729), raio_km=40.0)
    md = xf.formatar_enriquecimento(r)
    assert "Manaus (1302603)" in md
    assert "Rio de Janeiro (3304557)" in md
    assert r["confianca_nivel"] in ("alta", "media", "baixa")