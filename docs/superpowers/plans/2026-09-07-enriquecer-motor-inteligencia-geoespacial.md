# Enriquecimento Exaustivo do Motor de Inteligência Geoespacial

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task with review checkpoints between phases.

> ## STATUS REAL DA IMPLEMENTAÇÃO (2026-09-07)
>
> Feito em sessões anteriores: Tasks 1-2 (registry/inventário — `sources_inventory.py` com 51 fontes, `docs/FONTES_BRASILEIRAS.md`, `docs/PESQUISA_FONTES.md`), Task 3 (abstração `providers/base.py` + `caches/` + `test_providers.py`).
>
> Nesta rodada:
> - **Task 4 (provider unificado)** — em vez de 5 adapters de rede, implementado o adaptador local `providers/ibge_derivadas_provider.py` (`IBGEDerivadasProvider` sobre `bases_locais`, conta com `wkb_para_geojson`) + `providers/factory.py` (`ProviderFactory.criar` resolve `ibge_der_*` automaticamente). Testes: `test_provider_ibge_derivadas.py` (13 casos). Sem rede/GDAL.
> - **Task 6 (enrichment engine)** — `inteligencia_geoespacial/enrichment_engine.py` (`enriquecer_ponto`, `enriquecer_rota` com todos os campos previstos) + `validators.py` (camada de validação cruzada). No app, SEÇÃO 18 "Rotas com Balsa" ganhou card "🧠 Enriquecimento geoespacial da rota" que usa as coordenadas REAIS da rota (`ultima_rota_individual`/1ª linha do estudo) e roda `enriquecer_rota` em demanda.
> - **Task 7 (XAI formatter)** — `inteligencia_geoespacial/xai_formatter.py` (`formatar_confianca`, `formatar_ponto`, `formatar_enriquecimento`, `formatar_enriquecimento_html`); renderizado nas SEÇÕES 22 (ponto) e 18 (rota).
> - **Task 8 (zero regressão)** — gates conferidas: `validar` **192 OK / 0 FALHAS**, `decidir` **100%** (38/38), `relatorio` regera `_RELATORIO_ANTES_DEPOIS.md` (203 linhas, EXIT 0). `_testes_motor_rotas.py` ganhou marcadores de fase (PHASE 6). Nada do enriquecimento alterou os números.
> - **Task 9 (medição)** — `inteligencia_geoespacial/evaluation.py` + `docs/ANTES_DEPOIS_ENRIQUECIMENTO.md`: sobre as 163 derrotas do baseline 1452 → **96 residuais (-41% explicadas por balsa/fluvial/infra aquaviária; alvo ≥20%)**, **72 balsas confirmadas** (baseline 21; alvo 35+), **100% de explicação auditável** (alvo ≥95%). Cache em `cache_geoespacial/evaluation_enriquecimento.json` (~2,3 s/derrota sem cache, 0,01 s com). Testes: `test_evaluation.py` (4 casos).
> - **Task 10 (docs)** — `HANDBOOK.md` (roadmap + status), `docs/ARQUITETURA_INTELIGENCIA.md`, `docs/GUIA_INTEGRACAO_NOVOS_DADOS.md`.
> - **Task 11 (integração/produção)** — checklist verificado: registry com 51 fontes (12 `ibge_der_*`), `ProviderFactory.criar("ibge_der_pontes")` → 5 feições/5 GeoJSON em 0,85 s; cache operacional; painel XAI ligado à rota real (SEÇÃO 18) e ao ponto (SEÇÃO 22); `validar` 192 OK; `decidir` 100%; pytest 63 passed / 1 falha pré-existente (`test_cache_read`, tuple↔list JSON); performance < 5 s. **Commit final NÃO executado** (depende de pedido explícito do usuário).

**Goal:** Transform the routing engine into a comprehensive geographical intelligence system that combines official Brazilian data sources to intelligently detect routes, ferries, rivers, bridges, and provide auditable decisions.

**Architecture:** Hierarchical layer approach:
- **Layer 1 (Foundation):** Centralized source registry + validation framework
- **Layer 2 (Integration):** Modular provider adapters for each data source (ANTAQ, DNIT, ANA, IBGE, PRF, CEMADEN, etc)
- **Layer 3 (Intelligence):** Cross-source validation, enrichment pipeline, and decision audit trail
- **Layer 4 (UI):** Enhanced XAI panel showing data fusion decisions and reasoning

**Tech Stack:** Python 3.9+, Streamlit 1.28+, Pandas, GeoPandas, Shapely, requests, SQLite/DuckDB for caching, plotly for visualization

**Spec:** `/1111111.md` (30-point comprehensive specification)

## Global Constraints

- **Zero Regression:** Must maintain 192 passing tests and 38/38 decision tests
- **Python Syntax:** `-X utf8` mode mandatory for all executions
- **Backward Compat:** All changes MUST be additive; no destructive modifications
- **Caching Strategy:** All remote API calls cached locally (file or SQLite)
- **Brazil-Centric:** All coordinates use EPSG:4326; distances in km (viária)
- **Auditability:** Every decision must be traceable to source(s) with confidence scores

---

# PHASE 1: SOURCE RESEARCH & INVENTORY

## Task 1: Create Centralized Source Registry Schema

**Files:**
- Create: `inteligencia_geoespacial/fontes_registry.py` (source registry + validation)
- Create: `inteligencia_geoespacial/__init__.py`
- Create: `docs/FONTES_BRASILEIRAS.md` (living documentation)
- Modify: `requirements.txt` (add DuckDB if needed)

**Interfaces:**
- Produces: `SourceRegistry(name, organ, dataset_url, api_endpoint, status, coverage, crs, license, fields_available, quality_score, last_validated, notes)` class
- Produces: `register_source()` function to add/update sources
- Produces: `validate_source()` function to test API connectivity + data quality

**Steps:**

- [ ] **Step 1:** Create directory structure
```bash
mkdir -p inteligencia_geoespacial\caches inteligencia_geoespacial\providers inteligencia_geoespacial\tests
```

- [ ] **Step 2:** Write `fontes_registry.py` with SourceRegistry class
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

class SourceStatus(Enum):
    ATIVO = "ativo"
    INATIVO = "inativo"
    EM_TESTE = "em_teste"
    DESCONTINUADO = "descontinuado"

@dataclass
class SourceRegistry:
    # Identificação
    id: str  # unique slug: "antaq_hidrovias_geojson"
    nome: str  # "ANTAQ - Hidrovias Navegáveis"
    orgao: str  # "ANTAQ"
    categoria: str  # "hidrografia", "rodoviaria", "territorial", "ambiental", "transporte"
    
    # URLs e Acesso
    dataset_url: str  # direct download link
    api_endpoint: Optional[str]  # REST API endpoint (if available)
    api_docs_url: Optional[str]  # documentation URL
    
    # Dados
    formato: str  # "GeoJSON", "Shapefile", "CSV", "REST/JSON", "WMS", "WFS", "API"
    tipo_geometria: Optional[str]  # "Point", "LineString", "Polygon", "MultiLineString"
    sistema_coordenadas: str  # "EPSG:4326"
    
    # Cobertura e Qualidade
    cobertura_geografica: str  # "Brasil", "Região Amazônia", "Zona Costeira"
    registros_totais: Optional[int]  # number of features
    data_atualizacao: datetime
    periodicidade: str  # "Mensal", "Trimestral", "Anual", "Ad-hoc"
    qualidade: Dict[str, float]  # {"completude": 0.95, "acuracia": 0.92, "atualidade": 0.88}
    
    # Licença e Metadados
    licenca: str  # "CC0", "CC-BY", "OGL", "Domínio Público"
    atribuicao_obrigatoria: str
    restricoes: str  # "Nenhuma", "Uso comercial", etc.
    
    # Campos Disponíveis
    campos_disponiveis: List[str]  # ["geometria", "nome", "codigo_ibge", "area_km2", "populacao"]
    
    # Status e Validação
    status: SourceStatus
    data_ultimo_teste: Optional[datetime]
    tempo_resposta_ms: Optional[int]
    proxima_validacao: datetime
    notas: str
    responsavel_validacao: Optional[str]

class SourcesRegistry:
    def __init__(self):
        self.sources: Dict[str, SourceRegistry] = {}
        self.validation_history: List[Dict] = []
    
    def register(self, source: SourceRegistry) -> None:
        """Register or update a data source"""
        self.sources[source.id] = source
    
    def get(self, source_id: str) -> Optional[SourceRegistry]:
        """Get a source by ID"""
        return self.sources.get(source_id)
    
    def list_by_category(self, categoria: str) -> List[SourceRegistry]:
        """List all sources in a category"""
        return [s for s in self.sources.values() if s.categoria == categoria]
    
    def list_ativas(self) -> List[SourceRegistry]:
        """List only active sources"""
        return [s for s in self.sources.values() if s.status == SourceStatus.ATIVO]
    
    def to_dataframe(self):
        """Export registry to pandas DataFrame for analysis"""
        import pandas as pd
        data = []
        for source in self.sources.values():
            data.append({
                'ID': source.id,
                'Órgão': source.orgao,
                'Categoria': source.categoria,
                'Formato': source.formato,
                'Status': source.status.value,
                'Registros': source.registros_totais or "N/A",
                'Atualização': source.data_atualizacao.strftime('%Y-%m-%d'),
                'Cobertura': source.cobertura_geografica,
                'Licença': source.licenca,
                'Nota': source.notas
            })
        return pd.DataFrame(data)

# Global registry instance
_registry_global = SourcesRegistry()

def get_registry() -> SourcesRegistry:
    return _registry_global
```

- [ ] **Step 3:** Create test file to validate registry
```python
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
```

- [ ] **Step 4:** Run test
```bash
cd new_rotas-main
python -m pytest inteligencia_geoespacial/tests/test_registry.py -v
```

- [ ] **Step 5:** Create `docs/FONTES_BRASILEIRAS.md` template
```markdown
# Catálogo Exaustivo de Fontes de Dados Oficiais Brasileiras

Atualizado em: 2026-09-07

## Status Geral

| Categoria | Total | Ativas | Em Teste | Descontinuadas |
|-----------|-------|--------|----------|----------------|
| Territorial | - | - | - | - |
| Hidrografia | - | - | - | - |
| Rodoviária | - | - | - | - |
| Transporte Aquaviário | - | - | - | - |
| Ambiental | - | - | - | - |
| Transporte Aéreo | - | - | - | - |

## Por Órgão

### ANTAQ (Agência Nacional de Transportes Aquaviários)
### ANA (Agência Nacional de Águas)
### IBGE (Instituto Brasileiro de Geografia e Estatística)
### DNIT (Departamento Nacional de Infraestrutura de Transportes)
### ANTT (Agência Nacional de Transportes Terrestres)
### DERs (Departamentos de Estradas de Rodagem Estaduais)
### PRF (Polícia Rodoviária Federal)
### INPE/CPTEC (Instituto Nacional de Pesquisas Espaciais)
### CEMADEN (Centro Nacional de Monitoramento de Desastres)
### INMET (Instituto Nacional de Meteorologia)
### Defesa Civil
```

- [ ] **Step 6:** Commit
```bash
git add inteligencia_geoespacial/ docs/FONTES_BRASILEIRAS.md
git commit -m "feat: create centralized source registry framework"
```

---

## Task 2: Research & Document All Brazilian Official Data Sources

**Files:**
- Modify: `docs/FONTES_BRASILEIRAS.md` (populate with full inventory)
- Create: `inteligencia_geoespacial/sources_inventory.py` (pre-populate registry with all sources)
- Create: `docs/PESQUISA_FONTES.md` (research log and validation notes)

**Interfaces:**
- Produces: `sources_inventory.py` with ~40+ pre-registered sources
- Produces: Comprehensive research documentation

**Steps:**

For each major source (ANTAQ, ANA, IBGE, DNIT, ANTT, DERs, PRF, INPE, CPTEC, CEMADEN, INMET, Defesa Civil):

- [ ] **Step 1:** Research ANTAQ (Agência Nacional de Transportes Aquaviários)
  - Access: https://www.gov.br/antaq/pt-br/acesso-a-informacao/dados-abertos
  - Document: all datasets, APIs, shapefile downloads, GeoJSON availability, WMS/WFS endpoints
  - Record: coverage (hidrovias, portos, terminais, travessias, infraestrutura aquaviária)
  - Validate: at least 5 API endpoints or download links

- [ ] **Step 2:** Research ANA (Agência Nacional de Águas e Saneamento Básico)
  - Access: https://www.snirh.gov.br/portal/
  - Document: HidroWeb API, datasets (rios, bacias, estações, telemétricas, cotas)
  - Collect: OGC Web Services (WMS, WFS), direct downloads
  - Already integrated: verify current implementation, identify gaps

- [ ] **Step 3:** Research IBGE (Instituto Brasileiro de Geografia e Estatística)
  - Access: https://geoftp.ibge.gov.br/, https://www.ibge.gov.br/
  - Document: BC250, BC100, BCIM, malhas municipais, localidades, distritos
  - Identify: API endpoints vs static downloads, shapefile formats
  - Check: 2025 edition availability, coordinates systems

- [ ] **Step 4:** Research DNIT (Departamento Nacional de Infraestrutura)
  - Access: https://www.gov.br/dnit/pt-br/
  - Document: rodovias, trechos, pontes, obras, condições pavimento, dados tráfego
  - Search: open data portals, APIs, shapefile repositories
  - Validate: coverage of BR-XXX highways, state-level roads

- [ ] **Step 5:** Research ANTT & DERs (Agência Nacional de Transportes Terrestres)
  - Access: https://www.antt.gov.br/, state DER websites
  - Document: concedidas, áreas de concessão, rodovias estaduais
  - List: contact info for each state DER with data availability

- [ ] **Step 6:** Research PRF (Polícia Rodoviária Federal)
  - Access: https://www.gov.br/prf/pt-br/
  - Document: publicly available data on accidents, roadblocks, critical points
  - Understand: data access restrictions, frequency, format

- [ ] **Step 7:** Research INPE/CPTEC/CEMADEN/INMET
  - Access: https://www.inpe.gov.br/, https://www.cemaden.gov.br/, https://www.inmet.gov.br/
  - Document: rainfall, flood alerts, extreme events APIs, real-time data
  - Identify: which datasets are actually queryable programmatically

- [ ] **Step 8:** Create comprehensive inventory in `sources_inventory.py`
```python
from inteligencia_geoespacial.fontes_registry import SourceRegistry, SourcesRegistry, SourceStatus
from datetime import datetime

def populate_sources() -> SourcesRegistry:
    """Pre-populate global registry with all validated Brazilian official sources"""
    registry = SourcesRegistry()
    
    # TERRITORIAL - IBGE
    registry.register(SourceRegistry(
        id="ibge_malhas_2025",
        nome="IBGE Malhas Municipais 2025",
        orgao="IBGE",
        categoria="territorial",
        dataset_url="https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/",
        api_endpoint=None,
        api_docs_url="https://www.ibge.gov.br/geociencias/",
        formato="Shapefile + GeoPackage",
        tipo_geometria="Polygon",
        sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil (5.570 municípios + 27 UFs)",
        registros_totais=5597,
        data_atualizacao=datetime(2025, 1, 1),
        periodicidade="Anual",
        qualidade={"completude": 1.0, "acuracia": 0.99, "atualidade": 1.0},
        licenca="CC0",
        atribuicao_obrigatoria="IBGE",
        restricoes="Nenhuma",
        campos_disponiveis=["CODIGO_IBGE", "NOME", "GEOMETRIA", "AREA_KM2", "CODIGO_UF"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=datetime(2026, 9, 7),
        tempo_resposta_ms=None,
        proxima_validacao=datetime(2027, 1, 1),
        notas="Oficialmente recomendado pelo IBGE",
        responsavel_validacao="Lucas"
    ))
    
    # HIDROGRAFIA - ANA/SNIRH
    registry.register(SourceRegistry(
        id="ana_snirh_rios",
        nome="ANA SNIRH - Rios do Brasil",
        orgao="ANA",
        categoria="hidrografia",
        dataset_url="https://www.snirh.gov.br/portal/",
        api_endpoint="https://snirh.snirh.gov.br/api/",
        api_docs_url="https://www.snirh.gov.br/portal/",
        formato="REST/JSON + GeoJSON",
        tipo_geometria="LineString",
        sistema_coordenadas="EPSG:4326",
        cobertura_geografica="Brasil",
        registros_totais=14135,
        data_atualizacao=datetime(2026, 8, 1),
        periodicidade="Mensal",
        qualidade={"completude": 0.95, "acuracia": 0.90, "atualidade": 0.95},
        licenca="CC-BY",
        atribuicao_obrigatoria="ANA - Sistema Nacional de Informações sobre Recursos Hídricos",
        restricoes="Nenhuma",
        campos_disponiveis=["NOME", "CODIGO", "EXTENSAO_KM", "GEOMETRIA", "BACIA", "ESTADO"],
        status=SourceStatus.ATIVO,
        data_ultimo_teste=datetime(2026, 9, 7),
        tempo_resposta_ms=150,
        proxima_validacao=datetime(2026, 10, 7),
        notas="JÁ INTEGRADO. Expansão: adicionar WMS/WFS",
        responsavel_validacao="Lucas"
    ))
    
    # ... (adicionar 38+ sources more)
    
    return registry
```

- [ ] **Step 9:** Commit research findings
```bash
git add docs/FONTES_BRASILEIRAS.md docs/PESQUISA_FONTES.md inteligencia_geoespacial/sources_inventory.py
git commit -m "docs: comprehensive inventory of 40+ Brazilian official data sources"
```

---

# PHASE 2: PROVIDER ARCHITECTURE & ABSTRACTION

## Task 3: Create Modular Provider Interface & Base Classes

**Files:**
- Create: `inteligencia_geoespacial/providers/__init__.py`
- Create: `inteligencia_geoespacial/providers/base.py` (abstract provider)
- Create: `inteligencia_geoespacial/providers/exceptions.py`
- Create: `inteligencia_geoespacial/caches/provider_cache.py`
- Create: `inteligencia_geoespacial/tests/test_providers.py`

**Interfaces:**
- Produces: `BaseProvider` abstract class with methods: `fetch()`, `validate()`, `transform()`, `to_geojson()`
- Produces: `ProviderFactory` to instantiate providers by type
- Produces: Cache layer for all provider responses

**Steps:**

- [ ] **Step 1:** Create `providers/base.py`
```python
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

class ProviderException(Exception):
    """Base exception for provider errors"""
    pass

class ProviderTimeoutException(ProviderException):
    """Provider request timed out"""
    pass

class ProviderValidationException(ProviderException):
    """Data validation failed"""
    pass

class BaseProvider(ABC):
    """Abstract base class for all data providers"""
    
    def __init__(self, name: str, source_id: str, cache_dir: Optional[Path] = None, cache_ttl_hours: int = 24):
        self.name = name
        self.source_id = source_id
        self.cache_dir = cache_dir or Path("inteligencia_geoespacial/caches")
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.last_fetch_time: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.fetch_count = 0
    
    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch raw data from provider.
        Returns list of dictionaries with provider's native schema.
        """
        pass
    
    @abstractmethod
    def validate(self, data: List[Dict[str, Any]]) -> bool:
        """
        Validate data structure and content.
        Raises ProviderValidationException if invalid.
        """
        pass
    
    @abstractmethod
    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform data to standard schema.
        Returns list with standardized fields: id, nome, geometria, coordenadas, metadados.
        """
        pass
    
    @abstractmethod
    def to_geojson(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert transformed data to GeoJSON FeatureCollection"""
        pass
    
    def _get_cache_path(self, query_hash: str) -> Path:
        """Generate cache file path for query"""
        return self.cache_dir / f"{self.source_id}_{query_hash}.json"
    
    def _hash_query(self, **kwargs) -> str:
        """Generate deterministic hash of query parameters"""
        query_str = json.dumps(kwargs, sort_keys=True, default=str)
        return hashlib.md5(query_str.encode()).hexdigest()
    
    def _load_cache(self, query_hash: str) -> Optional[List[Dict[str, Any]]]:
        """Load data from cache if available and fresh"""
        cache_file = self._get_cache_path(query_hash)
        if not cache_file.exists():
            return None
        
        # Check if cache expired
        file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if file_age > self.cache_ttl:
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.last_error = f"Cache load error: {str(e)}"
            return None
    
    def _save_cache(self, query_hash: str, data: List[Dict[str, Any]]) -> None:
        """Save data to cache"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._get_cache_path(query_hash)
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            self.last_error = f"Cache save error: {str(e)}"
    
    def fetch_with_cache(self, use_cache: bool = True, **kwargs) -> List[Dict[str, Any]]:
        """Fetch data with automatic caching"""
        query_hash = self._hash_query(**kwargs)
        
        # Try cache first
        if use_cache:
            cached = self._load_cache(query_hash)
            if cached is not None:
                return cached
        
        # Fetch from source
        data = self.fetch(**kwargs)
        
        # Validate
        self.validate(data)
        
        # Transform
        transformed = self.transform(data)
        
        # Cache
        if use_cache:
            self._save_cache(query_hash, transformed)
        
        self.last_fetch_time = datetime.now()
        self.fetch_count += 1
        
        return transformed
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return provider metadata"""
        return {
            "name": self.name,
            "source_id": self.source_id,
            "last_fetch": self.last_fetch_time.isoformat() if self.last_fetch_time else None,
            "fetch_count": self.fetch_count,
            "last_error": self.last_error,
            "cache_ttl_hours": self.cache_ttl.total_seconds() / 3600
        }
```

- [ ] **Step 2:** Create test file
```python
# inteligencia_geoespacial/tests/test_providers.py
import pytest
from inteligencia_geoespacial.providers.base import BaseProvider, ProviderValidationException

class MockProvider(BaseProvider):
    def fetch(self, **kwargs):
        return [
            {"id": 1, "nome": "Test 1", "valor": 100},
            {"id": 2, "nome": "Test 2", "valor": 200}
        ]
    
    def validate(self, data):
        if not data or not isinstance(data, list):
            raise ProviderValidationException("Invalid data")
        for item in data:
            if "id" not in item or "nome" not in item:
                raise ProviderValidationException("Missing required fields")
        return True
    
    def transform(self, data):
        return [
            {
                "id": item["id"],
                "nome": item["nome"],
                "valor": item.get("valor", 0),
                "source": self.source_id
            }
            for item in data
        ]
    
    def to_geojson(self, data):
        return {
            "type": "FeatureCollection",
            "features": []  # Mock implementation
        }

def test_provider_fetch_with_cache():
    provider = MockProvider("test", "test_source")
    data = provider.fetch_with_cache(use_cache=False)
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert provider.fetch_count == 1

def test_provider_validation_error():
    provider = MockProvider("test", "test_source")
    with pytest.raises(ProviderValidationException):
        provider.fetch_with_cache(use_cache=False)
```

- [ ] **Step 3:** Run tests
```bash
python -m pytest inteligencia_geoespacial/tests/test_providers.py -v
```

- [ ] **Step 4:** Commit
```bash
git add inteligencia_geoespacial/providers/
git commit -m "feat: create modular provider abstraction layer"
```

---

## Task 4: Implement 5 Priority Provider Adapters (IBGE, ANA, ANTAQ, DNIT, ANTT)

**Files:**
- Create: `inteligencia_geoespacial/providers/ibge_provider.py`
- Create: `inteligencia_geoespacial/providers/ana_provider.py`
- Create: `inteligencia_geoespacial/providers/antaq_provider.py`
- Create: `inteligencia_geoespacial/providers/dnit_provider.py`
- Create: `inteligencia_geoespacial/providers/antt_provider.py`

**Interfaces:**
- Produces: 5 concrete provider classes, each inheriting BaseProvider
- Each provider exposes `fetch_by_municipio()`, `fetch_by_geometry()`, `fetch_by_code()` as appropriate

**Steps:**

For each provider, implement (4 hours each):

- [ ] **Step 1-5:** Implement 5 providers following same pattern:
  1. Write provider class with `fetch()`, `validate()`, `transform()`, `to_geojson()`
  2. Write unit tests (3-5 test cases per provider)
  3. Write integration test (fetch real data from API/source)
  4. Document: expected response format, error codes, rate limits
  5. Commit

Example for IBGE:
```python
# inteligencia_geoespacial/providers/ibge_provider.py
import requests
import geopandas as gpd
from pathlib import Path
from inteligencia_geoespacial.providers.base import BaseProvider, ProviderException

class IBGEProvider(BaseProvider):
    """IBGE Territorial Data Provider"""
    
    def __init__(self, cache_dir=None):
        super().__init__("IBGE", "ibge_territorial", cache_dir, cache_ttl_hours=168)  # 1 week
        self.base_urls = {
            "malhas": "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/",
            "api": "https://servicodados.ibge.gov.br/api/v1/"
        }
    
    def fetch(self, resource_type: str = "municipios", **kwargs):
        """
        Fetch IBGE data.
        resource_type: "municipios", "estados", "localidades", "distritos"
        """
        if resource_type == "municipios":
            return self._fetch_municipios(**kwargs)
        elif resource_type == "estados":
            return self._fetch_estados(**kwargs)
        else:
            raise ProviderException(f"Unknown resource type: {resource_type}")
    
    def _fetch_municipios(self, **kwargs):
        """Fetch municipality data from IBGE API"""
        try:
            # IBGE API v1 endpoint
            url = f"{self.base_urls['api']}municipios"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.last_error = str(e)
            raise ProviderException(f"IBGE fetch error: {e}")
    
    def validate(self, data):
        if not isinstance(data, list):
            raise ProviderValidationException("Expected list of municipalities")
        for item in data:
            if "id" not in item or "nome" not in item:
                raise ProviderValidationException(f"Missing id or nome in: {item}")
        return True
    
    def transform(self, data):
        """Transform IBGE data to standard schema"""
        return [
            {
                "id": item.get("id"),
                "codigo_ibge": item.get("id"),
                "nome": item.get("nome"),
                "regiao": item.get("regiao", {}).get("nome"),
                "uf": item.get("microrregiao", {}).get("mesorregiao", {}).get("estado", {}).get("sigla"),
                "source": "ibge"
            }
            for item in data
        ]
    
    def to_geojson(self, data):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {k: v for k, v in item.items() if k != "geometria"},
                    "geometry": item.get("geometria")
                }
                for item in data if item.get("geometria")
            ]
        }
```

---

# PHASE 3: CROSS-SOURCE VALIDATION & ENRICHMENT

## Task 5: Build Cross-Source Validator (IBGE + ANA + DNIT)

**Files:**
- Create: `inteligencia_geoespacial/validators.py`
- Create: `inteligencia_geoespacial/tests/test_validators.py`

**Interfaces:**
- Produces: `CoordinateValidator` class
- Produces: `RouteValidator` class with methods like `validate_against_multiple_sources()`

**Steps:**

- [ ] Implement 3-4 validation functions:
  - `validate_coordinate_in_municipality()` — crosses IBGE boundaries
  - `validate_river_crossing()` — ANA hidrography + ANTAQ infrastructure
  - `validate_road_network()` — DNIT data against route
  - `cross_validate_sources()` — majority voting among 3+ sources

---

# PHASE 4: ENRICHMENT PIPELINE FOR ROUTES

## Task 6: Create Route Enrichment Engine

**Files:**
- Modify: `streamlit_app.py` (add enrichment call)
- Create: `inteligencia_geoespacial/enrichment_engine.py`
- Create: `inteligencia_geoespacial/tests/test_enrichment.py`

**Interfaces:**
- Consumes: `RotaPipeline` from existing code
- Produces: enriched `RotaPipeline` with new fields:
  - `rios_detectados: List[str]` - river names from ANA
  - `bacia_hidrografica: str` - basin name
  - `pontes_encontradas: List[Dict]` - bridge data from DNIT
  - `infraestrutura_aquaviaria: Dict` - ANTAQ data
  - `balsas_confirmadas: List[Dict]` - ferry crossing details
  - `alternativa_sem_balsa: Optional[float]` - km for route without ferry
  - `confianca_geral: float` - 0-100 confidence score
  - `fontes_concordam: List[str]` - which sources agreed
  - `motivo_decisao: str` - human-readable explanation

**Steps:**

- [ ] Implement enrichment logic that:
  1. Detects ferry crossings (existing code)
  2. Calls ANA to identify river names
  3. Calls DNIT to find bridges/alternatives
  4. Calls ANTAQ to verify ferry infrastructure
  5. Generates confidence score based on source agreement
  6. Produces human-readable audit trail

---

# PHASE 5: ENHANCED XAI PANEL FOR AUDIT TAB

## Task 7: Extend XAI Explanation with Source Details

**Files:**
- Modify: `streamlit_app.py` (around lines 54000-54200 where XAI audit is rendered)
- Create: `inteligencia_geoespacial/xai_formatter.py`
- Create: `inteligencia_geoespacial/tests/test_xai.py`

**Interfaces:**
- Consumes: enriched `RotaPipeline` with all source data
- Produces: HTML/Markdown formatted explanation for Streamlit

**Steps:**

- [ ] Create XAI formatter that generates rich explanations:
  ```
  🟢 ALTA CONFIANÇA - Rota Validada (95/100)
  
  📍 ORIGEM
    Município: São Paulo/SP
    Validado por: IBGE (2025), SNIRH (rio próximo: 28km), coordenadas EPSG:4326
    Confiança: 100/100
  
  📍 DESTINO
    Município: Manaus/AM
    Validado por: IBGE (2025), localidade confirmada
    Confiança: 98/100
  
  🛣️ REDE RODOVIÁRIA
    BR-116: 1.240 km (DNIT - pavimento BOM)
    BR-174: 980 km (DNIT - pavimento REGULAR)
    Confiança DNIT: 92/100
  
  🌊 HIDROGRAFIA & BALSAS
    Balsa detectada: Rio Amazonas
    Validação ANA: Rio navegável (SNIRH - estação telemétrica a 12km)
    Travessia confirmada por ANTAQ: Terminal Manaus - Porto operacional
    Alternativa sem balsa: +480 km (não viável)
    Confiança ANA/ANTAQ: 96/100
  
  🌉 PONTES & ALTERNATIVAS
    1 ponte identificada (DNIT - nova, 2024)
    Possibilidade de contorno sem balsa: NÃO
    Confiança DNIT: 88/100
  
  ⚔️ COMPARAÇÃO DE FONTES
    IBGE: Origem = São Paulo ✓ | Destino = Manaus ✓
    SNIRH: Rio Amazonas presente ✓ | Navegável ✓
    DNIT: Rodovia BR-116 + BR-174 ✓ | Pavimento verificado
    ANTAQ: Terminal Manaus operacional ✓
  
  📊 DECISÃO FINAL
    Motor: OSRM (1º) vs FOSSGIS (2º, +2%) vs Valhalla (3º, +1.8%)
    Critério: Distância mínima validada contra 4 fontes
    Recomendação: APROVADA PARA OPERAÇÃO
  ```

---

# PHASE 6: TESTING & REGRESSION VERIFICATION

## Task 8: Verify Zero Regression on Existing Gates

**Files:**
- Modify: `_testes_motor_rotas.py` (add phase markers)

**Steps:**

- [ ] Run all existing tests to ensure no regression:
```bash
python -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py
python -X utf8 _testes_motor_rotas.py validar    # Must remain 192 OK
python -X utf8 _testes_motor_rotas.py decidir    # Must remain 38/38
python -X utf8 _testes_motor_rotas.py relatorio  # Verify output
```

- [ ] If any regression: debug and fix before proceeding

---

## Task 9: Measure Improvement (Derrotas Reduction)

**Files:**
- Create: `inteligencia_geoespacial/evaluation.py`
- Create: `docs/ANTES_DEPOIS_ENRIQUECIMENTO.md`

**Steps:**

- [ ] Implement evaluation function that:
  1. Runs existing baseline (436)
  2. Runs new enriched version
  3. Compares defeats count
  4. Measures confidence improvements
  5. Generates detailed report

- [ ] Target improvements:
  - Defeats: 88 → <70 (reduce by 20%)
  - Ferry detection: 21 → 35+ (more accurate)
  - Route explanation quality: 80% → 95%+ auditable

---

# PHASE 7: DOCUMENTATION & DEPLOYMENT

## Task 10: Complete Documentation & Knowledge Transfer

**Files:**
- Modify: `HANDBOOK.md`
- Create: `docs/ARQUITETURA_INTELIGENCIA.md`
- Create: `docs/GUIA_INTEGRACAO_NOVOS_DADOS.md`

**Steps:**

- [ ] Document:
  1. Complete architecture diagram
  2. How to add new data source (step-by-step)
  3. Cache strategy and TTL settings
  4. Rate limits and API quotas
  5. Troubleshooting guide
  6. Performance benchmarks

---

## Task 11: Final Integration & Production Deployment

**Files:**
- Modify: `streamlit_app.py` (integrate all layers)
- Modify: `requirements.txt` (if new deps added)

**Steps:**

- [ ] Integration checklist:
  - [ ] All providers registered in global registry
  - [ ] Caching layer operational
  - [ ] XAI panel shows enriched data
  - [ ] All 192 tests passing
  - [ ] All 38 decision tests passing
  - [ ] Zero regressions
  - [ ] Performance acceptable (<5s per query)

- [ ] Final commit:
```bash
git add -A
git commit -m "feat: complete geographical intelligence enrichment system

- Integrated 40+ official Brazilian data sources
- Added modular provider architecture
- Cross-source validation and enrichment
- Enhanced XAI panel with source-level audit trail
- Improved from 88 to <70 defeats (~20% reduction)
- 192 tests passing, zero regressions, 38/38 decision tests"
```

---

# EXECUTION FLOW

```
START
  └─> Phase 1: Source Research (Tasks 1-2)
       └─> Phase 2: Provider Architecture (Tasks 3-4)
            └─> Phase 3: Cross-Source Validation (Task 5)
                 └─> Phase 4: Route Enrichment (Task 6)
                      └─> Phase 5: XAI Enhancement (Task 7)
                           └─> Phase 6: Testing & Regression (Tasks 8-9)
                                └─> Phase 7: Documentation (Tasks 10-11)
                                     └─> PRODUCTION READY
```

Each phase should complete before starting next (except where noted).

---

# APPENDIX: CURRENT STATE & DEPENDENCIES

## Already Implemented
- ✅ SNIRH/ANA HidroWeb (40k+ estações, 14k+ rios)
- ✅ IBGE Malhas Municipais (5.570 municípios)
- ✅ OSRM/FOSSGIS routing (basic + ferry support)
- ✅ Aquaviário fluvial (1.46M nós, 1.72M arestas)
- ✅ Basic XAI audit trail

## To Be Implemented (This Plan)
- 🔄 ANTAQ APIs (hidrovias, portos, terminais)
- 🔄 DNIT road condition data
- 🔄 ANTT/DER concession data
- 🔄 PRF safety/traffic data
- 🔄 CEMADEN flood alerts
- 🔄 INPE/CPTEC environmental data
- 🔄 Enhanced cross-source validation
- 🔄 Enriched XAI panel

## Tests to Maintain
- 192 unit/integration tests (must remain 100% passing)
- 38 critical decision tests (must remain 100% passing)
- Performance: <5s per route calculation

