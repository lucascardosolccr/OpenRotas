# -*- coding: utf-8 -*-
"""[RESGATE-GEOMETRICO] Motivado pela análise de derrotas de um estudo real: 41 de 53 derrotas eram
casos em que a pré-seleção (por linha reta) escolheu um polo INDIRETO (V/R alto) e o polo genuinamente
mais curto por ESTRADA — que a referência achou — estava mais LONGE por reta, fora dos K mais próximos
que o resgate roteava. Como reta ≤ viária SEMPRE, qualquer polo cuja reta seja menor que a distância
VIÁRIA já medida do líder PODE vencê-lo. O resgate passa a avaliar TODO esse conjunto (bounded), não só
os K mais diretos. Este teste prova que o polo antes descartado agora é encontrado e adotado."""
import streamlit_app as m


def _polo(nome, dlat):
    # posiciona o polo a ~ (dlat*111) km ao norte da origem (0,0)
    return {"nome": nome, "lat": dlat, "lon": 0.0}


def test_recupera_polo_mais_distante_por_reta_mas_mais_curto_por_estrada():
    origem = "MunTeste"
    coord = (0.0, 0.0)
    # 6 polos mais próximos por reta (10..35 km), todos INDIRETOS (estrada > 100 km) → não vencem o líder;
    # B está a 50 km por reta (7º mais próximo, FORA dos K=6) mas a estrada dele é 70 km (< 100 do líder).
    candidatos = [_polo(f"P{i}", (10 + 5 * i) / 111.0) for i in range(6)]  # P0..P5 ~10..35km
    candidatos.append(_polo("B", 50 / 111.0))                              # ~50 km reta
    candidatos.append(_polo("A", 40 / 111.0))                              # o já escolhido (~40 km reta)

    rotas = {f"P{i}": 130.0 for i in range(6)}   # todos indiretos por estrada
    rotas["B"] = 70.0                             # o vencedor real por estrada
    rotas["A"] = 100.0

    def fn_rota(nome):
        d = rotas.get(nome)
        if d is None:
            return None
        reta = {"B": 50.0, "A": 40.0}.get(nome, (10 + 5 * int(nome[1:])) if nome.startswith("P") else 40.0)
        return {"dist_km": d, "tempo_min": d, "tem_balsa": False, "fluvial": False,
                "reta_km": reta, "vr": (d / reta) if reta else None}

    escolhido = {"nome": "A", "dist_km": 100.0, "reta_km": 40.0, "vr": 2.5,
                 "tem_balsa": False, "fluvial": False, "tempo_min": 100.0}

    res = m._resgate_circuidade(origem, "SP", coord, candidatos, escolhido, fn_rota, inscritos=10)
    assert res["trocou"] is True, "o resgate deveria trocar para o polo mais curto por estrada"
    assert res["destino_final"] == "B"
    assert res["dist_final_km"] == 70.0


def test_lider_direto_nao_dispara_resgate():
    # líder com V/R baixa (rota direta) não tem assinatura de risco → resgate não roteia nada
    escolhido = {"nome": "A", "dist_km": 42.0, "reta_km": 40.0, "vr": 1.05,
                 "tem_balsa": False, "fluvial": False, "tempo_min": 42.0}
    res = m._resgate_circuidade("Mun", "SP", (0.0, 0.0), [_polo("B", 0.9)], escolhido,
                                lambda n: {"dist_km": 10.0}, inscritos=1)
    assert res["trocou"] is False and res["destino_final"] == "A"
