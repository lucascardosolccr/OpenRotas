# -*- coding: utf-8 -*-
"""[COMPARA-JUSTA] O veredito "qual estudo reduz mais o DESLOCAMENTO total?" não pode ser decidido por
distâncias da REFERÊNCIA fisicamente impossíveis (menores que a linha reta geodésica — nenhuma estrada
é mais curta que o 'voo de pássaro'). Motivado por um estudo real (comparacao_estudos_8): 1.515 de 2.439
municípios tinham distância de referência impossível, e somá-las inflava o total da referência, fazendo
a aplicação 'perder' o confronto por 716 mil km-candidato — 4× o número honesto (181 mil). O app já
NEUTRALIZA esse número bogus POR LINHA (economia zerada em _comparar_alocacoes); faltava neutralizá-lo no
agregado. Agora o total de CADA estudo soma só as linhas com distância de referência válida; as
impossíveis já são vitória da aplicação, contadas à parte. Prova offline (puro, sem motor de rotas)."""
import streamlit_app as m


def _linha(origem, uf, da, dr, reta_ref, insc, inval=""):
    return {
        "Origem": origem, "UF": uf, "Inscritos": insc,
        "Destino Aplicacao": origem + "-APP", "Destino Referencia": origem + "-REF",
        "Distancia Aplicacao": da, "Distancia Referencia": dr,
        "Linha Reta Referencia (km)": reta_ref,
        "Vencedor Distancia": "Aplicação" if inval else ("Aplicação" if da <= dr else "Referência"),
        "Vitoria por Ref Invalida": inval,   # "Sim" marca a referência como impossível
    }


def _q_deslocamento(linhas):
    d = m._diagnostico_imparcial(linhas)
    for p in d.get("perguntas", []):
        if "DESLOCAMENTO" in p["Pergunta"]:
            return p
    return None


def test_impossivel_fora_do_confronto_de_total():
    # Linha VÁLIDA: app 100 × ref 90 (reta 60 → válida) → nessa linha a referência é mais curta.
    # Linha IMPOSSÍVEL: ref diz 50 km mas a reta é 120 km (impossível); a app mediu 180 km reais.
    # Sem o filtro, a ref somaria 50×100 e 'venceria' o total por um número que nenhuma estrada percorre.
    val = _linha("Valida", "SP", da=100.0, dr=90.0, reta_ref=60.0, insc=10)
    imp = _linha("Impossivel", "AM", da=180.0, dr=50.0, reta_ref=120.0, insc=100, inval="Sim")
    p = _q_deslocamento([val, imp])
    assert p is not None
    # confronto só na linha válida: app 100×10=1000, ref 90×10=900 → diferença 100 (não o bogus 50×100).
    assert "100 km-candidato" in p["Resposta"]
    assert "1 município" in p["Base"]
    assert "menor que a linha reta" in p["Base"].lower()


def test_sem_impossiveis_todas_as_linhas_contam():
    # Nenhuma referência impossível → confronto sobre TODAS as linhas, sem exclusões (comportamento base).
    a = _linha("A", "SP", da=80.0, dr=100.0, reta_ref=60.0, insc=10)
    b = _linha("B", "RJ", da=70.0, dr=90.0, reta_ref=50.0, insc=5)
    p = _q_deslocamento([a, b])
    assert p is not None and "A NOSSA aplicação" in p["Resposta"]
    # app: 80×10 + 70×5 = 1150 ; ref: 100×10 + 90×5 = 1450 → diferença 300, nenhuma exclusão.
    assert "300 km-candidato" in p["Resposta"]
    assert "fora do confronto" not in p["Base"]


def test_perfil_ref_exclui_impossiveis_das_estatisticas_mas_preserva_cobertura():
    # A REFERÊNCIA reporta 1 distância válida (90, reta 60) e 1 impossível (20, reta 120). O PERFIL dela
    # deve: (a) calcular média/máx SÓ sobre a válida; (b) preservar a cobertura (2 municípios, polos);
    # (c) expor quantas foram excluídas; (d) o 'deslocamento total' da tabela bate com o veredito.
    val = _linha("Valida", "SP", da=100.0, dr=90.0, reta_ref=60.0, insc=10)
    imp = _linha("Impossivel", "AM", da=200.0, dr=20.0, reta_ref=120.0, insc=10, inval="Sim")
    d = m._diagnostico_imparcial([val, imp])
    pr, pa = d["perfil_ref"], d["perfil_app"]
    # (a) média da ref só sobre a válida (90), não contaminada pela impossível (20):
    assert pr["dist_media_km"] == 90.0 and pr["dist_maxima_km"] == 90.0
    # (b) cobertura preservada: a ref cobre os 2 municípios e seus polos (só reportou distância errada):
    assert pr["municipios"] == 2 and pr["locais_de_prova"] == 2
    # (c) transparência:
    assert pr["municipios_distancia_valida"] == 1 and pr["distancias_invalidas_excluidas"] == 1
    assert pa["distancias_invalidas_excluidas"] == 0   # a app não tem linhas impossíveis
    # (d) o 'deslocamento total' dos dois perfis é o do MESMO conjunto válido → subtrair bate o veredito:
    assert round(pa["km_candidato_total"] - pr["km_candidato_total"], 1) == 100.0  # app 100*10 - ref 90*10


def test_placar_separa_vitorias_por_referencia_invalida():
    # O placar de vitórias é o CONFRONTO físico-válido; as vitórias por referência impossível ficam À
    # PARTE (vitória de VALIDADE do dado, não de km) e não entram no % do confronto.
    val_app = _linha("AppVence", "SP", da=50.0, dr=90.0, reta_ref=40.0, insc=10)   # app < ref → app
    val_ref = _linha("RefVence", "RJ", da=100.0, dr=70.0, reta_ref=50.0, insc=10)  # ref < app → ref
    imp = _linha("Impossivel", "AM", da=200.0, dr=20.0, reta_ref=120.0, insc=10, inval="Sim")
    d = m._diagnostico_imparcial([val_app, val_ref, imp])
    pl = d["placar"]
    assert pl["total"] == 2 and pl["total_comparado"] == 3
    assert pl["aplicacao"] == 1 and pl["concorrente"] == 1
    assert pl["vitorias_ref_invalida"] == 1          # a impossível não entra no confronto
    assert pl["aplicacao"] + pl["concorrente"] + pl["empates"] == pl["total"]
    # os percentuais usam o conjunto válido (2), não o total (3):
    assert pl["pct_aplicacao"] == 50.0 and pl["pct_concorrente"] == 50.0


def test_piso_geodesico_tambem_detecta_sem_rotulo():
    # Mesmo SEM o rótulo 'Vitoria por Ref Invalida', a rede de segurança (ref < linha reta) exclui a linha.
    val = _linha("Valida", "SP", da=100.0, dr=90.0, reta_ref=60.0, insc=10)
    imp = _linha("ImpSemRotulo", "PA", da=180.0, dr=50.0, reta_ref=120.0, insc=100, inval="")
    assert m._ref_distancia_impossivel(imp) is True
    assert m._ref_distancia_impossivel(val) is False
    p = _q_deslocamento([val, imp])
    assert "100 km-candidato" in p["Resposta"] and "1 município" in p["Base"]
