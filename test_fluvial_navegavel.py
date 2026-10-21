# -*- coding: utf-8 -*-
"""[FLUVIAL-NAVEGAVEL] Guarda do classificador de navegabilidade de rios, que alimenta o roteamento
fluvial (qualidade de rota / rótulos de rio navegável). Três defeitos reais corrigidos:

  1) A lista autoritativa (ANA/ANTAQ) tinha nomes ACENTUADOS, mas o nome de entrada é normalizado (sem
     acento) — logo rios acentuados (Paraná, Parnaíba, Itajaí) NUNCA casavam e caíam na heurística
     fraca; o Solimões (tronco do Amazonas) nem estava na lista e dava só 25/100.
  2) O teste de corpo d'água PEQUENO rodava DEPOIS da heurística de tamanho: "Riacho Grande"/"Córrego
     Grande" casavam 'grande' e eram dados como navegáveis.
  3) O match parcial usava substring solto ('una' casava dentro de 'laguna').

Funções PURAS (sem o grafo fluvial de 500 MB) → o teste roda em qualquer ambiente."""
import streamlit_app as m


def test_rios_acentuados_casam_a_lista_autoritativa():
    # Antes: acentuados nunca casavam (input normalizado × lista acentuada). Agora casam (>=85).
    for nome in ("Rio Paraná", "Rio Parnaíba", "Rio Itajaí", "Rio Amazonas"):
        nav, conf, _ = m._rio_e_navegavel(nome)
        assert nav is True and conf >= 85, (nome, conf)


def test_solimoes_e_navegavel():
    # O Solimões faltava na lista — dava 25 (desconhecido). Agora é conhecido (95).
    for nome in ("Rio Solimões", "Solimões", "rio solimoes"):
        nav, conf, _ = m._rio_e_navegavel(nome)
        assert nav is True and conf == 95, (nome, conf)


def test_riacho_grande_nao_e_navegavel():
    # Bug de ordem: 'grande' era casado antes do teste de 'riacho/corrego/arroio'. Agora o pequeno vence.
    for nome in ("Riacho Grande", "Córrego Grande", "Arroio Grande", "Córrego da Mãe"):
        nav, conf, det = m._rio_e_navegavel(nome)
        assert nav is False and "pequeno" in det, (nome, det)


def test_rio_grande_de_verdade_continua_navegavel():
    # Sem palavra de corpo pequeno, 'Rio Grande' segue navegável (não é regressão do fix de ordem).
    nav, conf, _ = m._rio_e_navegavel("Rio Grande")
    assert nav is True and conf >= 50


def test_match_parcial_exige_palavra_inteira():
    # 'preto' é rio conhecido; por SUBSTRING solto (bug antigo) casaria dentro de 'Pretória' — falso
    # positivo. Com fronteira de palavra, 'Rio Pretória' NÃO casa e cai em desconhecido (25).
    nav, conf, det = m._rio_e_navegavel("Rio Pretoria")
    assert conf == 25, (conf, det)
    # e o match por palavra inteira funciona de verdade: 'Rio Preto' casa 'preto'.
    nav2, conf2, det2 = m._rio_e_navegavel("Rio Preto")
    assert nav2 is True and conf2 >= 85 and "preto" in det2


def test_riacho_pequeno_e_vazio():
    assert m._rio_e_navegavel("Riacho do Sapo")[0] is False
    assert m._rio_e_navegavel("")[0] is False
    assert m._rio_e_navegavel(None)[0] is False
