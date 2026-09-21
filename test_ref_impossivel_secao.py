# -*- coding: utf-8 -*-
"""[AUDITORIA-REF-IMPOSSIVEL] `_secao_ref_impossivel_html`: seção HTML da comparação que aponta as
distâncias da referência fisicamente impossíveis/implausíveis. A tabela mostra só as `top` de maior
déficit, mas o KPI conta TODAS — sem uma nota de truncamento, num estudo nacional o KPI ("150
impossíveis") e a tabela (40 linhas) se contradiziam em silêncio. Estes testes travam a nota honesta."""
import streamlit_app as m


def _linha_impossivel(i):
    return {"Origem": f"Mun{i}", "Destino Referencia": f"Polo{i}",
            "Auditoria Distancia Referencia": "IMPOSSÍVEL — menor que a linha reta",
            "Distancia Referencia": 10.0, "Linha Reta Referencia (km)": 100.0 + i,
            "Explicacao Auditoria Referencia": "menor que o piso físico", "Inscritos": 5}


def test_sem_truncamento_ate_o_teto():
    html = m._secao_ref_impossivel_html([_linha_impossivel(i) for i in range(10)], top=40)
    assert html
    assert "no total" not in html  # 10 < 40 → sem nota de truncamento


def test_nota_de_truncamento_acima_do_teto():
    html = m._secao_ref_impossivel_html([_linha_impossivel(i) for i in range(120)], top=40)
    assert html
    assert "de <b>120</b> no total" in html   # KPI conta 120, tabela mostra 40 → nota honesta
    assert "planilha exportável" in html


def test_sem_casos_retorna_vazio():
    assert m._secao_ref_impossivel_html([], top=40) == ""
    assert m._secao_ref_impossivel_html([{"Auditoria Distancia Referencia": "Plausível"}], top=40) == ""
