# Guia de Integração de Novos Dados

**Versão:** 1.0
**Atualizado em:** 2026-09-07
**Escopo:** como adicionar uma nova fonte/dataset ao Motor Nacional de Inteligência Logística
e expô-la na camada `inteligencia_geoespacial/` + UI, seguindo as convenções do projeto.

---

## 1. Fluxo de integração (visão geral)

```
1. Registro da fonte         → sources_inventory.py / (docs/FONTES_BRASILEIRAS.md)
2. Builder da camada local   → construir_bases_locais_ibge.py → data/brasil/ibge/derivadas/<camada>.parquet
3. Consumo espacial          → bases_locais.camadas_disponiveis() + mais_proximos(filtros)
4. Provider (opcional)       → providers/ibge_derivadas_provider.py (prefixo ibge_der_*) ou provider próprio
5. UI                        → streamlit_app.py (SEÇÃO 22 Geoespacial / card de rota na SEÇÃO 18)
6. Testes e gates            → test_bases_locais/test_validators/test_enrichment/test_provider_ibge_derivadas
                                + py _testes_motor_rotas.py validar (192 OK) / decidir (38/38)
```

**Regra de ouro:** toda nova camada deve ser **aditiva** — com a camada ausente ou o
parquet corrompido o sistema continua funcionando (import defensivo + fail-open).

---

## 2. Passo a passo com exemplo real (camada `ferrovias`)

### 2.1 Registrar a fonte no inventário

Em `inteligencia_geoespacial/sources_inventory.py`, faça `registry.register(SourceRegistry(...))`
com o `id` no slug padrão (`ibge_der_<camada>` para camadas derivadas locais):

```python
registry.register(SourceRegistry(
    id="ibge_der_ferrovias",
    nome="IBGE BC250 - Ferrovias (derivada local)",
    orgao="IBGE",
    categoria="transporte",
    dataset_url="https://geoftp.ibge.gov.br/cartas_e_mapas/bases_cartograficas_continuas/bc250/",
    formato="Shapefile",
    tipo_geometria="LineString",
    sistema_coordenadas="EPSG:4326",
    cobertura_geografica="Brasil",
    registros_totais=889,
    data_atualizacao=datetime(2025, 1, 1),
    periodicidade="Versão BC250 (v2025)",
    qualidade={"completude": 0.98, "acuracia": 0.95, "atualidade": 0.90},
    licenca="Domínio Público",
    atribuicao_obrigatoria="IBGE",
    restricoes="Nenhuma",
    campos_disponiveis=["nome", "bitola", "codtrechof", "tipo_geom", "geometry_wkb"],
    status=SourceStatus.ATIVO,
    ...
))
```

Atualize também `docs/FONTES_BRASILEIRAS.md` (contagem + tabela + portal).

### 2.2 Gerar a camada Parquet local

Adicione a entrada em `construir_bases_locais_ibge.py` (lista de camadas do `build()`):
cada camada guarda `geometry_wkb`, colunas de aceleração `xmin/ymin/xmax/ymax`, `lon/lat`
(centróide) e os atributos relevantes. O builder decima polígonos/linhas e codifica a
geometria em WKB (sem GDAL).

```bash
py -X utf8 construir_bases_locais_ibge.py
py -X utf8 -c "from inteligencia_geoespacial import bases_locais as b; print(b.camadas_disponiveis())"
```

Resultado: `data/brasil/ibge/derivadas/ferrovias.parquet` + `manifest.json`.

### 2.3 Consumir pela base local

Se a camada já seguir o schema-padrão (`geometry_wkb`, `lon`, `lat`, `xmin/ymin/xmax/ymax`,
`nome`), ela **funciona automaticamente** em `mais_proximos("ferrovias", lon, lat, raio_km,
filtros={"bitola": "Métrica"})`. Atributos adicionais aparecem com `fonte_*` e `tipo_geom`.

### 2.4 Expor via provider (padrão de fábrica)

Fontes com prefixo `ibge_der_` são resolvidas automaticamente pelo `ProviderFactory`:

```python
from inteligencia_geoespacial.providers.factory import ProviderFactory
p = ProviderFactory.criar("ibge_der_ferrovias")
dados = p.fetch_with_cache(lat=-3.1, lon=-60.0, camada="ferrovias", raio_km=40, limite=10)
geojson = p.to_geojson(dados)
```

Para um tipo de fonte NOVO (ex.: API web), crie `providers/<nome>_provider.py` com o
contrato de `BaseProvider` (`fetch`, `validate`, `transform`, `to_geojson`) e registre:

```python
from inteligencia_geoespacial.providers.factory import ProviderFactory
from providers.meu_provider import MeuProvider
ProviderFactory.registrar_tipo("meu_tipo", MeuProvider)
```

### 2.5 Expor na UI

- Consulta pontual: adicione a camada à lista da SEÇÃO 22 (marcador `# SEÇÃO 22 ... [IBGE-GEO]`),
  no selectbox de camadas + raio + filtros (ex.: `filtros` coluna→selectbox).
- Enriquecimento de rota: adicione a camada a `_CAMADAS_INFRA` em `validators.py` (e, se
  tiver atributo de digest relevante, a `_ATRIBUTOS_DIGEST`), e o campo correspondente em
  `enrichment_engine.enriquecer_rota` (ex.: `ferrovias_encontradas`).

### 2.6 Testes obrigatórios

Adicione casos em:

- `inteligencia_geoespacial/tests/test_bases_locais.py` — carrega a camada, consulta perto
  de um ponto conhecido, filtro.
- `inteligencia_geoespacial/tests/test_provider_ibge_derivadas.py` — `fetch` + geojson da camada.
- Se entrou no enriquecimento: `test_validators.py` / `test_enrichment.py`.

Depois rode as gates de regressão (não podem mudar):

```bash
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py
py -X utf8 _testes_motor_rotas.py validar   # permanece 192 OK
py -X utf8 _testes_motor_rotas.py decidir   # permanece todos OK
py -X utf8 _testes_motor_rotas.py relatorio # regera o artefato ANTES×DEPOIS
py -X utf8 -m pytest inteligencia_geoespacial/tests -q
```

---

## 3. Estratégia de cache e TTL

| Nível | Onde | Regras |
|---|---|---|
| Camadas Parquet | `data/brasil/ibge/derivadas/` | Estáticas por versão IBGE; leitura por bbox, nunca inteiras (exceto `municipios`) |
| Provider cache | `inteligencia_geoespacial/caches/<source_id>_<hash>.json` | TTL por provider (`cache_ttl_hours`): 24 h padrão; territorial IBGE 168 h |
| Evaluation cache | `cache_geoespacial/evaluation_enriquecimento.json` | Chave `origem|uf|lat,lon->lat,lon`; reprocessamento instantâneo |

Ajuste o TTL em `BaseProvider.__init__` (via kwargs do provider) ou no construtor da subclasse.

## 4. Cotas e rate limits (APIs de rede)

| Serviço | Cota | Recomendação |
|---|---|---|
| OSRM público | instável, sem chave | fallback → FOSSGIS (`_get_tls_fallback` só em SSLError) |
| FOSSGIS | 300 cruzes/sessão | consenso binário económico; budget de auto-engajamento por processo |
| Demais APIs (planejadas: PRF, CEMADEN, CPTEC) | ver painel "Monitor de APIs" | nunca bloquear o caminho crítico da rota |

## 5. Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| Consulta vazia em camada nova | bbox/raio pequeno ou ponto fora do Brasil | aumentar raio; validar `_ponto_em_wkb` |
| `ProviderException: Nenhum provider registrado` | source_id sem prefixo `ibge_der_` | usar `registrar_tipo` |
| Filtro não filtra | coluna do filtro não existe na camada parquet | conferir `campos_disponiveis`/`manifest.json` |
| Teste de provider falha só no 2º run | cache persistente entre execuções | usar `tmp_path` como `cache_dir` nos testes |
| UI sem a camada nova | import defensivo caiu | verificar parquet + flag `_BASES_LOCAIS_IBGE` |

## Camadas pesadas no deploy (Streamlit Cloud)

Camadas >100MB (`drenagem`, `rodovias`) e `snirh_estacaos.csv` não entram no git
(limite do GitHub). Para adicionar/atualizar uma camada pesada ao deploy:

1. Gere/atualize o arquivo no diretório esperado (ex.: `data/brasil/ibge/derivadas/`).
2. Publique-o como asset da Release `dados-geoespaciais-v1` deste repositório
   (`gh release upload dados-geoespaciais-v1 <arquivo>`).
3. Atualize o tamanho esperado (bytes) em `inteligencia_geoespacial/dados_bootstrap.py`
   (dict `EXTRAS`) e o `ausentes()` passa a detectar o novo arquivo.

O app baixa sob demanda via `dados_bootstrap.baixar_ausentes(...)` nos botões das seções
Geoespacial IBGE e Hidrografia → Estações.

---

*Guia complementar a `docs/ARQUITETURA_INTELIGENCIA.md` e `docs/FONTES_BRASILEIRAS.md`.*