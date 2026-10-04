# -*- coding: utf-8 -*-
"""Configuração global do pytest.

Alguns testes de inteligência geoespacial dependem de bases derivadas GRANDES que NÃO são
versionadas por tamanho (drenagem.parquet ~451 MB, rodovias.parquet ~121 MB; ver .gitignore).
Elas são geradas localmente por `construir_bases_locais_ibge.py`. Num checkout limpo (ex.: CI),
esses arquivos não existem e os testes que os acessam falhariam com FileNotFoundError.

Para manter o CI confiável SEM inchar o repositório, pulamos AUTOMATICAMENTE os testes que
precisam dessas bases QUANDO (e somente quando) elas estão ausentes. No ambiente de quem tem as
bases (desenvolvimento), nada é pulado — a cobertura permanece completa."""
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parent
_DERIVADAS = _RAIZ / "data" / "brasil" / "ibge" / "derivadas"

# Bases derivadas grandes, não versionadas (gitignore), de que alguns testes dependem.
_BASES_PESADAS = ["drenagem.parquet", "rodovias.parquet"]
_FALTAM = [nome for nome in _BASES_PESADAS if not (_DERIVADAS / nome).exists()]

# Arquivos de teste que acessam essas bases (acesso direto ou via enriquecimento de ponto/rota).
_TESTES_DEPENDENTES = {
    "test_enrichment.py",
    "test_evaluation.py",
    "test_route_context.py",
    "test_validators.py",
    "test_xai.py",
    "test_ana_hidroweb.py",
    "test_rodovias_local.py",
}


def pytest_collection_modifyitems(config, items):
    if not _FALTAM:
        return
    motivo = ("requer bases derivadas grandes ausentes neste ambiente: %s "
              "(não versionadas por tamanho; gere com construir_bases_locais_ibge.py)"
              % ", ".join(_FALTAM))
    marca = pytest.mark.skip(reason=motivo)
    for item in items:
        if Path(str(item.fspath)).name in _TESTES_DEPENDENTES:
            item.add_marker(marca)
