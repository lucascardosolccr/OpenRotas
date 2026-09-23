# -*- coding: utf-8 -*-
"""[ANA WEBSERVICE PÚBLICO] Extrai o máximo da ANA/SNIRH sem token: HidroSerieHistorica (cotas/vazões/chuvas)
e DadosHidrometeorologicos (telemetria). Os PARSERS são puros (sem rede) — estes testes travam o formato real
que a ANA devolve: colunas diárias por mês (Cota01..31 / Vazao01..31 / Chuva01..31) e o elemento de telemetria
que a ANA grafa com erro ('DadosHidrometereologicos')."""
from datetime import datetime

from inteligencia_geoespacial import ana_hidroweb as a


def test_tipo_dados_e_unidades():
    assert a.TIPO_DADOS["vazões"] == 3 and a.TIPO_DADOS["cotas"] == 1 and a.TIPO_DADOS["chuvas"] == 2
    assert a.UNIDADE[3] == "m³/s" and a.UNIDADE[1] == "cm" and a.UNIDADE[2] == "mm"


def test_parse_serie_historica_desempilha_dias_e_le_virgula_decimal():
    xml = ("<DataTable><DocumentElement>"
           "<SerieHistorica><EstacaoCodigo>17050001</EstacaoCodigo><DataHora>2020-01-01T00:00:00</DataHora>"
           "<Maxima>1500</Maxima><Vazao01>1000</Vazao01><Vazao02>1100.5</Vazao02><Vazao03>1200,7</Vazao03>"
           "<Vazao04></Vazao04></SerieHistorica>"
           "<SerieHistorica><EstacaoCodigo>17050001</EstacaoCodigo><DataHora>2020-02-01T00:00:00</DataHora>"
           "<Vazao01>900</Vazao01></SerieHistorica>"
           "</DocumentElement></DataTable>")
    s = a.parse_serie_historica(xml, 3)
    assert len(s) == 4                                  # 3 dias de jan + 1 de fev (Vazao04 vazio ignorado)
    assert s[0]["data"] == datetime(2020, 1, 1) and s[0]["valor"] == 1000.0
    assert s[2]["valor"] == 1200.7                      # vírgula decimal tratada
    assert s[3]["data"] == datetime(2020, 2, 1) and s[3]["valor"] == 900.0


def test_parse_serie_historica_prefixo_por_tipo():
    xml = ("<DocumentElement><SerieHistorica><DataHora>2021-03-01T00:00:00</DataHora>"
           "<Cota01>250</Cota01><Cota02>251</Cota02></SerieHistorica></DocumentElement>")
    s = a.parse_serie_historica(xml, 1)               # tipo 1 = Cotas → prefixo 'Cota'
    assert [r["valor"] for r in s] == [250.0, 251.0]
    # com o prefixo errado (vazões) não acha nada
    assert a.parse_serie_historica(xml, 3) == []


def test_parse_telemetria_com_grafia_da_ana():
    xml = ("<DocumentElement>"
           "<DadosHidrometereologicos><DataHora>2024-05-01 12:00:00</DataHora><Nivel>250</Nivel>"
           "<Vazao>1200</Vazao><Chuva>0</Chuva></DadosHidrometereologicos>"
           "<DadosHidrometereologicos><DataHora>2024-05-01 13:00:00</DataHora><Nivel>251</Nivel>"
           "<Vazao>1210</Vazao><Chuva>2,5</Chuva></DadosHidrometereologicos>"
           "</DocumentElement>")
    t = a.parse_telemetria(xml)
    assert len(t) == 2
    assert t[0]["nivel"] == 250.0 and t[0]["vazao"] == 1200.0
    assert t[1]["chuva"] == 2.5


def test_parsers_fail_open_em_xml_invalido():
    assert a.parse_serie_historica("<nao-fecha", 3) == []
    assert a.parse_serie_historica("", 1) == []
    assert a.parse_telemetria(None) == []


# ---- Rede nacional LOCAL (asset versionado) + integração ao enriquecimento de rotas ----------
def test_rede_nacional_local_e_estacao_mais_proxima():
    rede = a.carregar_rede_nacional()
    assert len(rede) > 1000, "a rede nacional local deve carregar milhares de estações"
    e = a.estacao_mais_proxima(-3.119, -60.0217)      # Manaus
    assert e and e["uf"] == "AM" and e["distancia_km"] < 20
    assert str(e["codigo"]).isdigit()
    # ponto no oceano → sem estação (fail-open)
    assert a.estacao_mais_proxima(-20.0, -30.0) is None


def test_enriquecimento_de_ponto_carrega_estacao_ana():
    from inteligencia_geoespacial import enrichment_engine as e, xai_formatter as x
    enr = e.enriquecer_ponto(-3.119, -60.0217, raio_km=30, limite=5)
    est = enr.get("estacao_ana")
    assert est and est["uf"] == "AM", "o enriquecimento da rota deve receber a estação ANA de referência"
    md = x.formatar_ponto(enr)
    assert "Estação ANA" in md and est["codigo"] in md


# ---- Estação de referência EXATA: casa pelo mesmo rio + classificação direta/aproximada/regional -----
def test_referencia_casa_pelo_mesmo_rio_e_classifica():
    # Manaus SEM rio → mais próxima, mas rio não confirmado → 'aproximada'
    s0 = a.estacao_de_referencia(-3.119, -60.0217)
    assert s0["mesmo_rio"] is False and s0["classificacao"] == "aproximada"
    # Manaus COM 'Rio Negro' → mesmo rio e próxima → 'direta'
    s1 = a.estacao_de_referencia(-3.119, -60.0217, "Rio Negro")
    assert s1["mesmo_rio"] is True and s1["classificacao"] == "direta"
    assert s1["rio_consultado"] == "Rio Negro"


def test_referencia_casamento_fuzzy_de_rio():
    # 'Rio Solimões' casa com 'RIO SOLIMÕES-AMAZONAS' (um contém o outro)
    assert a._rios_casam("Rio Solimões", "RIO SOLIMÕES-AMAZONAS") is True
    # prefixos e acentos normalizados
    assert a._norm_rio("Rio Negro") == "NEGRO" and a._norm_rio("Igarapé Tarumã") == "TARUMA"
    # rios diferentes não casam
    assert a._rios_casam("Rio Negro", "Rio Branco") is False


def test_referencia_prefere_rio_certo_mesmo_mais_longe():
    # perto de um ponto, escolher o rio pedido pode trazer uma estação mais distante que a mais próxima geral
    perto = a.estacao_de_referencia(-3.5, -60.5)                 # mais próxima qualquer
    solimoes = a.estacao_de_referencia(-3.5, -60.5, "Rio Solimões")
    assert solimoes is not None and solimoes["mesmo_rio"] is True
    assert a._rios_casam(solimoes["rio"], "Solimões")


def test_estacao_mais_proxima_ainda_funciona():
    e = a.estacao_mais_proxima(-23.55, -46.63)                  # São Paulo
    assert e and "codigo" in e and "distancia_km" in e
