"""Testes do evaluation (Task 9) — mede o impacto do enriquecimento nas derrotas."""

from inteligencia_geoespacial import evaluation as ev


def test_coords_validas_rejeita_sem_coordenadas():
    ok_row = {"olat": -3.1, "olon": -60.0, "rlat": -2.0, "rlon": -60.5}
    sem_dest = {"olat": -3.1, "olon": -60.0, "rlat": None, "rlon": None}
    assert ev._coords_validas(ok_row) is True
    assert ev._coords_validas(sem_dest) is False
    assert ev._coords_validas({"olat": "a", "olon": 0, "rlat": 0, "rlon": 0}) is False


def test_auditavel_requer_motivo_fontes_e_confianca():
    rec = {"motivo_decisao": "Origem em X e destino em Y (IBGE).",
           "fontes_concordam": ["IBGE (malha municipal)"], "confianca_geral": 75}
    assert ev._auditavel(rec) is True
    assert ev._auditavel({**rec, "motivo_decisao": ""}) is False
    assert ev._auditavel({**rec, "fontes_concordam": []}) is False
    assert ev._auditavel({**rec, "confianca_geral": 10}) is False


def test_rio_navegavel_e_infra_aqua():
    assert ev._rio_navegavel({"rios_detectados": [{"navegavel": "Sim"}]}) is True
    assert ev._rio_navegavel({"rios_detectados": [{"navegavel": "Nao"}]}) is False
    assert ev._rio_navegavel({"rios_detectados": []}) is False
    assert ev._tem_infra_aqua({"infraestrutura_aquaviaria": {"atracadouros_terminal": [{}]}}) is True
    assert ev._tem_infra_aqua({"infraestrutura_aquaviaria": {}}) is False


def test_avaliar_smoke_subconjunto_sem_rede():
    """Roda 1 derrota real do baseline offline (sem cache em disco)."""
    r = ev.avaliar(max_rows=1, usar_cache=False, raio_km=40.0)
    assert r.get("ok") is True
    assert r["derrotas_auditadas"] == 1
    assert set(r.keys()) >= {"derrotas_baseline", "derrotas_residuais",
                             "ferry_detection", "explicacao_qualidade_pct"}