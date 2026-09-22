# -*- coding: utf-8 -*-
"""[FECHAMENTO-OTIMALIDADE] Guarda de REGRESSÃO do passe REAL de produção `_fechar_otimalidade_final`
(o que roda no pipeline, linha 53760 — NÃO o helper legado `_resgate_circuidade`).

Motivação (análise de derrotas de um estudo real): a maioria das derrotas por sinuosidade eram casos em
que a pré-seleção por LINHA RETA elegeu um polo INDIRETO (V/R alto) e o polo genuinamente mais curto por
ESTRADA — o que a referência achou — estava MAIS LONGE por reta, logo atrás do incumbente no ranking por
reta. Como reta ≤ viária SEMPRE, qualquer polo cuja reta seja menor que a VIÁRIA já medida do incumbente
PODE vencê-lo. O fechamento varre TODA essa fronteira admissível (universo COMPLETO de polos, `topk_completo`)
e adota o menor por estrada. Estes testes exercitam o caminho REAL (df montado + router mock por nome) e
travam que:
  1) o polo mais distante por reta, porém mais curto por estrada, É descoberto e adotado (a derrota vira vitória);
  2) quando o incumbente já é o menor por estrada, NADA troca (monotônico, sem falso-positivo);
  3) a preferência cross-modal é preservada: não se troca uma rodovia por uma alternativa que só é mais curta
     porque depende de balsa (risco de travessia)."""
import pandas as pd

import streamlit_app as m


class _RP:
    """Mímica de uma RotaPipeline: só os atributos que o fechamento lê."""
    def __init__(self, distancia, reta, balsas="Não", fonte="OSRM", tempo="1:00",
                 municipio="", lat=None, lon=None):
        self.distancia = distancia
        self.dist_linha_reta = reta
        self.balsas = balsas
        self.fonte_rota = fonte
        self.status_linha_reta = ""
        self.motivo_roteamento = ""
        self.tempo = tempo
        self.municipio_destino = municipio
        self.lat_destino = lat
        self.lon_destino = lon
        self.link_rota = ""
        self.score_rota = 0.0


def _df_uma_origem(destino, viaria, reta):
    # SEM colunas lat/lon → o fechamento roteia por NOME (router mock), não por coordenada.
    return pd.DataFrame([{
        "Origem": "MunTeste", "UF": "AM", "Destino": destino,
        "Distancia": viaria, "Linha Reta": reta, "Tempo": "1:30", "Balsas": "Não",
        "Fonte da Rota": "OSRM", "Inscritos": 100,
    }])


def test_recupera_polo_mais_distante_por_reta_mas_mais_curto_por_estrada():
    # incumbente "A": viária 100, reta 40 (V/R 2,5 — INDIRETO). "B" está MAIS LONGE por reta (50, logo
    # atrás de A no ranking por reta) mas a estrada dele é 70 (< 100). "C" está a 60 por reta e é indireto.
    df = _df_uma_origem("A", viaria=100.0, reta=40.0)
    topk_completo = {"munteste": [(40.0, "A"), (50.0, "B"), (60.0, "C")]}

    _rotas = {"B": _RP(70.0, 50.0, municipio="B"), "C": _RP(125.0, 60.0, municipio="C")}

    def _router(origem_q, hub):
        return _rotas.get(hub)

    df2, resumo = m._fechar_otimalidade_final(df, topk_completo, router=_router, hubs_validos={})
    assert resumo["origens_fronteira_aberta"] == 1
    assert resumo["trocas"] == 1
    assert str(df2.at[0, "Destino"]) == "B"          # a derrota virou vitória
    assert m._num(df2.at[0, "Distancia"]) == 70.0    # viária atualizada para a menor real


def test_incumbente_ja_otimo_nao_troca():
    # incumbente "A": viária 45, reta 40. "B" reta 50 > 45 → fora da fronteira; "C" reta 42 < 45, mas
    # estrada 80 (não vence). Nenhuma troca: escolha já é a menor viária.
    df = _df_uma_origem("A", viaria=45.0, reta=40.0)
    topk_completo = {"munteste": [(40.0, "A"), (42.0, "C"), (50.0, "B")]}
    _rotas = {"C": _RP(80.0, 42.0, municipio="C"), "B": _RP(60.0, 50.0, municipio="B")}

    df2, resumo = m._fechar_otimalidade_final(df, topk_completo, router=lambda o, h: _rotas.get(h),
                                              hubs_validos={})
    assert resumo["trocas"] == 0
    assert str(df2.at[0, "Destino"]) == "A"


def test_nao_troca_rodovia_por_balsa_apenas_um_pouco_mais_curta():
    # cross-modal preservado: incumbente "A" rodoviário viária 100. "B" tem estrada 92 MAS depende de balsa
    # (risco de travessia). A economia (8 km) não paga o risco → mantém a rodovia. (Guarda de confiabilidade.)
    df = _df_uma_origem("A", viaria=100.0, reta=40.0)
    topk_completo = {"munteste": [(40.0, "A"), (50.0, "B")]}
    _rotas = {"B": _RP(92.0, 50.0, balsas="Sim", municipio="B")}

    df2, resumo = m._fechar_otimalidade_final(df, topk_completo, router=lambda o, h: _rotas.get(h),
                                              hubs_validos={})
    assert str(df2.at[0, "Destino"]) == "A", "não deveria trocar rodovia por balsa só 8 km mais curta"
