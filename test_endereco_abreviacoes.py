# -*- coding: utf-8 -*-
"""[ENDERECO-PRECISAO] Novas abreviações de logradouro/toponímia na normalização de endereços. Elas
melhoram DUAS coisas para endereços de casas e locais:
  1) o casamento OFFLINE de município — "Sto/Sta ..." não batia com a base "SANTO/SANTA ..." e caía na
     nuvem (mais lento e menos determinístico);
  2) a geocodificação de vias com honoríficos — "Av. Brig. Faria Lima", "Av. Alm. Barroso",
     "Av. Mal. Deodoro" casam melhor nos geocoders quando escritas por extenso.
CONTRATO DE SEGURANÇA: nenhuma nova abreviação pode colidir com um TOKEN de nome de município oficial
(a classe de bug 'VER→VEREADOR' em 'Venha-Ver/RN'). Este teste trava isso contra a base real embarcada."""
import re

from unidecode import unidecode

import streamlit_app as m

# tokens que passamos a expandir (devem casar com o que foi adicionado em streamlit_app.py)
NOVAS = {"STO", "STA", "MAL", "BRIG", "ALM", "IRM", "PTE",
         "MARQ", "TEN", "CMTE", "CONS", "LGO"}


def _tokens(s):
    # tokenização IGUAL à do pipeline (unidecode + upper + troca não-alfanumérico por espaço).
    # CRÍTICO: um `.split()` ingênuo NÃO separa "VENHA-VER" (fica 1 token) e daria falso-negativo —
    # exatamente a classe de bug VER→VEREADOR. Precisa quebrar no hífen como o normalizador quebra.
    return set(t for t in re.sub(r"[^A-Z0-9]", " ", unidecode(str(s)).upper()).split() if t)


def test_nenhuma_nova_abreviacao_colide_com_token_de_municipio():
    # nenhum nome oficial de município (chave OU nome do item) pode conter um desses tokens isolado —
    # senão a expansão o corromperia. Tokenização completa (pega hifenizados como "Venha-Ver").
    colisoes = {}
    for _nome, _itens in m.IBGE_MUNICIPIOS.items():
        _candidatos = [_nome] + [str(i.get("municipio", "")) for i in _itens]
        for _nm in _candidatos:
            _c = _tokens(_nm) & NOVAS
            if _c:
                colisoes.setdefault(frozenset(_c), set()).add(_nm)
    assert not colisoes, f"abreviação colide com nome de município: {colisoes}"


def test_guarda_pegaria_o_caso_ver_veredor():
    # meta-teste: a tokenização usada AQUI tem de pegar "VENHA-VER" (token VER) — se não pegar, a
    # guarda acima é falsa. Trava a robustez da própria guarda contra futuras adições.
    achou = [n for n in m.IBGE_MUNICIPIOS if "VER" in _tokens(n)]
    assert achou, "a guarda de colisão não separa hifenizados — estaria dando falso-negativo"


def test_expande_santo_santa_e_honorificos():
    _n = m.semantica.normalizar
    assert "SANTO" in _n("Sto Antonio").split()
    assert "SANTA" in _n("Sta Rita").split()
    assert "MARECHAL" in _n("Av Mal Deodoro").split()
    assert "BRIGADEIRO" in _n("Av Brig Faria Lima").split()
    assert "ALMIRANTE" in _n("Av Alm Barroso").split()
    assert "PONTE" in _n("Pte Rio Branco").split()


def test_sta_permite_resolucao_offline_do_municipio():
    # antes: "Sta Cruz do Sul, RS" não batia com "SANTA CRUZ DO SUL" na base → ia para a nuvem.
    r = m._resolver_municipio_offline("Sta Cruz do Sul, RS")
    assert r is not None
    assert r["estado"] == "RS"
    assert "SANTA CRUZ DO SUL" in str(r["cidade"]).upper()


def test_uf_alagoas_intacta_apos_mudanca():
    # regressão: a UF AL (Alagoas) continua NÃO virando ALAMEDA, e MAL não afeta municípios reais
    _n = m.semantica.normalizar
    assert "ALAMEDA" not in _n("Santana do Ipanema, AL")
    # "Mallet/PR" (token MALLET) não pode ser tocado por MAL→MARECHAL
    assert "MARECHAL" not in _n("Mallet, PR")
