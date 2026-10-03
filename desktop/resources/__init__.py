# -*- coding: utf-8 -*-
"""OpenRotas Desktop — Gerenciador de Recursos (§3/§4/§17/§18/§19/§24).

Orquestra os recursos do software (bases embarcadas + grafo OSRM provisionável): status,
integridade, provisionamento e reparo. NÃO duplica as camadas existentes — compõe
desktop/data_local/local_data.py (bases) e desktop/engines/osrm_manager.py (grafo)."""
__all__ = ["resource_manager"]
