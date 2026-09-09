# -*- coding: utf-8 -*-
"""
Missão 3, Rodada 3 (§10 da missão "aprimoramento máximo"): rede de segurança automatizada
para a decisão pareada app×referência do Comparador de Estudos — exatamente a classe de bug
que o prompt teme ("rota menor nunca pode ser interpretada como rota maior"): unidades,
arredondamento, null, comparação, ordenação, empate.

Por que este arquivo existe: `_decidir_vencedor_distancia` já tem um invariante anti-inversão
embutido, documentado como "verificado por 200 mil pares aleatórios na suíte
test_comparador_V446.py" — mas esse arquivo NUNCA existiu no repositório (confirmado via
`git log --all` sobre o caminho: zero resultados). A alegação estava fabricada/stale. Este
arquivo é a suíte real, re-executável, que a documentação sempre afirmou existir.

Roda via pytest a partir da raiz do repositório: `python3 -m pytest test_comparador_correcao.py`.
Importa `streamlit_app` em "modo bare" (sem `streamlit run`) — mesmo padrão usado por
`_testes_motor_rotas.py`: Streamlit não lança exceção quando importado fora de um runtime
ativo, só loga avisos (silenciados abaixo).
"""
import logging
import math
import random

logging.disable(logging.WARNING)

import streamlit_app as m  # noqa: E402  (import após configurar logging, de propósito)


# ==============================================================================
# _decidir_vencedor_distancia(dr, da, limiar_abs=1.0, limiar_rel=0.0)
# ==============================================================================

def test_decidir_vencedor_distancia_app_estritamente_menor_vence():
    venc, trace = m._decidir_vencedor_distancia(100.0, 80.0)
    assert venc == "Aplicação"
    assert trace["dif"] == 20.0


def test_decidir_vencedor_distancia_referencia_estritamente_menor_vence():
    venc, trace = m._decidir_vencedor_distancia(80.0, 100.0)
    assert venc == "Referência"
    assert trace["dif"] == -20.0


def test_decidir_vencedor_distancia_dentro_da_tolerancia_e_empate():
    venc, _ = m._decidir_vencedor_distancia(100.0, 100.5, limiar_abs=1.0)
    assert venc == "Empate"


def test_decidir_vencedor_distancia_distancias_identicas_e_empate():
    venc, trace = m._decidir_vencedor_distancia(150.0, 150.0)
    assert venc == "Empate"
    assert trace["dif"] == 0.0


def test_decidir_vencedor_distancia_none_no_lado_referencia_nao_decide():
    venc, trace = m._decidir_vencedor_distancia(None, 80.0)
    assert venc == "—"
    assert "ausente" in trace["motivo"]


def test_decidir_vencedor_distancia_none_no_lado_aplicacao_nao_decide():
    venc, _ = m._decidir_vencedor_distancia(100.0, None)
    assert venc == "—"


def test_decidir_vencedor_distancia_nan_tratado_como_ausente():
    venc, _ = m._decidir_vencedor_distancia(float("nan"), 80.0)
    assert venc == "—"


def test_decidir_vencedor_distancia_zero_ou_negativo_nao_decide():
    # zero/negativo são fisicamente inválidos para uma distância real — não podem
    # gerar um veredito (nunca fabricar uma decisão sobre um dado impossível).
    assert m._decidir_vencedor_distancia(0.0, 80.0)[0] == "—"
    assert m._decidir_vencedor_distancia(100.0, -5.0)[0] == "—"


def test_decidir_vencedor_distancia_string_numerica_e_aceita():
    # planilhas de referência às vezes trazem número como texto — não pode quebrar
    # nem ser tratado como ausente.
    venc, _ = m._decidir_vencedor_distancia("100.0", "80.0")
    assert venc == "Aplicação"


def test_decidir_vencedor_distancia_string_nao_numerica_nao_decide():
    venc, _ = m._decidir_vencedor_distancia("N/A", 80.0)
    assert venc == "—"


def test_decidir_vencedor_distancia_tolerancia_relativa_amplia_empate_em_distancias_grandes():
    # 2 km de diferença em 1.000 km deve poder ser empate técnico com limiar_rel ligado
    # (o item 19 do próprio comentário da função) — mas NÃO com limiar_rel=0.0 (padrão).
    venc_sem_rel, _ = m._decidir_vencedor_distancia(1000.0, 998.0, limiar_abs=1.0, limiar_rel=0.0)
    assert venc_sem_rel == "Aplicação"
    venc_com_rel, _ = m._decidir_vencedor_distancia(1000.0, 998.0, limiar_abs=1.0, limiar_rel=0.01)
    assert venc_com_rel == "Empate"


def test_decidir_vencedor_distancia_invariante_nunca_inverte_fuzz():
    """Property-based: para milhares de pares aleatórios (incluindo casos-limite de
    arredondamento próximos da tolerância), o vencedor NUNCA pode contradizer o sinal
    real de (dr - da) além da tolerância declarada. Substitui a suíte
    'test_comparador_V446.py' referenciada no código-fonte mas nunca commitada."""
    rng = random.Random(446)  # seed fixa: fuzz determinístico, reproduzível
    for _ in range(5000):
        dr = rng.uniform(0.01, 5000.0)
        da = rng.uniform(0.01, 5000.0)
        limiar_abs = rng.choice([0.5, 1.0, 2.0, 5.0])
        limiar_rel = rng.choice([0.0, 0.0, 0.0, 0.005, 0.02])  # maioria com o padrão (desligado)
        venc, trace = m._decidir_vencedor_distancia(dr, da, limiar_abs=limiar_abs, limiar_rel=limiar_rel)
        dif = dr - da
        tol = max(limiar_abs, limiar_rel * min(dr, da))
        if venc == "Aplicação":
            assert dif > 0, (dr, da, dif, tol, venc)
        elif venc == "Referência":
            assert dif < 0, (dr, da, dif, tol, venc)
        elif venc == "Empate":
            assert abs(dif) <= tol + 1e-6, (dr, da, dif, tol, venc)
        # trace nunca mente sobre o sinal bruto, independente da tolerância aplicada
        assert trace["app_estritamente_menor"] == (da < dr)


def test_decidir_vencedor_distancia_km_nao_vira_metros_por_engano():
    # Um erro clássico de unidade: 1.500 m confundido com 1.500 km inflaria a
    # distância em 1000x. A função em si é agnóstica de unidade (recebe o número
    # que o chamador informou) -- o que ela GARANTE é que, para o MESMO par de
    # números, 1500 sempre vence 1.5 na direção certa (sem inversão por conversão
    # implícita, arredondamento ou truncamento).
    venc, trace = m._decidir_vencedor_distancia(1500.0, 1.5)
    assert venc == "Aplicação"
    assert trace["dif"] == 1498.5


# ==============================================================================
# _vantagem_banda_balsa(da, dr, balsa_app, balsa_ref, margem, fallback="Empate")
# Nota de assinatura: AO CONTRÁRIO de _decidir_vencedor_distancia (dr, da), aqui a
# ordem é (da, dr) -- aplicação primeiro. Testado explicitamente abaixo porque essa
# assimetria entre as duas funções irmãs é, em si, uma fonte plausível de bug de
# chamador (trocar a ordem dos argumentos ao adaptar código de uma para a outra).
# ==============================================================================

def test_vantagem_banda_balsa_mesmo_status_vence_menor_distancia():
    assert m._vantagem_banda_balsa(80.0, 100.0, False, False, 1.0) == "Aplicação"
    assert m._vantagem_banda_balsa(100.0, 80.0, False, False, 1.0) == "Referência"
    assert m._vantagem_banda_balsa(80.0, 80.0, True, True, 1.0) == "Empate"


def test_vantagem_banda_balsa_mesmo_status_dentro_da_margem_e_empate():
    assert m._vantagem_banda_balsa(100.0, 100.4, False, False, 1.0) == "Empate"


def test_vantagem_banda_balsa_dado_ausente_cai_no_fallback():
    assert m._vantagem_banda_balsa(None, 100.0, False, False, 1.0) == "Empate"
    assert m._vantagem_banda_balsa(100.0, None, False, False, 1.0, fallback="Referência") == "Referência"


def test_vantagem_banda_balsa_app_com_balsa_evitavel_perde_para_rodovia_razoavel():
    # App usa balsa (30 km); referência é rodoviária (35 km) -- diferença cabe na
    # banda admissível (§6/§7) -> a rodovia razoável vence mesmo sendo mais longa.
    r = m._vantagem_banda_balsa(30.0, 35.0, True, False, 1.0)
    assert r == "Referência"


def test_vantagem_banda_balsa_app_com_balsa_inevitavel_vence_por_distancia():
    # App usa balsa (7 km); referência rodoviária é um desvio ENORME (315 km) --
    # fora de qualquer banda razoável -> a travessia menor vence (balsa inevitável).
    r = m._vantagem_banda_balsa(7.0, 315.0, True, False, 1.0)
    assert r == "Aplicação"


def test_vantagem_banda_balsa_simetrico_entre_app_e_referencia():
    # A mesma situação espelhada (agora é a REFERÊNCIA que tem a balsa evitável)
    # deve produzir o veredito espelhado -- nenhum viés estrutural a favor de um
    # lado só por ser "aplicação".
    r_app_balsa = m._vantagem_banda_balsa(30.0, 35.0, True, False, 1.0)
    r_ref_balsa = m._vantagem_banda_balsa(35.0, 30.0, False, True, 1.0)
    assert {r_app_balsa, r_ref_balsa} == {"Referência", "Aplicação"}
    assert r_app_balsa != r_ref_balsa or r_app_balsa == "Empate"
    # app perdeu no primeiro (balsa evitável dela) <=> referência perde no espelho
    assert (r_app_balsa == "Referência") == (r_ref_balsa == "Aplicação")


def test_vantagem_banda_balsa_nunca_inverte_quando_status_igual_fuzz():
    rng = random.Random(447)
    for _ in range(3000):
        da = rng.uniform(0.01, 3000.0)
        dr = rng.uniform(0.01, 3000.0)
        margem = rng.choice([0.5, 1.0, 2.0])
        balsa = rng.choice([True, False])
        r = m._vantagem_banda_balsa(da, dr, balsa, balsa, margem)  # mesmo status dos 2 lados
        if r == "Aplicação":
            assert da < dr
        elif r == "Referência":
            assert dr < da
        else:
            assert abs(da - dr) < max(1.0, margem) + 1e-6


# ==============================================================================
# Auxiliares puros da política de balsa (banda adaptativa §6/§7)
# ==============================================================================

def test_balsa_extra_admissivel_e_sempre_nao_negativo_e_cresce_com_a_travessia():
    a = m._balsa_extra_admissivel(10.0)
    b = m._balsa_extra_admissivel(100.0)
    assert a > 0 and b > 0
    assert b >= a  # travessia maior admite banda proporcionalmente maior (ou igual ao piso)


def test_balsa_extra_admissivel_entrada_invalida_cai_no_piso_absoluto():
    from streamlit_app import _REL_BANDA_ABS_KM
    assert m._balsa_extra_admissivel(None) == float(_REL_BANDA_ABS_KM)
    assert m._balsa_extra_admissivel(-5.0) == float(_REL_BANDA_ABS_KM)
    assert m._balsa_extra_admissivel("abc") == float(_REL_BANDA_ABS_KM)


def test_rota_sem_balsa_razoavel_dentro_da_banda_e_true():
    assert m._rota_sem_balsa_razoavel(km_balsa=50.0, km_rodovia=55.0) is True


def test_rota_sem_balsa_razoavel_muito_alem_da_banda_e_false():
    assert m._rota_sem_balsa_razoavel(km_balsa=7.0, km_rodovia=315.0) is False
