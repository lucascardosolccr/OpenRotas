# -*- coding: utf-8 -*-
"""[ENDERECO-PRECISAO] Novas abreviações de logradouro/toponímia na normalização de endereços. Elas
melhoram DUAS coisas para endereços de casas e locais:
  1) o casamento OFFLINE de município — "Sto/Sta ..." não batia com a base "SANTO/SANTA ..." e caía na
     nuvem (mais lento e menos determinístico);
  2) a geocodificação de vias com honoríficos — "Av. Brig. Faria Lima", "Av. Alm. Barroso",
     "Av. Mal. Deodoro" casam melhor nos geocoders quando escritas por extenso.
CONTRATO DE SEGURANÇA: nenhuma nova abreviação pode colidir com um TOKEN de nome de município oficial
(a classe de bug 'VER→VEREADOR' em 'Venha-Ver/RN'). Este teste trava isso contra a base real embarcada."""
import streamlit_app as m

# tokens que passamos a expandir (devem casar com o que foi adicionado em streamlit_app.py)
NOVAS = {"STO", "STA", "MAL", "BRIG", "ALM", "IRM", "PTE"}


def test_nenhuma_nova_abreviacao_colide_com_token_de_municipio():
    # nenhum nome oficial de município pode conter um desses tokens isolado — senão a expansão o corromperia
    colisoes = {}
    for _nome in m.IBGE_MUNICIPIOS.keys():
        _toks = set(str(_nome).upper().split())
        _c = _toks & NOVAS
        if _c:
            colisoes.setdefault(frozenset(_c), []).append(_nome)
    assert not colisoes, f"abreviação colide com nome de município: {colisoes}"


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
