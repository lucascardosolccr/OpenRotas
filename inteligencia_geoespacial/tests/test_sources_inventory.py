"""Testes do catálogo REAL de fontes (Rodada 2 da missão "extração máxima").

O objetivo destes testes não é só "não quebrar" — é impedir que o catálogo
volte a acumular metadados fabricados (a falha que motivou reescrever o
módulo do zero): nenhuma agência sem integração real, nenhum endpoint de
API para uma fonte que só é lida do disco, nenhuma contagem de registros
inventada.
"""
import json
import os

import pytest

from inteligencia_geoespacial.sources_inventory import populate_sources
from inteligencia_geoespacial.fontes_registry import SourceStatus

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MANIFEST = os.path.join(_RAIZ, "data", "brasil", "ibge", "derivadas", "manifest.json")


def test_populate_sources_nao_esta_vazio():
    registry = populate_sources()
    assert len(registry.sources) >= 30


def test_ids_sao_unicos():
    registry = populate_sources()
    ids = list(registry.sources.keys())
    assert len(ids) == len(set(ids))


def test_modo_acesso_sempre_num_conjunto_valido():
    registry = populate_sources()
    validos = {"api_rest_ao_vivo", "arquivo_local", "download_sob_demanda", "informativo_apenas"}
    for src in registry.sources.values():
        assert src.modo_acesso in validos, f"{src.id}: modo_acesso={src.modo_acesso!r}"


def test_api_endpoint_so_existe_quando_modo_e_api_ao_vivo():
    # Invariante central desta rodada: nunca declarar um api_endpoint "vivo"
    # para uma fonte que na verdade é lida do disco (era exatamente o
    # problema do catálogo anterior — ANTAQ/DNIT/ANTT com endpoints que o
    # código nunca chama).
    registry = populate_sources()
    for src in registry.sources.values():
        if src.api_endpoint is not None:
            assert src.modo_acesso == "api_rest_ao_vivo", (
                f"{src.id}: tem api_endpoint mas modo_acesso={src.modo_acesso!r}")


def test_nenhuma_agencia_sem_integracao_real_aparece_como_fonte_ativa():
    # ANTAQ/DNIT/ANTT/DER não têm integração própria hoje (a auditoria
    # confirmou: os dados atribuídos a elas na UI antiga são, na verdade,
    # colunas dentro do BC250/BC100 do IBGE). Não podem voltar a aparecer
    # como "orgao" de uma fonte marcada ATIVO.
    registry = populate_sources()
    orgaos_sem_integracao_propria = {"ANTAQ", "DNIT", "ANTT", "DER"}
    for src in registry.sources.values():
        orgao_norm = src.orgao.split(" ")[0].split("(")[0].strip().upper()
        assert orgao_norm not in orgaos_sem_integracao_propria or src.status != SourceStatus.ATIVO, (
            f"{src.id}: {src.orgao!r} não tem integração real confirmada, não deveria estar ATIVO")


@pytest.mark.skipif(not os.path.exists(_MANIFEST), reason="manifest.json ausente neste ambiente")
def test_contagens_das_camadas_ibge_batem_com_o_manifest_real():
    with open(_MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    camadas = manifest.get("camadas", {})
    assert camadas, "manifest.json sem seção 'camadas' — formato inesperado"

    registry = populate_sources()
    checadas = 0
    for camada, info in camadas.items():
        n_manifest = info.get("registros")
        if n_manifest is None:
            continue
        src = registry.get(f"ibge_bc250_{camada}")
        assert src is not None, f"camada {camada!r} do manifest não tem entrada no catálogo"
        assert src.registros_totais == n_manifest, (
            f"{camada}: catálogo diz {src.registros_totais}, manifest.json diz {n_manifest}")
        checadas += 1
    assert checadas >= 10  # as 12 camadas do BC250/BC100 devem estar todas no manifest


def test_registros_totais_nunca_negativo_quando_informado():
    registry = populate_sources()
    for src in registry.sources.values():
        if src.registros_totais is not None:
            assert src.registros_totais >= 0


def test_to_dataframe_funciona_com_datas_desconhecidas():
    # Várias fontes locais não têm data de atualização conhecida
    # (data_atualizacao=None) — o dataframe precisa lidar com isso sem
    # fabricar uma data, não sem quebrar.
    registry = populate_sources()
    df = registry.to_dataframe()
    assert len(df) == len(registry.sources)
    assert (df["Atualização"] == "Não informada").any()
    assert not df["Atualização"].isna().any()


def test_fonte_orfa_esta_marcada_inativa_e_sem_uso():
    registry = populate_sources()
    orfao = registry.get("localidades_brasil_shp_orfao")
    assert orfao is not None
    assert orfao.status == SourceStatus.INATIVO
    assert orfao.uso_no_motor == ""


# ==============================================================================
# Missão 2 / Rodada 11 — Saúde dos Dados (§19): checagens 100% locais
# (existência de arquivo, contagem real vs manifest.json, mtime) — nunca
# uma chamada de rede.
# ==============================================================================

def test_saude_dos_dados_estrutura_basica():
    from inteligencia_geoespacial.sources_inventory import saude_dos_dados
    r = saude_dos_dados()
    for chave in ("fontes_catalogadas", "fontes_ativas", "apis_ao_vivo", "camadas_ibge",
                  "camadas_com_arquivo_presente", "camadas_total", "bootstrap_ausentes"):
        assert chave in r


def test_saude_dos_dados_nunca_fabrica_manifest_quando_ausente(monkeypatch, tmp_path):
    from inteligencia_geoespacial import sources_inventory as si
    # Aponta para um "repositório" vazio (sem manifest.json) e confirma que
    # o relatório degrada honestamente (camadas vazias), não inventa dado.
    _fake = str(tmp_path / "inteligencia_geoespacial" / "sources_inventory.py")
    monkeypatch.setattr(os.path, "abspath", lambda p: _fake)
    r = si.saude_dos_dados()
    assert r["camadas_ibge"] == []
    assert r["camadas_total"] == 0
    assert r["extraido_em_utc_manifest"] is None


@pytest.mark.skipif(not os.path.exists(_MANIFEST), reason="manifest.json ausente neste ambiente")
def test_saude_dos_dados_contagens_reais_batem_com_manifest():
    from inteligencia_geoespacial.sources_inventory import saude_dos_dados
    r = saude_dos_dados()
    assert r["camadas_total"] >= 10
    assert r["camadas_divergentes_do_manifest"] == []
    for c in r["camadas_ibge"]:
        if c["existe"]:
            assert c["bate_com_manifest"] is True
            assert c["registros_reais"] == c["registros_manifest"]


@pytest.mark.skipif(not os.path.exists(_MANIFEST), reason="manifest.json ausente neste ambiente")
def test_saude_dos_dados_qualidade_media_e_fracao_valida():
    from inteligencia_geoespacial.sources_inventory import saude_dos_dados
    r = saude_dos_dados()
    if r["qualidade_media_completude"] is not None:
        assert 0.0 <= r["qualidade_media_completude"] <= 1.0
