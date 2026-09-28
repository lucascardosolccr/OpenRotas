# -*- coding: utf-8 -*-
"""[CHUNK-PERF · DIAGNÓSTICO] _perf_chunks_resumo agrega as métricas por chunk do roteamento e emite um
veredito acionável (rede × endgame × saudável). Puro/testável: aceita a lista de registros direto."""
import streamlit_app as m


def _rec(n, ok, adiadas, dt, timeout, ts=0.0):
    return {"ts": ts, "n": n, "ok": ok, "adiadas": adiadas, "dt": dt, "deadline": 40.0, "timeout": timeout}


def test_resumo_vazio_retorna_dict_vazio():
    assert m._perf_chunks_resumo([]) == {}


def test_resumo_rede_lenta():
    regs = [_rec(50, 5, 45, 40.0, True, ts=i) for i in range(8)]
    r = m._perf_chunks_resumo(regs)
    assert r["veredito"].startswith("rede")
    assert r["rotas_por_s"] < 2.0 and r["pct_chunks_deadline"] == 100.0
    assert r["rotas_medidas"] == 400 and r["concluidas"] == 40


def test_resumo_saudavel():
    regs = [_rec(50, 50, 0, 5.0, False, ts=i) for i in range(8)]
    r = m._perf_chunks_resumo(regs)
    assert r["veredito"].startswith("saudável")
    assert r["pct_adiadas"] == 0.0 and r["endgame"] is False


def test_resumo_endgame_detecta_crawl_final():
    # começo conclui tudo; último terço quase nada → queda >30 p.p. na taxa de conclusão
    regs = [_rec(50, 50, 0, 5.0, False, ts=i) for i in range(4)] + \
           [_rec(50, 5, 45, 30.0, True, ts=4 + i) for i in range(4)]
    r = m._perf_chunks_resumo(regs)
    assert r["endgame"] is True and r["veredito"].startswith("endgame")


def test_registrar_auto_reset_em_novo_run():
    # dois registros com gap > 120s → o acumulador reseta e conta só o run novo
    with m._PERF_CHUNKS_LOCK:
        m._PERF_CHUNKS.clear()
    m._perf_chunk_registrar(10, 10, 0, 1.0, 40.0, False)
    # força timestamp antigo no 1º registro
    with m._PERF_CHUNKS_LOCK:
        m._PERF_CHUNKS[-1]["ts"] -= 10_000
    m._perf_chunk_registrar(20, 18, 2, 2.0, 40.0, False)   # novo run → deve limpar o anterior
    r = m._perf_chunks_resumo()
    assert r["n_chunks"] == 1 and r["rotas_medidas"] == 20
    with m._PERF_CHUNKS_LOCK:
        m._PERF_CHUNKS.clear()
