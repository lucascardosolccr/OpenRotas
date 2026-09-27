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
    # A tolerância relativa amplia a faixa de EMPATE em distâncias grandes (item 19). Após a regra
    # ASSIMÉTRICA (app menor vence sempre), a faixa relevante do empate é o lado em que a app é MAIOR:
    # referência 2 km mais curta em 1.000 km é derrota SEM limiar_rel, mas empate técnico COM ele.
    venc_sem_rel, _ = m._decidir_vencedor_distancia(998.0, 1000.0, limiar_abs=1.0, limiar_rel=0.0)
    assert venc_sem_rel == "Referência"
    venc_com_rel, _ = m._decidir_vencedor_distancia(998.0, 1000.0, limiar_abs=1.0, limiar_rel=0.01)
    assert venc_com_rel == "Empate"


# [MENOR-ROTA · VITÓRIA DA APLICAÇÃO — regra assimétrica pedida pelo usuário]
# (A) app estritamente menor → vitória da aplicação em QUALQUER margem, mesmo dentro do limiar;
# (B) app igual/maior, porém a diferença cabe no limiar → empate;
# (C) app maior que a referência além do limiar → referência.
def test_menor_rota_app_menor_dentro_do_limiar_vence_aplicacao():
    # app 5 km mais curta, limiar 10 km: NÃO é mais empate — a vitória de menor rota é da aplicação.
    venc, trace = m._decidir_vencedor_distancia(105.0, 100.0, limiar_abs=10.0)
    assert venc == "Aplicação"
    assert trace["dif"] == 5.0


def test_menor_rota_app_maior_dentro_do_limiar_e_empate():
    # app 5 km MAIS LONGA, limiar 10 km: a diferença cabe na faixa → empate (a app não é derrotada).
    venc, _ = m._decidir_vencedor_distancia(100.0, 105.0, limiar_abs=10.0)
    assert venc == "Empate"


def test_menor_rota_diferenca_igual_ao_limiar_e_empate_inclusivo():
    # diferença EXATAMENTE igual ao limiar (app maior) → empate ("dentro da faixa", inclusivo).
    venc, _ = m._decidir_vencedor_distancia(100.0, 110.0, limiar_abs=10.0)
    assert venc == "Empate"


def test_menor_rota_app_maior_alem_do_limiar_perde():
    # app 15 km mais longa, limiar 10 km: além da faixa → referência vence.
    venc, _ = m._decidir_vencedor_distancia(100.0, 115.0, limiar_abs=10.0)
    assert venc == "Referência"


def test_menor_rota_app_menor_por_margem_minima_vence():
    # app apenas 0,3 km mais curta, limiar 10 km: ainda assim é vitória da aplicação (Δ>0 sempre vence).
    venc, _ = m._decidir_vencedor_distancia(100.3, 100.0, limiar_abs=10.0)
    assert venc == "Aplicação"


# [MENOR-ROTA · CONSISTÊNCIA ENTRE OS 3 VEREDITOS] O veredito de distância, o "Esforço Real"
# (_vencedor_multicriterio_comparacao) e a "Vantagem viária" (_v318_vantagem_viaria) não podem
# divergir no caso claro: app estritamente menor, SEM balsa, dentro do limiar → todos dão Aplicação.
def test_esforco_real_app_menor_sem_balsa_dentro_limiar_vence_aplicacao():
    linha = {"Distancia Referencia": 105.0, "Distancia Aplicacao": 100.0,
             "Balsa Aplicacao": "Não", "Balsa Referencia": "Não"}
    venc, _crit, _exp = m._vencedor_multicriterio_comparacao(linha, limiar_empate_km=10.0)
    assert venc == "Aplicação"


def test_v318_vantagem_viaria_app_menor_sem_balsa_dentro_limiar_vence_aplicacao():
    venc, _crit = m._v318_vantagem_viaria(100.0, 105.0, balsa_app="Não", balsa_ref="Não", limiar_empate_km=10.0)
    assert venc == "Aplicação"


def test_v318_app_maior_dentro_do_limiar_e_empate():
    # app 5 km mais longa, sem balsa, limiar 10 → segue empate (a regra assimétrica só favorece a app quando MENOR).
    venc, _ = m._v318_vantagem_viaria(105.0, 100.0, balsa_app="Não", balsa_ref="Não", limiar_empate_km=10.0)
    assert venc == "Empate"


def test_estabilidade_limiar_vitorias_app_sao_independentes_da_regua():
    # Regra assimétrica: a app vence sempre que é menor (Δ>0), então "Aplicação vence" é CONSTANTE ao
    # variar a régua; a régua só move o lado da referência (empate × derrota).
    linhas = [
        {"Diferenca Abs (km)": 3.0, "Inscritos": 100},    # app 3 km menor  → app vence em qualquer régua
        {"Diferenca Abs (km)": -3.0, "Inscritos": 50},    # ref 3 km menor  → derrota(≤1) vira empate(≥3)
        {"Diferenca Abs (km)": 15.0, "Inscritos": 20},    # app 15 km menor → app vence
        {"Diferenca Abs (km)": -15.0, "Inscritos": 30},   # ref 15 km menor → derrota estrutural
    ]
    out = m._estabilidade_limiar_empate(linhas, limiares=(1.0, 5.0))
    by = {r["Limiar (km)"]: r for r in out}
    assert by[1.0]["Aplicação vence"] == 2
    assert by[5.0]["Aplicação vence"] == 2            # não muda com a régua (assimétrico)
    assert by[1.0]["Referência vence"] == 2 and by[1.0]["Empates"] == 0
    assert by[5.0]["Referência vence"] == 1 and by[5.0]["Empates"] == 1   # 1 derrota vira ruído
    # "Candidatos beneficiados" (benefício material > régua) encolhe ao ampliar o limiar
    assert by[1.0]["Candidatos beneficiados"] == 120 and by[5.0]["Candidatos beneficiados"] == 20


def test_justificativa_empate_reflete_limiar_configurado():
    # a justificativa do empate não pode mais dizer "< 1 km" fixo quando o usuário definiu outro limiar.
    linha = {"Origem": "Mun", "UF": "PA", "Inscritos": 10,
             "Destino Referencia": "D", "Distancia Referencia": 100.0,
             "Destino Aplicacao": "D", "Distancia Aplicacao": 105.0}   # app 5 km maior → empate com limiar 10
    out = m._comparar_alocacoes([linha], limiar_empate_km=10.0)
    r = out[0]
    assert r["Vencedor Distancia"] == "Empate"
    assert "10 km" in r["Justificativa"]
    assert "< 1 km" not in r["Justificativa"]


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


# ==============================================================================
# _confianca_fundida(idx_motor, idx_geografico, qt_anomalias) / _rotulo_confianca(score)
# Missão 3, Rodada 12: cobertura real via pytest do que a Rodada 10 só tinha verificado
# por script isolado (não commitado) — mesmo motivo de existir deste arquivo (ver docstring
# do módulo): uma alegação de verificação que não vira suíte re-executável não vale nada.
# ==============================================================================

def test_confianca_fundida_concordam_media_alta_sem_conflito():
    r = m._confianca_fundida(90, 85, qt_anomalias=0)
    assert r["conflito"] is False
    assert 85 <= r["confianca"] <= 90
    assert r["rotulo"] == "Alta"


def test_confianca_fundida_gap_grande_e_conflito():
    r = m._confianca_fundida(95, 20, qt_anomalias=1)
    assert r["conflito"] is True
    assert r["gap"] == 75.0
    assert r["confianca"] == 58  # round((95+20)/2)


def test_confianca_fundida_muitas_anomalias_tambem_e_conflito_mesmo_com_gap_pequeno():
    r = m._confianca_fundida(70, 68, qt_anomalias=3)
    assert r["conflito"] is True


def test_confianca_fundida_so_um_lado_disponivel_nao_fabrica_o_outro():
    r_geo = m._confianca_fundida(None, 60, qt_anomalias=0)
    assert r_geo == {"confianca": 60, "rotulo": "Média", "conflito": False, "gap": None}
    r_motor = m._confianca_fundida(72, None, qt_anomalias=0)
    assert r_motor["confianca"] == 72 and r_motor["gap"] is None


def test_confianca_fundida_nenhum_lado_disponivel_e_none():
    r = m._confianca_fundida(None, None)
    assert r["confianca"] is None
    assert r["conflito"] is False


def test_rotulo_confianca_faixas():
    assert m._rotulo_confianca(85) == "Alta"
    assert m._rotulo_confianca(80) == "Alta"
    assert m._rotulo_confianca(79.9) == "Média"
    assert m._rotulo_confianca(50) == "Média"
    assert m._rotulo_confianca(49.9) == "Baixa"
    assert m._rotulo_confianca(None) == ""


# ==============================================================================
# _n_candidatos_adaptativo(uf, cands_reta, ..., lat=None, lon=None) — Rodada 11: o caminho
# NOVO (lat/lon), que amplia o teto perto de travessia/hidrovia catalogada. Cobre o gap que
# a Rodada 6 do agente de auditoria apontou: o único teste existente (_testes_motor_rotas.py)
# nunca passa lat/lon, então o caminho novo nunca era exercitado por nenhuma suíte.
# ==============================================================================

def test_n_candidatos_adaptativo_sem_lat_lon_e_retrocompativel():
    cands = [(500.0, f"Hub{i}") for i in range(30)]
    assert m._n_candidatos_adaptativo("MG", cands) == m._n_candidatos_adaptativo("MG", cands, lat=None, lon=None)


def test_n_candidatos_adaptativo_amplia_perto_de_travessia_real_catalogada():
    # São José do Norte/RS — mesmo ponto de embarque da balsa usado como caso canônico em
    # _testes_motor_rotas.py (travessia real, catalogada na base IBGE).
    cands = [(500.0, f"Hub{i}") for i in range(30)]
    _base = m._n_candidatos_adaptativo("RS", cands)
    _com_agua = m._n_candidatos_adaptativo("RS", cands, lat=-32.0091, lon=-52.0168)
    assert _com_agua >= _base  # nunca reduz (monotônico)
    assert _com_agua > _base   # e de fato amplia quando há travessia real por perto


def test_n_candidatos_adaptativo_nao_amplia_sem_travessia_hidrovia_por_perto():
    # Interior seco de MG, sem travessia/hidrovia catalogada nas proximidades.
    cands = [(500.0, f"Hub{i}") for i in range(30)]
    _base = m._n_candidatos_adaptativo("MG", cands)
    _sem_agua = m._n_candidatos_adaptativo("MG", cands, lat=-18.5, lon=-44.5)
    assert _sem_agua == _base


# [MENOR-ROTA-MAX] Teto _max elevado 240→300: em universos MUITO densos (>400 polos) a descoberta
# por matriz agora vai mais fundo (a fronteira do ótimo viário pode passar do 240º por reta). O
# fator de escala (~60%) e o intervalo [_min, _max] continuam governando o resultado.
def test_n_candidatos_adaptativo_teto_ampliado_em_universo_muito_denso():
    # 600 polos por reta CRESCENTE (distintos): dispara o caminho de densidade (n_total*0.6=360),
    # limitado pelo novo teto _max=300 — antes travava em 240.
    cands = [(float(i + 1), f"Hub{i}") for i in range(600)]
    _n = m._n_candidatos_adaptativo("MG", cands)
    assert _n > 240          # de fato ultrapassa o teto antigo (busca mais ampla pela menor rota)
    assert _n <= 300         # respeita o novo teto máximo
    # e permanece limitado ao teto mesmo com sinal de barreira hídrica (não estoura _max)
    assert m._n_candidatos_adaptativo("MG", cands, lat=-18.5, lon=-44.5) <= 300


def test_n_candidatos_adaptativo_economia_preservada_em_universo_pequeno():
    # UF esparsa com 1º colocado dominante: a economia continua valendo (não infla até o teto novo).
    cands = [(float((i + 1) * 40), f"Hub{i}") for i in range(30)]   # retas bem espaçadas → sem empate
    assert m._n_candidatos_adaptativo("GO", cands) < 60


# ==============================================================================
# _agregar_diagnostico_divergencias — Rodada 16 (§36): tally de "derrotas recuperáveis"/
# "derrotas evitáveis" por classe forense (_apr2_forense_derrota), antes só disponível como
# texto livre dentro do parecer de CADA derrota individual, nunca somado num KPI agregado.
# ==============================================================================

def _analise(venc, forense=None, uf="SP"):
    return {"Inscritos": 1, "Vencedor (Qualidade)": venc, "Diferença (km)": -5.0 if venc == "Referência" else 5.0,
            "UF": uf, "Categoria": "x", "Balsa Aplicação": "Não", "_forense_classe": forense}


def test_agregar_diagnostico_tally_derrotas_por_classe_forense():
    analises = [
        _analise("Referência", "nao_roteado"),
        _analise("Referência", "bug_algoritmo"),
        _analise("Referência", "regra_balsa"),
        _analise("Aplicação", None),
        _analise("Empate", None),
    ]
    r = m._agregar_diagnostico_divergencias(analises)["resumo"]
    assert r["derrotas_recuperaveis"] == 1
    assert r["derrotas_evitaveis"] == 1
    assert r["derrotas_regra_correta"] == 1
    assert r["derrotas_por_classe_forense"] == {"nao_roteado": 1, "bug_algoritmo": 1, "regra_balsa": 1}
    assert r["ref_superior"] == 3 and r["app_superior"] == 1 and r["empates"] == 1


def test_agregar_diagnostico_sem_derrotas_forenses_nunca_fabrica_classe():
    r = m._agregar_diagnostico_divergencias([_analise("Aplicação", None)])["resumo"]
    assert r["derrotas_recuperaveis"] == 0
    assert r["derrotas_por_classe_forense"] == {}
