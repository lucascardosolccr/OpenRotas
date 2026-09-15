# -*- coding: utf-8 -*-
"""Rede de segurança para o ESTUDO DE IMPACTO NOS CANDIDATOS (IMPACTO-CANDIDATOS): análise ponderada por
candidato (não por município), com quantis ponderados, Gini de concentração e recortes por balsa/risco/UF.
Núcleo 100% PURO — fixa o contrato, a ponderação e a robustez.

Roda: `python3 -m pytest test_impacto_candidatos.py`."""
import logging

logging.disable(logging.WARNING)

import pandas as pd  # noqa: E402

import streamlit_app as m  # noqa: E402


def _df():
    return pd.DataFrame({
        "Origem": ["A", "B", "C", "D"], "UF Origem": ["AM", "AM", "SP", "SP"],
        "Distancia": [300.0, 30.0, 500.0, 80.0], "Tempo": ["6 h", "30 min", "8 h", "1 h"],
        "Inscritos": [5000, 100, 50, 2000], "Balsas": ["Sim", "Não", "Não", "Não"],
        "Risco Operacional": ["crítico (78)", "baixo (10)", "alto (52)", "baixo (12)"],
    })


def test_sem_coluna_de_candidatos_nao_produz_estudo():
    df = pd.DataFrame({"Origem": ["A"], "Distancia": [100.0]})
    assert m._estudo_impacto_candidatos(df)["tem_candidatos"] is False


def test_detecta_coluna_e_totais():
    e = m._estudo_impacto_candidatos(_df())
    assert e["tem_candidatos"] and e["col_candidatos"] == "Inscritos"
    assert e["total_candidatos"] == 7150
    assert e["n_municipios"] == 4


def test_ponderacao_por_candidato_difere_da_media_simples():
    e = m._estudo_impacto_candidatos(_df())
    # candidato-km = 300*5000 + 30*100 + 500*50 + 80*2000 = 1.688.000; /7150 ≈ 236.1
    assert abs(e["km_candidato_total"] - 1688000.0) < 1.0
    assert abs(e["deslocamento_medio_ponderado"] - 236.1) < 0.2
    assert abs(e["deslocamento_medio_simples"] - 227.5) < 0.2


def test_quantil_ponderado_direto():
    # 3 municípios: dist 10 (peso 1), 20 (peso 1), 100 (peso 8) → mediana ponderada = 100
    assert m._quantil_ponderado([(10, 1), (20, 1), (100, 8)], 0.5) == 100.0
    assert m._quantil_ponderado([], 0.5) is None


def test_gini_extremos():
    assert m._gini([5, 5, 5, 5]) == 0.0              # igualdade total
    assert m._gini([0, 0, 0, 100]) > 0.6             # forte concentração


def test_recortes_balsa_e_risco_ponderados():
    e = m._estudo_impacto_candidatos(_df())
    assert e["balsa"]["candidatos"] == 5000          # só A tem balsa (5000 inscritos)
    assert e["risco"]["candidatos"] == 5050          # A (crítico) + C (alto) = 5000 + 50


def test_candidatos_longo_e_faixas():
    e = m._estudo_impacto_candidatos(_df(), limiar_longo_km=200.0)
    assert e["candidatos_longo"] == 5050             # A (300) + C (500)
    assert abs(sum(f["candidatos"] for f in e["distribuicao_faixas"]) - 7150) < 1


def test_por_uf_ponderado():
    e = m._estudo_impacto_candidatos(_df())
    _uf = {u["uf"]: u for u in e["por_uf"]}
    assert _uf["AM"]["candidatos"] == 5100 and _uf["SP"]["candidatos"] == 2050


def test_secao_html():
    h = m._secao_impacto_candidatos_html(m._estudo_impacto_candidatos(_df()))
    assert h and "Candidato-km total" in h and "Estudo" not in h.split("<h3")[0][:5]
    assert m._secao_impacto_candidatos_html({"tem_candidatos": False}) == ""
    assert m._secao_impacto_candidatos_html(None) == ""


def test_pareto_iniquidade_e_faixa_central():
    e = m._estudo_impacto_candidatos(_df())
    # quantis ponderados por candidato: metade central e caudas
    assert e["p25_candidato_km"] == 80.0 and e["p75_candidato_km"] == 300.0
    assert e["mediana_candidato_km"] == 300.0
    # razão P95/mediana (iniquidade de acesso)
    assert e["razao_p95_mediana"] == 1.0
    # Pareto: com A dominando o candidato-km, 1 município já concentra 50% e 80%
    assert e["pareto"]["municipios_para_50pct"] == 1
    assert e["pareto"]["municipios_para_80pct"] == 1
    assert e["pareto"]["pct_municipios_para_80pct"] == 25.0


def test_tempo_ponderado_por_candidato():
    e = m._estudo_impacto_candidatos(_df())
    # min ponderado: (360*5000 + 30*100 + 480*50 + 60*2000)/7150 = 1.947.000/7150 ≈ 272.3
    assert abs(e["tempo_medio_ponderado_min"] - 272.3) < 0.5
    assert e["mediana_tempo_min"] == 360.0


def test_dupla_exposicao_balsa_e_risco():
    e = m._estudo_impacto_candidatos(_df())
    # só A tem balsa E risco crítico ao mesmo tempo → 5000 candidatos
    assert e["balsa_e_risco"]["candidatos"] == 5000
    assert e["balsa_e_risco"]["municipios"] == 1


def test_share_acumulado_nos_top_municipios():
    e = m._estudo_impacto_candidatos(_df())
    tm = e["top_municipios_peso"]
    assert tm[0]["share_acumulado"] < 100.0            # o 1º não fecha 100%
    assert abs(tm[-1]["share_acumulado"] - 100.0) < 0.2  # o último acumula ~100%


def _df_grande():
    import pandas as pd
    # 12 municípios com pesos e distâncias variados → habilita a curva de Lorenz (≥10)
    return pd.DataFrame({
        "Origem": [f"M{i}" for i in range(12)],
        "UF Origem": ["AM"] * 6 + ["SP"] * 6,
        "Distancia": [500, 400, 300, 250, 200, 150, 120, 100, 80, 60, 40, 20.0],
        "Inscritos": [3000, 100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5],
    })


def test_lorenz_por_decil_com_massa():
    e = m._estudo_impacto_candidatos(_df_grande())
    lz = e["lorenz_deciles"]
    assert len(lz) == 10
    assert lz[-1]["share_acumulado"] == 100.0            # o último decil fecha 100%
    assert abs(sum(d["share_km_candidato"] for d in lz) - 100.0) < 0.6  # marginais somam ~100
    # a seção HTML deve trazer a curva de Lorenz e a leitura de Pareto quando há massa
    h = m._secao_impacto_candidatos_html(e)
    assert "Lorenz" in h and "acumulado" in h


def test_lorenz_ausente_sem_massa():
    # com poucos municípios (4) não há curva de Lorenz
    assert m._estudo_impacto_candidatos(_df())["lorenz_deciles"] == []


def test_wrapper_cacheado_equivale_ao_nucleo_puro():
    # [PERF-CACHE] o wrapper cacheado do painel deve devolver EXATAMENTE o mesmo resultado do núcleo puro —
    # o cache é só uma camada de memoização entre reruns, nunca altera o conteúdo.
    df = _df_grande()
    assert m._estudo_impacto_candidatos_cached(df) == m._estudo_impacto_candidatos(df)
    assert (m._narrativa_analitica_dashboard_cached(df)
            == m._narrativa_analitica_dashboard(df))
