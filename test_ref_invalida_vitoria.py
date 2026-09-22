# -*- coding: utf-8 -*-
"""[REF-INVÁLIDA → VITÓRIA DA APP] Regra física: nenhuma estrada é mais curta que a linha reta geodésica.
Quando a distância da referência é FISICAMENTE IMPOSSÍVEL (< reta) ou IMPLAUSÍVEL (colada à reta), o número
dela é inválido e não pode "vencer" — a vitória vai para a APLICAÇÃO, e a economia bogus é neutralizada.

Motivado por comparacao_estudos_5: 76 das 96 "vitórias da referência" eram distâncias impossíveis
(ilhas fluviais amazônicas: Muana→Abaetetuba ref 1,83 km com reta 42 km; Afuá→Macapá ref 45 km, rota real
~990 km). Estes testes travam a atribuição correta do vencedor e a limpeza das estatísticas."""
import streamlit_app as m


def _linha(dest_ref, dr, dest_app, da, reta_ref, insc=100):
    return {"Origem": "MunTeste", "UF": "PA", "Inscritos": insc,
            "Destino Referencia": dest_ref, "Distancia Referencia": dr,
            "Destino Aplicacao": dest_app, "Distancia Aplicacao": da,
            "Linha Reta Referencia (km)": reta_ref,
            "Tempo Referencia": "1:00", "Tempo Aplicacao": "1:10"}


def test_ref_impossivel_vira_vitoria_da_app():
    # ref 1.83 km mas a linha reta é 42.4 km → IMPOSSÍVEL; nominalmente a ref "venceu" (1.83<53)
    out = m._comparar_alocacoes([_linha("Abaetetuba", 1.83, "Abaetetuba", 53.0, 42.40)])
    r = out[0]
    assert r["Vencedor Distancia"] == "Aplicação"
    assert r.get("Vitoria por Ref Invalida") == "Sim"
    assert r["Economia km x Inscritos"] == 0.0      # economia bogus neutralizada
    assert r["Diferenca Abs (km)"] == 0.0
    assert "IMPOSS" in str(r.get("Ref Distancia Invalida", "")).upper()


def test_ref_plausivel_menor_continua_vitoria_da_ref():
    # ref 139 km, reta 98 km (fator 1.42 — rota real plausível) e menor que app 161 → ref vence de verdade
    out = m._comparar_alocacoes([_linha("Jaru", 139.0, "Ariquemes", 161.0, 98.0)])
    r = out[0]
    assert r["Vencedor Distancia"] == "Referência"
    assert r.get("Vitoria por Ref Invalida") is None


def test_app_menor_continua_vitoria_da_app():
    # app já é menor (90 < 120) e a ref é plausível → nada muda
    out = m._comparar_alocacoes([_linha("X", 120.0, "Y", 90.0, 80.0)])
    assert out[0]["Vencedor Distancia"] == "Aplicação"


def test_ref_implausivel_colada_na_reta_vira_vitoria_da_app():
    # ref 96 km, reta 95.5 km (fator ~1.005 — implausível, nenhuma estrada é tão reta) e menor que app 110
    out = m._comparar_alocacoes([_linha("Z", 96.0, "Z", 110.0, 95.5)])
    r = out[0]
    assert r["Vencedor Distancia"] == "Aplicação"
    assert r.get("Vitoria por Ref Invalida") == "Sim"
