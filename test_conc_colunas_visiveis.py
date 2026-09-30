# -*- coding: utf-8 -*-
"""[CONC-FONTE-DIST / CONC-DIVERG-CLASSE] Dois campos da auditoria do 2º colocado eram CALCULADOS mas nunca
APARECIAM na planilha: a FONTE da distância do concorrente (`fonte_2o` — Google, OSRM real no fast-fail, ou
estimativa geodésica) e a CLASSE legível da divergência Google×OSRM (`divergencia_classe`). Agora ambos têm
coluna própria e estão na ordem oficial de colunas da alocação. Guardas de regressão contra silenciamento futuro."""
import streamlit_app as m


def test_colunas_novas_declaradas_na_ordem_oficial():
    cols = m.NOVAS_COLUNAS_ALOCACAO
    assert 'Fonte Distancia Concorrente' in cols
    assert 'Classe Divergencia Concorrente' in cols
    # posicionadas junto ao bloco do concorrente (perto da distância / da divergência)
    assert cols.index('Fonte Distancia Concorrente') > cols.index('Distancia Concorrente')
    assert cols.index('Classe Divergencia Concorrente') > cols.index('Divergencia Motores Concorrente (%)')


def test_colunas_textuais_nao_entram_na_coercao_numerica():
    # são rótulos textuais — não podem ser coeridas a número (viraria NaN e sumiria o texto)
    assert 'Fonte Distancia Concorrente' not in m.COLUNAS_NUMERICAS_ALOCACAO
    assert 'Classe Divergencia Concorrente' not in m.COLUNAS_NUMERICAS_ALOCACAO


def test_reindex_preserva_colunas_extras_do_concorrente():
    # a rede de segurança do reindex (lista branca) deve preservar QUALQUER coluna extra do resultado;
    # simula o padrão real: ordem = base + brancas, depois anexa extras não-artefato.
    import pandas as pd, re
    df = pd.DataFrame([{'Origem': 'A', 'Destino': 'B',
                        'Fonte Distancia Concorrente': 'OSRM (Google indisponível no fast-fail)',
                        'Classe Divergencia Concorrente': 'alta', '_3': 'artefato'}])
    ordem = ['Origem', 'Destino']
    for c in df.columns:
        if c in ordem:
            continue
        if re.fullmatch(r'_\d+', str(c)) or str(c).startswith('Unnamed:'):
            continue
        ordem.append(c)
    out = df.reindex(columns=ordem)
    assert 'Fonte Distancia Concorrente' in out.columns
    assert 'Classe Divergencia Concorrente' in out.columns
    assert '_3' not in out.columns  # artefato posicional descartado, como no app
