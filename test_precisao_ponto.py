# -*- coding: utf-8 -*-
"""[ENDERECO-PRECISAO] `_precisao_ponto_endereco`: sinaliza quando a ENTRADA era um endereço específico
(via/nº de casa) mas o ponto obtido é apenas MUNICIPAL (centro/sede) — ou seja, a rota partiu do centro
do município, não do endereço. Antes isso passava silencioso na planilha. Estes testes travam o
disparo correto: só alarma endereço colapsado a município; não alarma município puro, código IBGE, nem
endereço bem resolvido."""
import streamlit_app as m


def test_endereco_colapsado_a_municipio_alarma():
    r = m._precisao_ponto_endereco("Rua das Flores, 123, Centro, Manaus, AM", "MUNICIPAL", "BASE_IBGE_CENTROIDE")
    assert r and "municipal" in r.lower()


def test_endereco_com_via_mas_confianca_alta_nao_alarma():
    assert m._precisao_ponto_endereco("Av. Brig. Faria Lima, 1000, São Paulo, SP", "ALTISSIMA", "ARCGIS") == ""
    assert m._precisao_ponto_endereco("Rua X, 50, Recife, PE", "ALTA", "TomTom") == ""


def test_municipio_puro_nao_alarma_mesmo_municipal():
    # município puro: precisão municipal é o resultado ESPERADO, não uma perda
    assert m._precisao_ponto_endereco("Manaus, AM", "MUNICIPAL", "IBGE (Base Oficial)") == ""
    assert m._precisao_ponto_endereco("Belo Horizonte, MG", "MUNICIPAL", "BASE_IBGE_OFFLINE") == ""


def test_codigo_ibge_nao_alarma():
    assert m._precisao_ponto_endereco("3550308", "MUNICIPAL", "IBGE_CODIGO_OFICIAL") == ""


def test_entrada_vazia_e_defensiva():
    assert m._precisao_ponto_endereco("", "MUNICIPAL", "x") == ""
    assert m._precisao_ponto_endereco(None, None, None) == ""


def test_numero_de_casa_conta_como_endereco():
    # sem palavra de logradouro, mas com número de casa plausível → é endereço
    r = m._precisao_ponto_endereco("Quadra 12, Casa 5, Palmas, TO", "MUNICIPAL", "BASE_IBGE_CENTROIDE")
    assert r != ""
