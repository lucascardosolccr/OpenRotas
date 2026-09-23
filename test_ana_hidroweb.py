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
