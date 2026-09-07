"""
Provider Factory - instancia providers padronizados pelos identificadores de fonte.

Resolve o `source_id` (ex.: ibge_der_pontes) para a classe de provider concreta.
Toda fonte registrada no catálogo com prefixo `ibge_der_*` é atendida pelo
`IBGEDerivadasProvider` (camadas locais). Tipos adicionais podem ser registrados
com `ProviderFactory.registrar_tipo(...)`.
"""

from __future__ import annotations

from typing import Dict, Optional

from .base import BaseProvider
from .exceptions import ProviderException
from .ibge_derivadas_provider import IBGEDerivadasProvider


class ProviderFactory:
    """Cria providers por source_id, com resolução automática para ibge_der_*."""

    _tipos: Dict[str, type] = {
        "ibge_derivadas": IBGEDerivadasProvider,
    }
    _cls_ibge_der = IBGEDerivadasProvider

    @classmethod
    def registrar_tipo(cls, nome: str, cls_provider: type) -> None:
        """Registra uma classe de provider sob um nome de tipo."""
        cls._tipos[nome] = cls_provider

    @classmethod
    def _resolve(cls, source_id: str) -> type:
        if source_id.startswith("ibge_der_"):
            return cls._cls_ibge_der
        if source_id.startswith("ibge_"):
            return cls._cls_ibge_der
        return cls._tipos.get(source_id)

    @classmethod
    def criar(cls, source_id: str, **kwargs) -> BaseProvider:
        """Instancia o provider adequado ao source_id (parâmetros extras via kwargs)."""
        cls_provider = cls._resolve(source_id)
        if cls_provider is None:
            raise ProviderException(
                "Nenhum provider registrado para %r. Registre com ProviderFactory.registrar_tipo." % source_id)
        return cls_provider(source_id=source_id, **kwargs)

    @classmethod
    def lista(cls) -> list:
        """Descreve os tipos/classes conhecidos pela factory."""
        return sorted({"ibge_der_*": cls._cls_ibge_der.__name__} | {k: v.__name__ for k, v in cls._tipos.items()},
                      key=lambda x: x)

    @classmethod
    def tipos(cls) -> Dict[str, type]:
        return dict(cls._tipos)