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
    data_atualizacao: Optional[datetime]  # None = data de atualização da fonte não é conhecida (nunca fabricar uma)
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

    # Uso real na aplicação (Rodada 2 da missão "extração máxima de APIs/datasets"):
    # honestidade sobre COMO a fonte é acessada e ONDE ela é de fato consumida —
    # nunca "✅ API REST funcional" para algo que o código nunca chama.
    modo_acesso: str = "arquivo_local"  # "api_rest_ao_vivo" | "arquivo_local" | "download_sob_demanda" | "informativo_apenas"
    uso_no_motor: str = ""  # onde/como esta fonte é de fato consumida hoje (arquivo:função) — "" se não usada

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
                'Fonte': source.nome,
                'Órgão': source.orgao,
                'Categoria': source.categoria,
                'Formato': source.formato,
                'Modo de acesso': source.modo_acesso,
                'Status': source.status.value,
                'Registros': source.registros_totais or "N/A",
                'Atualização': source.data_atualizacao.strftime('%Y-%m-%d') if source.data_atualizacao else "Não informada",
                'Cobertura': source.cobertura_geografica,
                'Endpoint/Caminho': source.api_endpoint or source.dataset_url or "—",
                'Uso no motor hoje': source.uso_no_motor or "Não integrado ao pipeline automático",
                'Licença': source.licenca,
                'Nota': source.notas
            })
        return pd.DataFrame(data)

# Global registry instance
_registry_global = SourcesRegistry()

def get_registry() -> SourcesRegistry:
    return _registry_global
