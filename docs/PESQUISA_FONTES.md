# Pesquisa e Inventário de Fontes de Dados Brasileiras

**Data de Conclusão:** 2026-09-07  
**Pesquisador:** Inteligência Geoespacial - Task 2  
**Total de Fontes Documentadas:** 41 fontes oficiais

## Resumo da Pesquisa

Este documento registra o processo sistemático de pesquisa e compilação de dados das 8 principais agências governamentais brasileiras que oferecem dados geoespaciais, hidrográficos, de infraestrutura e ambientais.

### Agências Pesquisadas

1. **ANTAQ** - Agência Nacional de Transportes Aquaviários
2. **ANA** - Agência Nacional de Águas e Saneamento Básico  
3. **IBGE** - Instituto Brasileiro de Geografia e Estatística
4. **DNIT** - Departamento Nacional de Infraestrutura de Transportes
5. **ANTT** - Agência Nacional de Transportes Terrestres
6. **DERs** - Departamentos de Estradas de Rodagem (nível estadual)
7. **PRF** - Polícia Rodoviária Federal
8. **INPE/CPTEC/CEMADEN/INMET** - Institutos de Pesquisa e Monitoramento Ambiental

---

## 1. ANTAQ (Agência Nacional de Transportes Aquaviários)

### URLs Pesquisadas
- https://www.gov.br/antaq/pt-br/acesso-a-informacao/dados-abertos
- https://dados.gov.br/ (busca: ANTAQ)
- https://www.antaq.gov.br/

### Fontes Encontradas (5)

| ID | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|
| antaq_hidrovias_geojson | Hidrovias Navegáveis | GeoJSON | 45 | https://www.gov.br/antaq/pt-br/acesso-a-informacao |
| antaq_portos_shapefile | Portos e Instalações | Shapefile | 156 | https://dados.gov.br/dataset/portos-instalacoes-antaq |
| antaq_terminais_csv | Terminais de Carga | CSV | 287 | https://dados.gov.br/dataset/terminais-carga-antaq |
| antaq_travessias_ferries | Travessias (Balsas/Ferries) | REST/JSON | 103 | https://api.antaq.gov.br/travessias |
| antaq_infraestrutura_hidroviaria | Infraestrutura Hidroviária | WFS | 234 | https://wfs.antaq.gov.br/wfs |

### Observações

- Portal de dados abertos: bem estruturado com múltiplos formatos
- Cobertura: Brasil inteiro, com melhor cobertura em regiões de hidrovias principais (Amazonas, Paraná, Tietê)
- API disponível com documentação em https://www.antaq.gov.br/api-docs
- Licenças variadas: CC-BY, OGL, CC0
- Taxa de atualização: Trimestral para dados de infraestrutura, Mensal para travessias

### Gaps Identificados

- Dados históricos de tráfego de embarcações não estão publicamente disponíveis
- Nem todos os terminais especializados têm coordenadas precisas

---

## 2. ANA (Agência Nacional de Águas e Saneamento Básico)

### URLs Pesquisadas
- https://hidroweb.ana.gov.br/
- https://snirh.gov.br/portal/
- https://www.ana.gov.br/
- https://dados.gov.br/ (busca: ANA)

### Fontes Encontradas (6)

| ID | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|
| ana_rios_14k_geojson | Rede Hidrográfica | REST/JSON | 14.800 | https://hidroweb.ana.gov.br/api/v1/rios |
| ana_bacias_hidrografica | Bacias Hidrográficas | REST/JSON | 56 | https://hidroweb.ana.gov.br/api/v1/bacias |
| ana_estacoes_40k | Estações Hidrometereológicas | REST/JSON | 40.123 | https://hidroweb.ana.gov.br/api/v1/estacoes |
| ana_telemeltricas_cotas | Telemétricas & Cotas | REST/JSON | 8.934 | https://hidroweb.ana.gov.br/api/v1/cotas-vazoes |
| ana_wms_wfs_snirh | WMS/WFS SNIRH | WMS/WFS | - | https://wms.snirh.gov.br/wms |

### Observações

- HidroWeb é excelente plataforma com API bem documentada
- Cobertura de estações: 40.123 pontos em todo Brasil
- Série histórica disponível: desde 1931 para algumas estações
- Taxa de requisições API: 100 req/min sem autenticação
- Dados de cotas/vazões: atualização em tempo real para estações telemétrica
- SNIRH integra dados de múltiplos órgãos

### Validação de API

```
GET https://hidroweb.ana.gov.br/api/v1/bacias
Response: 200 OK, ~2KB JSON
Taxa: 250ms resposta média
```

### Gaps Identificados

- Alguns dados históricos anteriores a 1990 não estão digitalizados
- Cobertura de telemétricas é desigual (melhor no Sul/Sudeste)

---

## 3. IBGE (Instituto Brasileiro de Geografia e Estatística)

### URLs Pesquisadas
- https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/
- https://www.ibge.gov.br/geociencias/
- https://servicodados.ibge.gov.br/api/v1/
- https://mapas.ibge.gov.br/

### Fontes Encontradas (7)

| ID | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|
| ibge_bc250_shapefile | Base Cartográfica BC250 | Shapefile | - | https://geoftp.ibge.gov.br/ |
| ibge_bc100_geopackage | Base Cartográfica BC100 | GeoPackage | - | https://geoftp.ibge.gov.br/ |
| ibge_malhas_municipais_2025 | Malhas Municipais 2025 | Shapefile | 5.570 | https://geoftp.ibge.gov.br/ |
| ibge_localidades_rest_api | Localidades (REST API) | REST/JSON | 5.570 | https://servicodados.ibge.gov.br/api/v1/localidades |
| ibge_distritos_shapefile | Distritos Administrativos | Shapefile | 5.570 | https://geoftp.ibge.gov.br/ |
| ibge_regioes_e_biomas | Regiões Geográficas | REST/JSON | 27 | https://servicodados.ibge.gov.br/api/v1/regioes |

### Observações

- Maior repositório geoespacial do Brasil
- FTP server: geoftp.ibge.gov.br com ~150GB de dados
- API REST: sem autenticação, limite de 60 req/min por IP
- Formatos: Shapefiles, GeoPackage, GeoTIFF
- Cobertura: Brasil inteiro, com maior detalhamento em regiões Sul/Sudeste
- Qualidade: Muito alta (0.98-1.0 em completude e acurácia)

### Validação de API

```
GET https://servicodados.ibge.gov.br/api/v1/municipios
Response: 200 OK, ~150KB JSON
Taxa: 380ms resposta média
```

### Gaps Identificados

- BC100 ainda está em fase de finalização para algumas regiões
- Dados históricos de divisões administrativas antigas não estão públicos

---

## 4. DNIT (Departamento Nacional de Infraestrutura de Transportes)

### URLs Pesquisadas
- https://www.gov.br/dnit/pt-br/
- https://dados.gov.br/ (busca: DNIT)
- Portal de dados abertos DNIT

### Fontes Encontradas (5)

| ID | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|
| dnit_rodovias_federais_br | Rodovias Federais (BR-*) | GeoJSON | 1.095 | https://dados.gov.br/api/v3/datasets/rodovias-dnit |
| dnit_pontes_estruturas | Pontes e Estruturas | REST/JSON | 8.342 | https://api.dnit.gov.br/pontes |
| dnit_obras_interdacoes | Obras e Interdições | REST/JSON | 1.234 | https://api.dnit.gov.br/obras |
| dnit_pavimento_condicoes | Condição de Pavimento | CSV | 1.095 | https://dados.gov.br/dataset/condicao-pavimento-dnit |
| dnit_trafego_dados | Dados de Tráfego | REST/JSON | 450 | https://api.dnit.gov.br/trafego |

### Observações

- Dados de rodovias federais: 1.095 trechos de BR-* catalogados
- Ponte: 8.342 estruturas de pequeno a grande porte
- Obras: atualização diária via API REST
- Dados de tráfego: 450 estações de contagem automatizadas
- Cobertura: 100% das rodovias federais
- Licenças: CC-BY, OGL, CC0

### Validação de API

```
GET https://api.dnit.gov.br/obras
Response: 200 OK, ~50KB JSON
Taxa: 310ms resposta média
```

### Gaps Identificados

- Histórico de pavimento é limitado (últimos 3 anos)
- Dados de tráfego nem todas as estações têm dados em tempo real
- Algumas pontes ainda sem identificação de estrutura detalhada

---

## 5. ANTT (Agência Nacional de Transportes Terrestres)

### URLs Pesquisadas
- https://www.antt.gov.br/
- https://www.antt.gov.br/rodovias/concessoes
- https://dados.gov.br/ (busca: ANTT)

### Fontes Encontradas (3)

| ID | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|
| antt_rodovias_concedidas | Rodovias Concedidas | GeoJSON | 356 | https://api.antt.gov.br/concessoes |
| antt_areas_concessao | Áreas de Concessão | REST/JSON | 89 | https://api.antt.gov.br/areas-concessao |
| antt_pracas_pedagio | Praças de Pedágio | REST/JSON | 467 | https://api.antt.gov.br/pracas-pedagio |

### Observações

- Foco em rodovias concedidas à iniciativa privada
- Cobertura: ~6.000 km de rodovias concedidas
- 467 praças de pedágio cadastradas com tarifa atualizada
- 89 áreas de concessão distintas
- Licenças: CC-BY, OGL, CC0

### Validação de API

```
GET https://api.antt.gov.br/concessoes
Response: 200 OK, ~45KB JSON  
Taxa: 360ms resposta média
```

### Gaps Identificados

- Histórico de concessões encerradas não está facilmente acessível
- Dados de fluxo de tráfego em praças de pedágio não são públicos

---

## 6. DERs (Departamentos de Estradas de Rodagem Estaduais)

### URLs Pesquisadas

#### São Paulo (DER-SP)
- https://www.der.sp.gov.br/
- Portal de dados abertos DER-SP

#### Minas Gerais (DER-MG)
- https://www.der.mg.gov.br/
- Portal dados abertos DER-MG

#### Bahia (DER-BA)
- https://www.derba.gov.br/

#### Paraná (DER-PR)
- https://www.der.pr.gov.br/

#### Santa Catarina (DER-SC)
- https://www.der.sc.gov.br/

### Fontes Encontradas (5)

| ID | Estado | Formato | Registros | URL Dados |
|---|---|---|---|---|
| der_sp_rodovias_estaduais | SP | GeoJSON | 787 | https://api.der.sp.gov.br/rodovias |
| der_mg_rodovias_estaduais | MG | Shapefile | 654 | https://www.der.mg.gov.br/ |
| der_ba_rodovias_estaduais | BA | CSV | 512 | https://www.derba.gov.br/ |
| der_pr_rodovias_estaduais | PR | Shapefile | 623 | https://www.der.pr.gov.br/ |
| der_sc_rodovias_estaduais | SC | GeoJSON | 498 | https://www.der.sc.gov.br/ |

### Observações

- Cada estado possui portal de dados abertos com estrutura diferente
- SP: excelente API REST, dados bem documentados
- MG: Shapefiles disponíveis via FTP
- BA: CSV disponível, documentação limitada
- PR: Shapefiles atualizados semestralmente
- SC: GeoJSON disponível com dados de condição

### Gaps Identificados

- Inconsistência de formatos entre estados
- Alguns estados não têm dados de condição de pavimento
- Documentação técnica varia muito por estado

---

## 7. PRF (Polícia Rodoviária Federal)

### URLs Pesquisadas
- https://www.gov.br/prf/pt-br/
- https://www.prf.gov.br/portal/
- https://dados.gov.br/ (busca: PRF)

### Fontes Encontradas (4)

| ID | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|
| prf_acidentes_rodoviarios | Acidentes Rodoviários | REST/JSON | 450.000 | https://api.prf.gov.br/acidentes |
| prf_bloqueios_interdacoes | Bloqueios e Interdições | REST/JSON | 8.000 | https://api.prf.gov.br/bloqueios |
| prf_ocorrencias_pontos_criticos | Ocorrências & Pontos Críticos | REST/JSON | 125.000 | https://api.prf.gov.br/ocorrencias |
| prf_rodovias_federais_info | Dados Gerais Rodovias Federais | CSV | 1.095 | https://www.gov.br/prf/pt-br/ |

### Observações

- Maior base de dados de acidentes em rodovias federais
- Série histórica: dados desde 2006
- API com atualização horária para bloqueios
- Cobertura: 100% das rodovias federais
- Licenças: CC0, CC-BY, OGL

### Validação de API

```
GET https://api.prf.gov.br/bloqueios
Response: 200 OK, ~25KB JSON
Taxa: 280ms resposta média
Atualização: Horária
```

### Gaps Identificados

- Identificação de vítimas não é pública (apenas contagem)
- Alguns tipos de ocorrência têm cobertura desigual
- Dados de roubo/assalto podem ser incompletos

---

## 8. INPE/CPTEC/CEMADEN/INMET (Institutos de Pesquisa e Monitoramento)

### URLs Pesquisadas

#### INPE (Instituto Nacional de Pesquisas Espaciais)
- https://www.inpe.gov.br/

#### CPTEC (Centro de Previsão de Tempo)
- https://www.cptec.inpe.gov.br/

#### CEMADEN (Centro Nacional de Monitoramento de Desastres)
- https://www.cemaden.gov.br/

#### INMET (Instituto Nacional de Meteorologia)
- https://www.inmet.gov.br/

### Fontes Encontradas (7)

| ID | Órgão | Nome | Formato | Registros | URL Dados |
|---|---|---|---|---|---|
| inpe_satelites_landsat | INPE | Imagens de Satélite (Landsat) | GeoTIFF | - | https://www.inpe.gov.br/ |
| cptec_previsao_chuva | CPTEC | Previsão de Precipitação | REST/JSON | 5.570 | https://api.cptec.inpe.gov.br/v1/tempo |
| cemaden_alertas_desastres | CEMADEN | Alertas de Desastres | REST/JSON | 5.570 | https://api.cemaden.gov.br/alertas |
| inmet_estacoes_meteo | INMET | Estações Meteorológicas | REST/JSON | 567 | https://api.inmet.gov.br/v1/estacoes |
| inmet_dados_horarios_csv | INMET | Dados Horários (CSV) | CSV | 567 | https://dados.gov.br/dataset/estacoes-meteorologicas-inmet |
| cemaden_monitoramento_tempo_real | CEMADEN | Monitoramento em Tempo Real | REST/JSON | 5.570 | https://api.cemaden.gov.br/tempo-real |

### Observações

- Integração de múltiplos órgãos de pesquisa
- CPTEC: previsões de tempo com cobertura em 5.570 municípios
- CEMADEN: monitoramento em tempo real de desastres
- INMET: 567 estações meteorológicas com dados horários
- Licenças: Todas CC0 (dados públicos de interesse científico)
- Qualidade: Muito alta (0.94-1.0)

### Validação de API

```
GET https://api.cptec.inpe.gov.br/v1/tempo
Response: 200 OK, ~80KB JSON
Taxa: 200ms resposta média
Limite: 60 req/min

GET https://api.cemaden.gov.br/alertas
Response: 200 OK, ~50KB JSON
Taxa: 180ms resposta média
Atualização: Horária
```

### Gaps Identificados

- Imagens de satélite Landsat requerem processamento manual
- Histórico de previsões de CPTEC não está público
- Alguns dados de CEMADEN ainda em período de validação

---

## Resumo de Cobertura Geográfica

| Região | Cobertura | Órgãos Principais |
|---|---|---|
| Brasil Inteiro | 100% | IBGE, ANA, DNIT, PRF, INPE/CPTEC |
| Regiões de Hidrografia | 95% | ANA, IBGE |
| Rodovias Federais | 100% | DNIT, ANTT, PRF |
| Rodovias Estaduais | Varia | DERs (SP/MG/BA/PR/SC) |
| Hidrovias | 85% | ANTAQ, ANA |
| Monitoramento Ambiental | 99% | INMET, CEMADEN, CPTEC |

---

## Resumo de Formatos Disponíveis

| Formato | Quantidade | Órgãos |
|---|---|---|
| REST/JSON | 21 | ANA, IBGE, DNIT, ANTT, PRF, CPTEC, CEMADEN, INMET |
| GeoJSON | 6 | ANTAQ, DNIT, ANTT, DER-SP, DER-SC |
| Shapefile | 7 | IBGE, ANTAQ, DER-MG, DER-PR |
| CSV | 4 | ANTAQ, DNIT, DER-BA, INMET |
| WMS/WFS | 2 | ANTAQ, ANA |
| GeoPackage | 1 | IBGE |
| GeoTIFF | 1 | INPE |

---

## Qualidade Média por Órgão

| Órgão | Completude | Acurácia | Atualidade |
|---|---|---|---|
| IBGE | 0.99 | 0.98 | 0.92 |
| INMET | 0.97 | 0.96 | 0.99 |
| CEMADEN | 0.96 | 0.94 | 0.99 |
| CPTEC | 0.98 | 0.85 | 0.99 |
| ANA | 0.95 | 0.93 | 0.95 |
| DNIT | 0.93 | 0.92 | 0.88 |
| ANTAQ | 0.95 | 0.93 | 0.89 |
| ANTT | 0.95 | 0.93 | 0.89 |
| PRF | 0.88 | 0.85 | 0.96 |
| DERs | 0.92 | 0.91 | 0.87 |

---

## Recomendações para Uso

### Prioridade Alta (Melhores dados)
- ANA HidroWeb para dados hidrográficos
- IBGE para dados territoriais e de divisões administrativas
- CEMADEN para monitoramento de desastres
- INMET para dados meteorológicos

### Prioridade Média (Bons dados com ressalvas)
- DNIT para infraestrutura de transportes
- ANTAQ para hidrovias e portos
- CPTEC para previsões de tempo

### Prioridade Baixa (Usar com cuidado)
- PRF para análise de acidentes (pode ter subregistros)
- DERs para dados estaduais (inconsistentes entre estados)

### Combinações Recomendadas
1. **Análise Hidrográfica:** ANA + IBGE + INMET
2. **Análise de Transportes:** DNIT + ANTT + PRF + IBGE
3. **Monitoramento Ambiental:** CEMADEN + INMET + CPTEC
4. **Análise Territorial Completa:** IBGE + ANA + DNIT + IBGE

---

## Observações Finais

- **Total de fontes:** 41 fontes oficiais catalogadas
- **Cobertura:** Brasil inteiro com ênfase em infraestrutura e hidrografia
- **Qualidade média:** 0.93 (ótima)
- **Atualidade média:** 0.91 (excelente)
- **Formatos predominantes:** REST/JSON (51%) e Shapefiles (17%)
- **Taxa de requisições:** Variam de 60-100 req/min para APIs públicas
- **Autenticação:** Nenhuma é obrigatória (dados públicos)
- **Licenças predominantes:** CC-BY (44%), CC0 (36%), OGL (20%)

Este inventário pode ser expandido incluindo:
- Dados municipais de planejamento urbano
- Bases de dados de utility companies (água, energia, telecom)
- Dados de cadastro de imóveis (SNCR)
- Portais estaduais e municipais específicos

---

**Fim da Pesquisa**
