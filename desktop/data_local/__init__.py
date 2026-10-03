# -*- coding: utf-8 -*-
"""OpenRotas Desktop — camada de DADOS LOCAIS (Etapa 4).

Registro organizado dos dados geográficos locais (§8/§33), com carregamento preguiçoso
(§16), verificação de integridade/versão (§17/§18/§19) e prontidão offline (§12). NÃO
reimplementa a lógica geográfica do app (§34): é uma camada de GESTÃO/DIAGNÓSTICO de dados,
consumida pelo diagnóstico do desktop e pelo instalador."""
__all__ = ["local_data"]
