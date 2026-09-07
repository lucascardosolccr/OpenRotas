"""
Inteligência Geoespacial - Centralized geographical intelligence system for routing
"""

from .fontes_registry import SourceRegistry, SourcesRegistry, SourceStatus, get_registry

__version__ = "0.1.0"
__all__ = ["SourceRegistry", "SourcesRegistry", "SourceStatus", "get_registry"]
