# -*- coding: utf-8 -*-
"""[FASE-PERF · DIAGNÓSTICO] _perf_fases_resumo agrega o tempo das fases de FINALIZAÇÃO (montagem,
enriquecimento, comparação, planilha) e emite um veredito de DOMINÂNCIA (finalização × roteamento),
para o painel apontar o gargalo real mesmo quando ele não é rede. Puro/testável: aceita as fases e o
tempo de roteamento direto. Também cobre o acumulador thread-safe e o decorator transparente."""
import streamlit_app as m


def _fases(**kw):
    """Monta um dict de fases no formato do acumulador a partir de {chave: segundos}."""
    return {k: {"dt": float(v), "n": 1, "linhas": 0} for k, v in kw.items()}


def test_resumo_vazio_retorna_dict_vazio():
    assert m._perf_fases_resumo({}, tempo_roteamento_s=0.0) == {}


def test_campea_e_total_corretos():
    r = m._perf_fases_resumo(_fases(montagem_dataframe=2.0, enriquecimento_geo=8.0,
                                    comparacao_referencia=1.0), tempo_roteamento_s=0.0)
    assert round(r["total_s"], 1) == 11.0
    assert r["campea"]["chave"] == "enriquecimento_geo"          # a mais cara vem primeiro
    assert r["itens"][0]["dt_s"] == 8.0 and r["itens"][-1]["dt_s"] == 1.0


def test_finalizacao_domina_quando_maior_que_roteamento():
    # finalização 30s vs roteamento 10s (>= 1.5×) → finaliza domina, aponta a fase campeã
    r = m._perf_fases_resumo(_fases(enriquecimento_geo=30.0), tempo_roteamento_s=10.0)
    assert r["finaliza_domina"] is True
    assert r["veredito"].startswith("finalização domina")
    assert "Enriquecimento geoespacial" in r["veredito"]


def test_roteamento_domina_quando_rede_maior():
    # roteamento 100s vs finalização 5s → roteamento domina (não sugere mexer na finalização)
    r = m._perf_fases_resumo(_fases(montagem_dataframe=5.0), tempo_roteamento_s=100.0)
    assert r["finaliza_domina"] is False
    assert r["veredito"].startswith("roteamento domina")


def test_sem_roteamento_ainda_resume_a_finalizacao():
    r = m._perf_fases_resumo(_fases(planilha_excel=3.0), tempo_roteamento_s=0.0)
    assert r["finaliza_domina"] is False
    assert r["tempo_roteamento_s"] == 0.0
    assert "Geração da planilha" in r["veredito"]


def test_registrar_acumula_e_auto_reseta_em_novo_run():
    with m._PERF_FASES_LOCK:
        m._PERF_FASES.clear()
    m._perf_fase_registrar("montagem_dataframe", 1.5, n_linhas=100)
    m._perf_fase_registrar("montagem_dataframe", 0.5, n_linhas=200)  # acumula no mesmo run
    with m._PERF_FASES_LOCK:
        assert round(m._PERF_FASES["montagem_dataframe"]["dt"], 2) == 2.0
        assert m._PERF_FASES["montagem_dataframe"]["n"] == 2
        assert m._PERF_FASES["montagem_dataframe"]["linhas"] == 200
        # força um novo run (gap grande)
        m._PERF_FASES_ULTIMO_TS[0] -= 10_000
    m._perf_fase_registrar("comparacao_referencia", 3.0)  # novo run → limpa o anterior
    with m._PERF_FASES_LOCK:
        assert "montagem_dataframe" not in m._PERF_FASES
        assert "comparacao_referencia" in m._PERF_FASES
        m._PERF_FASES.clear()


def test_decorator_e_transparente_no_retorno_e_na_excecao():
    with m._PERF_FASES_LOCK:
        m._PERF_FASES.clear()

    @m._perf_fase_timer("fase_teste")
    def _soma(a, b):
        return a + b

    assert _soma(2, 3) == 5                       # retorno intacto
    with m._PERF_FASES_LOCK:
        assert m._PERF_FASES["fase_teste"]["n"] == 1

    @m._perf_fase_timer("fase_erro")
    def _falha():
        raise ValueError("boom")

    try:
        _falha()
        assert False, "deveria ter propagado"
    except ValueError:
        pass
    with m._PERF_FASES_LOCK:
        assert m._PERF_FASES["fase_erro"]["n"] == 1   # mediu mesmo com exceção (finally)
        m._PERF_FASES.clear()
