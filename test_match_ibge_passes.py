# -*- coding: utf-8 -*-
"""[MATCH-IBGE-PASSES] Os passes de otimalidade (resgate/fechamento) casavam a origem com o universo de
polos SÓ por NOME. A própria Comparação concilia 100% por CÓDIGO IBGE, e o fechamento já MONTAVA a chave
"ibge:<cod>" — mas o índice do topk não tinha chave por IBGE, então esse caminho autoritativo ficava MORTO,
e qualquer deriva de formatação de nome (sufixo de UF, acento, caixa) fazia a origem ser SILENCIOSAMENTE
pulada — a rota indireta persistia. Estes testes provam que, com o índice por IBGE, a origem casa e a troca
acontece MESMO quando o nome no df NÃO bate com a chave-nome do topk (só o IBGE bate)."""
import pandas as pd

import streamlit_app as m


class _RP:
    def __init__(self, distancia, reta, balsas="Não", fonte="OSRM", tempo="1:00", municipio=""):
        self.distancia = distancia; self.dist_linha_reta = reta; self.balsas = balsas
        self.fonte_rota = fonte; self.status_linha_reta = ""; self.motivo_roteamento = ""
        self.tempo = tempo; self.municipio_destino = municipio; self.lat_destino = None
        self.lon_destino = None; self.link_rota = ""; self.score_rota = 0.0


def test_fechamento_casa_por_ibge_quando_nome_diverge():
    # O df tem a origem como "Pauini/AM" (com sufixo de UF); o topk é chaveado por "Pauini" (só nome) —
    # NÃO casa por nome. Mas ambos trazem o mesmo Código IBGE. Com o índice por IBGE, casa e troca.
    df = pd.DataFrame([{
        "Origem": "Pauini/AM", "UF": "AM", "Cod IBGE Origem": "1303403",
        "Destino": "Sena Madureira", "Distancia": 412.0, "Linha Reta": 236.0,
        "Tempo": "6:00", "Balsas": "Não", "Fonte da Rota": "OSRM", "Inscritos": 30,
    }])
    topk_completo = {"pauini": [(236.0, "Sena Madureira"), (280.0, "Rio Branco")]}  # chave-nome NÃO é "Pauini/AM"
    topk_ibge = {"1303403": [(236.0, "Sena Madureira"), (280.0, "Rio Branco")]}
    _rotas = {"Rio Branco": _RP(267.0, 280.0, municipio="Rio Branco")}

    # sem IBGE → NÃO casa (nome diverge) → nenhuma troca
    df_a = df.copy()
    df_a2, res_a = m._fechar_otimalidade_final(df_a, topk_completo, router=lambda o, h: _rotas.get(h),
                                               hubs_validos={})
    assert res_a["trocas"] == 0
    assert str(df_a2.at[0, "Destino"]) == "Sena Madureira"

    # com IBGE → casa por código → adota Rio Branco (267 < 412)
    df_b = df.copy()
    df_b2, res_b = m._fechar_otimalidade_final(df_b, topk_completo, router=lambda o, h: _rotas.get(h),
                                               hubs_validos={}, topk_ibge=topk_ibge)
    assert res_b["trocas"] == 1
    assert str(df_b2.at[0, "Destino"]) == "Rio Branco"


def test_resgate_casa_por_ibge_quando_nome_diverge():
    df = pd.DataFrame([{
        "Origem": "Machadinho/RO", "UF": "RO", "Cod IBGE Origem": "1101401",
        "Destino": "Ariquemes", "Distancia": 161.0, "Linha Reta": 98.0,
        "Tempo": "2:30", "Balsas": "Não", "Fonte da Rota": "OSRM", "Inscritos": 20,
    }])
    topk_completo = {"machadinho": [(98.0, "Ariquemes"), (100.0, "Jaru")]}
    topk_ibge = {"1101401": [(98.0, "Ariquemes"), (100.0, "Jaru")]}

    def _router(oq, hub):
        return {"Jaru": _RP(139.0, 100.0, municipio="Jaru"),
                "Ariquemes": _RP(161.0, 98.0, municipio="Ariquemes")}.get(hub)

    df2, regs = m._refinar_por_resgate_circuidade(df, topk_completo, router=_router,
                                                  topk_completo=topk_completo, topk_ibge=topk_ibge)
    assert str(df2.at[0, "Destino"]) == "Jaru", "deveria trocar Ariquemes→Jaru casando a origem por IBGE"


def test_ibge_float_normalizado():
    # IBGE que chega como "1101401.0" (float) casa com a chave "1101401"
    df = pd.DataFrame([{
        "Origem": "X", "UF": "RO", "Cod IBGE Origem": "1101401.0",
        "Destino": "Ariquemes", "Distancia": 161.0, "Linha Reta": 98.0,
        "Tempo": "2:30", "Balsas": "Não", "Fonte da Rota": "OSRM", "Inscritos": 20,
    }])
    topk_ibge = {"1101401": [(98.0, "Ariquemes"), (100.0, "Jaru")]}
    df2, regs = m._refinar_por_resgate_circuidade(
        df, {}, router=lambda o, h: {"Jaru": _RP(139.0, 100.0)}.get(h),
        topk_completo={}, topk_ibge=topk_ibge)
    assert str(df2.at[0, "Destino"]) == "Jaru"
