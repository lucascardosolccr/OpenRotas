# inteligencia_geoespacial/tests/test_registry.py
import pytest
from datetime import datetime
from inteligencia_geoespacial.fontes_registry import SourceRegistry, SourcesRegistry, SourceStatus

def test_registry_add_source():
    registry = SourcesRegistry()
    source = SourceRegistry(
        id="ibge_municipios",
        nome="IBGE - Malhas Municipais 2025",
        orgao="IBGE",
        categoria="territorial",
        dataset_url="https://geoftp.ibge.gov.br/",
        api_endpoint=None,
        api_docs_url=None,
        formato="Shapefile",
        tipo_geometria="Polygon",
        sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil",
        registros_totais=5570,
        data_atualizacao=datetime(2025, 1, 1),
        periodicidade="Anual",
        qualidade={"completude": 1.0, "acuracia": 0.99},
        licenca="CC0",
        atribuicao_obrigatoria="IBGE",
        restricoes="Nenhuma",
        campos_disponiveis=["CODIGO_IBGE", "NOME", "GEOMETRIA", "AREA_KM2"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=None,
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2026, 1, 1),
        notas="Malhas oficiais de jurisdição",
        responsavel_validacao=None
    )

    registry.register(source)
    assert registry.get("ibge_municipios") is not None
    assert registry.get("ibge_municipios").registros_totais == 5570

def test_registry_list_by_category():
    registry = SourcesRegistry()
    source1 = SourceRegistry(
        id="test1", nome="Test 1", orgao="Org1", categoria="territorial",
        dataset_url="http://test.com", api_endpoint=None, api_docs_url=None,
        formato="GeoJSON", tipo_geometria="Point", sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil", registros_totais=100,
        data_atualizacao=datetime.now(), periodicidade="Anual",
        qualidade={}, licenca="CC0", atribuicao_obrigatoria="Test",
        restricoes="Nenhuma", campos_disponiveis=[], status=SourceStatus.ATIVO,
        data_ultimo_teste=None, tempo_resposta_ms=None,
        proxima_validacao=datetime.now(), notas="", responsavel_validacao=None
    )
    registry.register(source1)

    result = registry.list_by_category("territorial")
    assert len(result) == 1
    assert result[0].id == "test1"
