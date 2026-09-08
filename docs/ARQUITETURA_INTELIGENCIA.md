# Arquitetura da Inteligência Geoespacial

**Versão:** 1.0
**Atualizado em:** 2026-09-07
**Escopo:** camada `inteligencia_geoespacial/` + providers + integração com `streamlit_app.py`

---

## 1. Visão geral

O Motor Nacional de Inteligência Logística possui uma camada de inteligência geoespacial
**100% local (sem GDAL/geopandas, sem rede)** construída sobre camadas derivadas IBGE e um
registro de fontes oficiais. O fluxo de dados é sempre **aditivo e auditável**: nenhuma
camada altera o vencedor da rota sem que haja evidência rastreável (fonte + distância).

```
                          FONTES OFICIAIS (IBGE BC250/BC100, ANTAQ, ANA, DNIT, ANTT, ...)
                                      │  construir_bases_locais_ibge.py
                                      ▼
                          data/brasil/ibge/derivadas/*.parquet (12 camadas, manifest.json)
                                      │
                      ┌───────────────┴────────────────┐
                      ▼                                ▼
          inteligencia_geoespacial/bases_locais.py    inteligencia_geoespacial/sources_inventory.py
          (leitura espacial por bbox pyarrow)         (registro de 51 fontes)
                      │
        ┌─────────────┼──────────────┬─────────────────┐
        ▼             ▼              ▼                 ▼
 coordinate_validator  enrichment  xai_formatter   providers/
 (validators.py)    (enrichment_engine)   (IBGEDerivadasProvider + factory)
        └─────────────┴──────────────┴─────────────────┴──────────────┘
                                      ▼
                          streamlit_app.py (SEÇÃO 22 Geoespacial, SEÇÃO 18 enriquecimento de rota)
```

## 2. Módulos

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `bases_locais.py` | Leitura por bbox (pyarrow) das 12 camadas; `municipio_do_ponto` (point-in-polygon); `mais_proximos` (distância ponto-geom só com WKB); `_deco_wkb` (ponto/linha/polígono) | parquet em `data/brasil/ibge/derivadas/` |
| `validators.py` | `CoordinateValidator`: `municipio`, `rio_mais_proximo` (drenagem NOMEADA), `mais_proximas` (com filtros), `perfil` (pacote de feições), `confianca` 0-100 com `fontes_concordam`/`nivel`/`motivo`, `validar_trecho` | `bases_locais` |
| `enrichment_engine.py` | `enriquecer_ponto`/`enriquecer_rota`: campos Task 6 (`rios_detectados`, `bacia_hidrografica`, `pontes_encontradas`, `infraestrutura_aquaviaria`, `balsas_confirmadas`, `alternativa_sem_balsa`, `confianca_geral`, `confianca_nivel`, `fontes_concordam`, `motivo_decisao`) | `validators` |
| `xai_formatter.py` | `formatar_confianca`, `formatar_ponto`, `formatar_enriquecimento` (Markdown), `formatar_enriquecimento_html` | `enrichment_engine`/`validators` |
| `evaluation.py` | Mede ANTES×DEPOIS das derrotas (baseline 1452): derrotas explicadas por balsa/fluvial/infra, detecção de balsa, qualidade da explicação. CLI `py -X utf8 -m inteligencia_geoespacial.evaluation --max 0 --write on` | `enrichment_engine` + `_baseline_1452.json` |
| `providers/` | `base.py` (contrato `fetch/validate/transform/to_geojson`), `ibge_derivadas_provider.py` (fetch por lat/lon/camada/raio/filtros + `wkb_para_geojson` + camada `municipios` point-in-polygon), `factory.py` (`ProviderFactory.criar("ibge_der_*")`, `registrar_tipo`), `caches/` (provider_cache) | `bases_locais` |
| `sources_inventory.py`/`fontes_registry.py` | Registro das 51 fontes oficiais (12 delas `ibge_der_*` ativas localmente) | — |

## 3. Camadas derivadas IBGE (12)

| Camada | Parquet | Registros | Uso típico |
|---|---|---|---|
| municipios | `municipios.parquet` | 5.571 | point-in-polygon do ponto |
| drenagem | `drenagem.parquet` | 2.181.288 | `rio_mais_proximo` (nome 71%) |
| rodovias | `rodovias.parquet` | 287.136 | rede viária / filtro `revestimen` |
| ferrovias | `ferrovias.parquet` | 889 | filtro `bitola` |
| massas_dagua | `massas_dagua.parquet` | 64.850 | corpos d'água |
| travessias | `travessias.parquet` | 4.046 | `balsas_confirmadas` (filtro `tipotraves=Balsa`) |
| pontes | `pontes.parquet` | 14.812 | `pontes_encontradas` |
| atracadouros_terminal | `atracadouros_terminal.parquet` | 172 | infra aquaviária |
| complexos_portuarios | `complexos_portuarios.parquet` | 171 | infra aquaviária |
| eclusas | `eclusas.parquet` | 22 | infra aquaviária |
| sinalizacao | `sinalizacao.parquet` | 388 | `tiposinal` |
| hidrovias | `hidrovias.parquet` | 179 | `regime` / navegação |

## 4. Estratégia de cache e TTL

- **Camadas parquet:** lidas com filtro de **bbox** (`_busca_com_filtro`) — nunca carregadas
  inteiras (exceto `municipios`, 5.571 linhas, leve). Sem TTL: são estáticas por versão IBGE.
- **Provider cache (`providers/caches/provider_cache.py`):** arquivos JSON
  `inteligencia_geoespacial/caches/<source_id>_<query_hash>.json`, TTL por provider
  (padrão 24 h; IBGE territorial 168 h).
- **Evaluation cache:** `cache_geoespacial/evaluation_enriquecimento.json` (chave
  `origem|uf|lat,lon->lat,lon`) — reprocessamento instantâneo.

## 5. Limites e cotas (APIs de rede)

A camada de inteligência **não faz chamadas de rede**; as consultas de avaliação rodam
100% off-line. As APIs com cota relevante ficam no motor de rotas (não nesta camada):

| Serviço | Cota/limite | Tratamento |
|---|---|---|
| OSRM público | sem chave; instável | fallback automático → FOSSGIS (verify→False só em SSLError), teste fechado |
| FOSSGIS | 300 "cruces"/sessão | consenso binário económico (já medido) + budget de auto-engajamento |

## 6. Benchmarks de performance

| Operação | Custo medido |
|---|---|
| `municipio_do_ponto` (SP/Manaus) | ~0,1 s |
| `mais_proximos(travessias, balsa)` Manaus | 0,1–0,3 s |
| `mais_proximos(drenagem)` | 0,5–1,0 s |
| `enriquecer_ponto` (perfil completo, raio 30) | ~1 s |
| `enriquecer_rota` (2 pontos, raio 40) | ~1,5–2,5 s (1º run) · ~0,01 s com cache |
| Bota do Streamlit (bare mode) | < 30 s (primeira), incremental depois |

Meta global do produto: **< 5 s por rota calculada** (o enriquecimento é acionado em
demanda por botão, nunca no caminho crítico do roteamento).

## 7. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| `não há dados`: consulta vazia numa camada | Ponto longe da base OU raio pequeno | Aumentar raio/limite; conferir que o ponto está no Brasil |
| Import defensivo desativado na SEÇÃO 22 | `bases_locais`/parquet ausentes | Presença dos 12 parquet + `_BASES_LOCAIS_IBGE=True` no topo do app |
| `test_cache_read` falha | Pré-existente (tuple↔list no JSON do provider cache) | Não relacionado a esta camada; mantido como falha conhecida |
| Gravação de `evaluation_enriquecimento.json` | Cache parcial | Reexecutar `--max 0` (cache reaproveita o que já existe) |
| Wortes na UI do mapa | `wkb_para_geojson` recebeu WKB None/desconhecido | `tipos de geometria` limitados a Point/LineString/Polygon (WKB codificado no builder) |

## Deploy no Streamlit Cloud — disponibilidade de dados

O repositório versiona os dados que cabem no GitHub: grafos fluviais (`*.pkl.gz`),
CSVs SNIRH leves (`snirh_rios.csv`, `snirh_bacias.csv`), `sedes_oficiais_ibge.csv` e
**10 das 12 camadas derivadas** (via exceções no `.gitignore` para
`data/brasil/ibge/derivadas/`).

Os arquivos que excedem o limite de 100MB/arquivo do GitHub ficam **fora do repo** e são
publicados como assets de uma GitHub Release deste repositório:
`drenagem.parquet`, `rodovias.parquet` e `snirh_estacaos.csv`.

O módulo `inteligencia_geoespacial/dados_bootstrap.py` baixa esses arquivos **sob demanda**
(pureza: sem Streamlit, fail-open) — os botões que o acionam ficam nas seções:
- **Geoespacial IBGE**: "Baixar camadas pesadas (drenagem + rodovias)" quando ausentes.
- **Hidrografia → Estações**: "Baixar catálogo completo de estações" quando em fallback.

O diagnóstico de camadas (`bases_locais.camadas_disponiveis()`) filtra por arquivo
existente, então as camadas baixadas aparecem automaticamente após o `st.rerun()`.

---

*Este documento acompanha o plano `docs/superpowers/plans/2026-09-07-enriquecer-motor-inteligencia-geoespacial.md` e o `docs/FONTES_BRASILEIRAS.md`.*