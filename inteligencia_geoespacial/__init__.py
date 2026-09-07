"""
Inteligência Geoespacial - Centralized geographical intelligence system for routing
"""

from .fontes_registry import SourceRegistry, SourcesRegistry, SourceStatus, get_registry
from . import bases_locais
from . import validators
from . import enrichment_engine
from . import xai_formatter

__version__ = "0.1.0"
__all__ = [
    "SourceRegistry",
    "SourcesRegistry",
    "SourceStatus",
    "get_registry",
    "bases_locais",
    "validators",
    "enrichment_engine",
    "xai_formatter",
]
