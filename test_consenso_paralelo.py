# -*- coding: utf-8 -*-
"""[PERF-CONSENSO-PARALELO] O Valhalla (motor keyless de consenso) é lançado no pool DEDICADO EXECUTOR_CONSENSO
para rodar EM PARALELO com o FOSSGIS no caminho do vencedor. Guardas de NÃO-REGRESSÃO:
  - o pool existe, é isolado (não é o EXECUTOR_APIS nem o EXECUTOR_GLOBAL) → não satura o caminho quente;
  - submeter `_chamar_motor_cb('Valhalla', func, ...)` ao pool e coletar `.result()` devolve EXATAMENTE o mesmo
    valor que a chamada inline (mesma decisão de rota — só o tempo muda);
  - o wrapper `_chamar_motor_cb` continua respeitando o disjuntor e registrando sucesso/falha do motor."""
import streamlit_app as m


def test_executor_consenso_existe_e_isolado():
    assert m.EXECUTOR_CONSENSO is not None
    # isolado dos pools do caminho quente (não pode contendê-los)
    assert m.EXECUTOR_CONSENSO is not m.EXECUTOR_APIS
    assert m.EXECUTOR_CONSENSO is not m.EXECUTOR_GLOBAL
    # singleton por processo (mesma referência entre chamadas — @st.cache_resource)
    assert m._obter_executor_consenso() is m.EXECUTOR_CONSENSO


def test_submit_e_coleta_equivalem_a_inline(monkeypatch):
    # motor stub determinístico no CONTRATO de rota (km, tempo, balsa, ...): o valor coletado do pool
    # deve ser IDÊNTICO ao da chamada inline — a paralelização muda só o tempo, nunca o resultado.
    _saida = (123.45, 90, "Não", "N/A", "geo-stub", {}, [], {})

    def _valhalla_stub(lat_o, lon_o, lat_d, lon_d):
        return _saida

    inline = m._chamar_motor_cb('Valhalla', _valhalla_stub, -10.0, -50.0, -11.0, -51.0)
    fut = m.EXECUTOR_CONSENSO.submit(m._chamar_motor_cb, 'Valhalla', _valhalla_stub, -10.0, -50.0, -11.0, -51.0)
    paralelo = fut.result()
    assert inline == paralelo == _saida


def test_disjuntor_aberto_pula_no_pool_tambem(monkeypatch):
    # se o disjuntor do motor estiver ABERTO, _chamar_motor_cb PULA (retorna None) — mesmo via pool,
    # confirmando que a paralelização não fura o disjuntor.
    monkeypatch.setattr(m, "_motor_pode_chamar", lambda nome: False)

    def _boom(*a, **k):
        raise AssertionError("motor NÃO deveria ser chamado com disjuntor aberto")

    fut = m.EXECUTOR_CONSENSO.submit(m._chamar_motor_cb, 'Valhalla', _boom, -10.0, -50.0, -11.0, -51.0)
    assert fut.result() is None
