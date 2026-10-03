# -*- coding: utf-8 -*-
"""OpenRotas Desktop — camada de MOTORES de rota locais (Etapa 3).

Objetivo: dar ao desktop um motor de rotas rápido e, quando configurado, OFFLINE — sem
reescrever o cliente de rotas do app (que já fala OSRM via OSRM_URL). A estratégia é
GERENCIAR um OSRM local (detectar/subir/validar) e injetar a URL dele, reaproveitando o
caminho de rotas já testado em produção. Ver desktop/README.md (seção "Motor de rotas local").
"""
__all__ = ["osrm_manager", "benchmark"]
