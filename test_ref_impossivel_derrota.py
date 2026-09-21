# -*- coding: utf-8 -*-
"""[REF-IMPOSSIVEL-DERROTA] Rotas da referência com distância FISICAMENTE IMPOSSÍVEL (menor que a
geodésica) ou IMPLAUSÍVEL (colada à linha reta) devem APARECER COMO DERROTAS no diagnóstico de
divergências (a referência "levou o candidato mais perto", mas por um número inválido) e ser
EXPLICADAS no parecer. Antes, uma "vitória" da referência com distância impossível podia passar sem
o alerta de que o triunfo era apenas nominal. Estes testes travam esse contrato — additivo e defensivo
(sem coordenadas → não avaliável → classificação inalterada)."""
import streamlit_app as m

# São Paulo → Rio de Janeiro: ~360 km em linha reta geodésica.
_O = (-23.55, -46.63)
_D = (-22.91, -43.20)


def _fatos(dist, coord_o, coord_d, destino="Rio de Janeiro", fonte="OSRM"):
    return m._fatos_rota_divergencia({
        "distancia_km": dist, "coord_origem": coord_o, "coord_destino": coord_d,
        "destino": destino, "fonte_rota": fonte, "balsa": "Não",
    })


def test_referencia_impossivel_vira_derrota_explicada():
    # referência afirma 50 km (< ~360 km de reta = fisicamente impossível); app mede 430 km (real)
    linha = {"Origem": "Sao Paulo", "UF": "SP", "Inscritos": 100}
    fa = _fatos(430.0, _O, _D)
    fr = _fatos(50.0, _O, _D)
    a = m._analisar_divergencia_par(linha, fa, fr, limiar_empate_km=1.0)
    assert a.get("Vencedor (Qualidade)") == "Referência", "distância menor (ainda que impossível) => derrota nominal"
    assert a.get("_ref_invalida") is True
    assert "impossí" in (a.get("Auditoria Referência", "") + a.get("Explicação Auditoria Referência", "")).lower()
    assert "nominal" in a.get("Parecer Técnico", "").lower()


def test_referencia_plausivel_nao_e_marcada():
    # referência 400 km (> reta, plausível); app 430 km → referência vence de verdade, sem selo
    linha = {"Origem": "Sao Paulo", "UF": "SP", "Inscritos": 100}
    fa = _fatos(430.0, _O, _D)
    fr = _fatos(400.0, _O, _D)
    a = m._analisar_divergencia_par(linha, fa, fr, limiar_empate_km=1.0)
    assert a.get("_ref_invalida") is False
    assert "nominal" not in a.get("Parecer Técnico", "").lower()


def test_sem_coordenadas_nao_avalia_e_nao_regride():
    # sem coordenadas não há geodésica → não avaliável → nada de selo (fail-open)
    linha = {"Origem": "Sao Paulo", "UF": "SP", "Inscritos": 100}
    fa = _fatos(430.0, None, None)
    fr = _fatos(50.0, None, None)
    a = m._analisar_divergencia_par(linha, fa, fr, limiar_empate_km=1.0)
    assert a.get("_ref_invalida") is False
    assert a.get("Auditoria Referência") == "—"


def test_reprocesso_flagra_impossivel_sem_roteamento_fresco(monkeypatch):
    # sem 2ª opinião de rede; roteamento fresco FALHA → cai no fallback honesto, que ainda assim usa as
    # coordenadas oficiais (_map_*) da conciliação para auditar a distância da referência. A rota impossível
    # deve virar derrota (Referência) explicada; o exportável HTML deve trazer o selo "Derrota apenas nominal".
    monkeypatch.setattr(m, "_segunda_opiniao_derrota", lambda *a, **k: None)

    def _router_falha(o, d):
        raise RuntimeError("sem rede")

    linhas = []
    for i in range(3):
        linhas.append({"Mesmo Destino": "Não", "Origem": f"Mun{i}", "UF": "SP",
                       "Destino Referencia": "Rio de Janeiro", "Destino Aplicacao": "Sao Paulo",
                       "Distancia Aplicacao": 430.0, "Distancia Referencia": (50.0 if i == 0 else 400.0),
                       "Inscritos": 100, "Tempo Referencia": "5 h",
                       "_map_olat": _O[0], "_map_olon": _O[1], "_map_rlat": _D[0], "_map_rlon": _D[1]})
    diag = m._reprocessar_rotas_divergentes(linhas, limiar_empate_km=1.0, router=_router_falha)
    imp = [a for a in diag.get("analises", []) if a.get("Município") == "Mun0"]
    assert imp, "a divergência impossível deve ser analisada"
    assert imp[0].get("_ref_invalida") is True
    assert imp[0].get("Vencedor (Qualidade)") == "Referência"
    html = m._diagnostico_divergencias_html(diag)
    assert "Derrota apenas nominal" in html
    # e o exportável NÃO traz mais os "cartões (resumo visual)"; pareceres e árvores são recolhíveis
    assert "resumo visual" not in html.lower()
    assert 'details class="dv-exp"' in html
    # o agregado conta as derrotas nominais e gera insight + KPI
    _res = diag.get("resumo", {})
    assert _res.get("derrotas_nominais_ref_invalida") == 1
    assert _res.get("inscritos_derrotas_nominais") == 100
    assert any("apenas nominais" in i for i in diag.get("insights", []))
    assert "apenas nominais" in html
