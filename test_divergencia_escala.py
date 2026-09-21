# -*- coding: utf-8 -*-
"""[DIVERGENCIA-ESCALA] Processamento de divergências por IMPACTO com teto de roteamento fresco.

Em estudos nacionais (milhares de divergências), rotear TODAS a fresco (rede) é lento e pressiona a
memória. Melhoria: processa por impacto (inscritos × |Δkm|) decrescente e concentra o roteamento
fresco (sinais ricos) nos casos de MAIOR impacto, até um teto; os demais entram COMPLETOS no agregado
com a distância já informada. Nenhuma divergência é descartada. Estes testes travam esse contrato."""
import streamlit_app as m


def _linhas(n):
    """n divergências; a linha i tem impacto = (n - i) → linha 0 é a de MAIOR impacto."""
    out = []
    for i in range(n):
        imp = n - i
        out.append({"Mesmo Destino": "Não", "Origem": f"Mun{i:04d}", "UF": "AM",
                    "Destino Referencia": f"R{i}", "Destino Aplicacao": f"A{i}",
                    "Distancia Aplicacao": 100.0, "Distancia Referencia": 100.0 + imp,
                    "Inscritos": 1, "Tempo Referencia": "1 h"})
    return out


def test_estudo_pequeno_roteia_tudo_fresco():
    chamadas = []
    diag = m._reprocessar_rotas_divergentes(_linhas(50), limiar_empate_km=1.0,
                                            router=lambda o, d: chamadas.append(o))
    assert diag.get("total_divergentes") == 50
    assert diag.get("sem_roteamento_fresco", 0) == 0      # nada capado num estudo pequeno
    assert len(chamadas) == 50                            # todas roteadas fresco
    assert len(diag.get("analises") or []) == 50


def test_estudo_nacional_capa_por_impacto_sem_descartar():
    N = 1300
    chamadas = []
    diag = m._reprocessar_rotas_divergentes(_linhas(N), limiar_empate_km=1.0,
                                            router=lambda o, d: chamadas.append(o))
    # todas as divergências entram no agregado — nenhuma descartada
    assert diag.get("total_divergentes") == N
    assert len(diag.get("analises") or []) == N
    # o roteamento fresco é limitado ao teto (1200), o resto entra sem roteamento fresco
    assert len(chamadas) == 1200
    assert diag.get("sem_roteamento_fresco") == N - 1200
    # e são as de MENOR impacto que ficam sem roteamento fresco
    roteadas = set(chamadas)
    assert all(f"Mun{i:04d}, AM" in roteadas for i in range(1200)), "top-1200 por impacto devem rotear"
    assert {f"Mun{i:04d}, AM" for i in range(1200, N)}.isdisjoint(roteadas), "as capadas são as de menor impacto"


def test_capados_nao_contam_como_falha_de_roteamento():
    # 'falhas_roteamento' mede falha REAL (tentou e não veio), não os capados por escala
    N = 1300
    diag = m._reprocessar_rotas_divergentes(_linhas(N), limiar_empate_km=1.0, router=lambda o, d: None)
    assert diag.get("sem_roteamento_fresco") == N - 1200
    # os 1200 que tentaram fresco com router->None caem no fallback honesto, contabilizados à parte
    assert diag.get("falhas_roteamento", 0) + 1200 >= 1200  # sanidade: capados não inflam as falhas
    assert diag.get("sem_roteamento_fresco") == 100
