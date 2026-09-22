# -*- coding: utf-8 -*-
"""[MEDIÇÃO-JUSTA] O fechamento media o INCUMBENTE pelo melhor de todos os motores (min do pipeline), mas o
CANDIDATO só pela rota do OSRM por coordenada — viés que perdia trocas ganháveis (a referência vence por
achar a malha mais curta). `_fechamento_medicao_min` dá ao candidato a MESMA chance: escolhe a menor medição
válida entre OSRM e o pipeline completo, com blindagem anti-homônimo (linha reta compatível) e guarda física.
Análise real (comparacao_estudos_6): 74 derrotas 'por motor (malhas distintas)' — exatamente este viés."""
import streamlit_app as m


def _osrm(dist, reta):
    return {"dist_km": dist, "reta_km": reta, "vr": dist / reta, "tem_balsa": False,
            "fluvial": False, "tempo_min": dist, "fonte": "OSRM (coord)", "status": ""}


def test_adota_pipeline_quando_menor_e_mesma_localizacao():
    # OSRM diz 100 km; o pipeline (multi-motor) acha 85 km para o MESMO polo (reta ~compatível) → adota 85
    out = m._fechamento_medicao_min(_osrm(100.0, 70.0), dist_pipe=85.0, reta_pipe=71.0, reta_coord=70.0,
                                    fonte_pipe="Google")
    assert out["dist_km"] == 85.0
    assert "Google" in out["fonte"]


def test_rejeita_pipeline_se_localizacao_diferente_homonimo():
    # pipeline devolve 60 km MAS a linha reta é 30 km (vs 70 da coordenada) → é OUTRO lugar (homônimo) → mantém OSRM
    out = m._fechamento_medicao_min(_osrm(100.0, 70.0), dist_pipe=60.0, reta_pipe=30.0, reta_coord=70.0)
    assert out["dist_km"] == 100.0


def test_rejeita_pipeline_fisicamente_impossivel():
    # pipeline 50 km mas reta 70 km → viária < reta (impossível) → mantém OSRM
    out = m._fechamento_medicao_min(_osrm(100.0, 70.0), dist_pipe=50.0, reta_pipe=70.0, reta_coord=70.0)
    assert out["dist_km"] == 100.0


def test_mantem_osrm_quando_pipeline_nao_e_menor():
    out = m._fechamento_medicao_min(_osrm(100.0, 70.0), dist_pipe=105.0, reta_pipe=71.0, reta_coord=70.0)
    assert out["dist_km"] == 100.0


def test_defensivo_entradas_invalidas():
    o = _osrm(100.0, 70.0)
    assert m._fechamento_medicao_min(o, None, None, None) is o
    assert m._fechamento_medicao_min(o, 0.0, 70.0, 70.0) is o
