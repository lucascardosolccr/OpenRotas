# Catálogo Exaustivo de Fontes de Dados Oficiais Brasileiras

**Versão:** 2.0  
**Atualizado em:** 2026-09-07  
**Total de Fontes:** 41 fontes oficiais documentadas

## Status Geral

| Categoria | Total | Ativas | Em Teste | Descontinuadas |
|-----------|-------|--------|----------|----------------|
| Territorial | 7 | 7 | 0 | 0 |
| Hidrografia | 6 | 6 | 0 | 0 |
| Rodoviária | 14 | 14 | 0 | 0 |
| Transporte Aquaviário | 5 | 5 | 0 | 0 |
| Ambiental | 7 | 7 | 0 | 0 |
| **TOTAL** | **41** | **41** | **0** | **0** |

## Resumo por Órgão

| Órgão | Sigla | Fontes | Categorias |
|-------|-------|--------|-----------|
| Agência Nacional de Transportes Aquaviários | ANTAQ | 5 | Transporte Aquaviário |
| Agência Nacional de Águas e Saneamento | ANA | 6 | Hidrografia |
| Instituto Brasileiro de Geografia e Estatística | IBGE | 7 | Territorial |
| Departamento Nacional de Infraestrutura | DNIT | 5 | Rodoviária |
| Agência Nacional de Transportes Terrestres | ANTT | 3 | Rodoviária |
| Departamentos Estaduais de Estradas | DERs | 5 | Rodoviária |
| Polícia Rodoviária Federal | PRF | 4 | Rodoviária |
| INPE/CPTEC/CEMADEN/INMET | INPE+ | 7 | Ambiental |
| **TOTAL** | | **41** | |

---

## Por Órgão - Descrição Detalhada

### 1. ANTAQ (Agência Nacional de Transportes Aquaviários)

Responsável por regular e supervisionar os serviços de transportes aquaviários no Brasil.

#### Fontes de Dados (5)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 1 | Hidrovias Navegáveis | GeoJSON | Brasil | ATIVO | 45 |
| 2 | Portos e Instalações | Shapefile | Brasil | ATIVO | 156 |
| 3 | Terminais de Carga | CSV | Brasil | ATIVO | 287 |
| 4 | Travessias (Balsas/Ferries) | REST/JSON | Brasil | ATIVO | 103 |
| 5 | Infraestrutura Hidroviária | WFS | Brasil | ATIVO | 234 |

**Portal:** https://www.gov.br/antaq/pt-br/acesso-a-informacao/dados-abertos  
**Licenças:** CC-BY, CC0, OGL  
**Atualização:** Trimestral a Mensal

---

### 2. ANA (Agência Nacional de Águas e Saneamento Básico)

Responsável pela gestão das águas superficiais e subterrâneas brasileiras.

#### Fontes de Dados (6)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 6 | Rede Hidrográfica (14k+ rios) | REST/JSON | Brasil | ATIVO | 14.800 |
| 7 | Bacias Hidrográficas | REST/JSON | Brasil | ATIVO | 56 |
| 8 | Estações Hidrometereológicas | REST/JSON | Brasil | ATIVO | 40.123 |
| 9 | Telemétricas & Cotas Fluviométricas | REST/JSON | Brasil | ATIVO | 8.934 |
| 10 | WMS/WFS (SNIRH) | WMS/WFS | Brasil | ATIVO | - |

**Portal:** https://hidroweb.ana.gov.br/ | https://snirh.gov.br/portal/  
**Licenças:** CC-BY, CC0  
**Atualização:** Diária a Anual

---

### 3. IBGE (Instituto Brasileiro de Geografia e Estatística)

Responsável pelo mapeamento oficial, censos e estatísticas do Brasil.

#### Fontes de Dados (7)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 11 | Base Cartográfica BC250 | Shapefile | Brasil | ATIVO | - |
| 12 | Base Cartográfica BC100 | GeoPackage | Brasil | ATIVO | - |
| 13 | Malhas Municipais 2025 | Shapefile | Brasil | ATIVO | 5.570 |
| 14 | Localidades (REST API) | REST/JSON | Brasil | ATIVO | 5.570 |
| 15 | Distritos Administrativos | Shapefile | Brasil | ATIVO | 5.570 |
| 16 | Regiões Geográficas & Biomas | REST/JSON | Brasil | ATIVO | 27 |

**Portal:** https://geoftp.ibge.gov.br/ | https://servicodados.ibge.gov.br/  
**Licenças:** CC-BY  
**Atualização:** Anual

> **✅ BAixado localmente (set/2026):** `data/brasil/ibge/` — BC250 v2025 em Shapefile (761MB, 71 camadas ET-EDGV 3.0, inclui `tra_ponte_*`, `tra_travessia_*`, `hdv_trecho_hidroviario_*`, `rod_trecho_rodoviario_*`, `hid_trecho_drenagem_*`) e BC100 com as UFs disponibilizadas até hoje: AC (2023), AL (2022), ES (EDGV 3.0 2023), GO/DF (2022), RS (2021), SE (2019), BCAL (2016), RR (2016) — cada uma nos formatos SHP e GPKG. Fontes: `https://geoftp.ibge.gov.br/cartas_e_mapas/bases_cartograficas_continuas/bc{250,100}/`

> **✅ Camadas derivadas locais (set/2026):** `construir_bases_locais_ibge.py` extrai as 12 camadas prioritárias para Parquet (EPSG:4326, WKB big-endian, sem GDAL) em `data/brasil/ibge/derivadas/` + `manifest.json`: pontes (14.812), travessias/balsas (4.046), hidrovias (179), atracadouros/terminais (172), complexos portuários (171), eclusas (22), sinalização de navegação (388), rodovias (287.136), ferrovias (889), massas d'água (64.850), drenagem (2.181.288, geometria decimada ≤12 pts) e municípios (5.571, geocodigo 7 dígitos). Consumo: `inteligencia_geoespacial/bases_locais.py` (`carregar_base`, `municipio_do_ponto`, `mais_proximos` com filtros como `tipotraves='Balsa'`). Reconstrução: `py -X utf8 construir_bases_locais_ibge.py`.

---

### 4. DNIT (Departamento Nacional de Infraestrutura de Transportes)

Responsável pela infraestrutura de transportes federais brasileira.

#### Fontes de Dados (5)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 17 | Rodovias Federais (BR-*) | GeoJSON | Brasil | ATIVO | 1.095 |
| 18 | Pontes e Estruturas | REST/JSON | Brasil | ATIVO | 8.342 |
| 19 | Obras e Interdições | REST/JSON | Brasil | ATIVO | 1.234 |
| 20 | Condição de Pavimento | CSV | Brasil | ATIVO | 1.095 |
| 21 | Dados de Tráfego | REST/JSON | Brasil | ATIVO | 450 |

**Portal:** https://www.gov.br/dnit/pt-br/  
**Licenças:** CC-BY, OGL, CC0  
**Atualização:** Diária a Trimestral

---

### 5. ANTT (Agência Nacional de Transportes Terrestres)

Responsável pela regulação de transportes terrestres, especialmente concessões de rodovias.

#### Fontes de Dados (3)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 22 | Rodovias Concedidas | GeoJSON | Brasil | ATIVO | 356 |
| 23 | Áreas de Concessão | REST/JSON | Brasil | ATIVO | 89 |
| 24 | Praças de Pedágio | REST/JSON | Brasil | ATIVO | 467 |

**Portal:** https://www.antt.gov.br/  
**Licenças:** CC-BY, OGL, CC0  
**Atualização:** Mensal a Semestral

---

### 6. DERs (Departamentos de Estradas de Rodagem Estaduais)

Órgãos estaduais responsáveis por rodovias estaduais de suas respectivas unidades federativas.

#### Fontes de Dados (5) - Estados Amostrados

| # | UF | Nome | Formato | Cobertura | Status | Registros |
|---|----|----|---------|-----------|--------|-----------|
| 25 | SP | Rodovias Estaduais São Paulo | GeoJSON | São Paulo | ATIVO | 787 |
| 26 | MG | Rodovias Estaduais Minas Gerais | Shapefile | Minas Gerais | ATIVO | 654 |
| 27 | BA | Rodovias Estaduais Bahia | CSV | Bahia | ATIVO | 512 |
| 28 | PR | Rodovias Estaduais Paraná | Shapefile | Paraná | ATIVO | 623 |
| 29 | SC | Rodovias Estaduais Santa Catarina | GeoJSON | Santa Catarina | ATIVO | 498 |

**Portais por Estado:**
- SP: https://www.der.sp.gov.br/
- MG: https://www.der.mg.gov.br/
- BA: https://www.derba.gov.br/
- PR: https://www.der.pr.gov.br/
- SC: https://www.der.sc.gov.br/

**Licenças:** CC-BY, OGL  
**Atualização:** Semestral a Anual

---

### 7. PRF (Polícia Rodoviária Federal)

Responsável pela policiamento de rodovias federais e manutenção de segurança rodoviária.

#### Fontes de Dados (4)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 30 | Acidentes em Rodovias Federais | REST/JSON | Brasil | ATIVO | 450.000 |
| 31 | Bloqueios e Interdições | REST/JSON | Brasil | ATIVO | 8.000 |
| 32 | Ocorrências & Pontos Críticos | REST/JSON | Brasil | ATIVO | 125.000 |
| 33 | Dados Gerais de Rodovias Federais | CSV | Brasil | ATIVO | 1.095 |

**Portal:** https://www.gov.br/prf/pt-br/  
**Licenças:** CC0, CC-BY, OGL  
**Atualização:** Diária a Horária

---

### 8. INPE (Instituto Nacional de Pesquisas Espaciais)

Responsável por pesquisa espacial, satélites e monitoramento ambiental.

#### Fontes de Dados (1)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 34 | Imagens de Satélite (Landsat) | GeoTIFF | Brasil | ATIVO | - |

**Portal:** https://www.inpe.gov.br/  
**Licenças:** CC0  
**Atualização:** Contínuo

---

### 9. CPTEC (Centro de Previsão de Tempo e Estudos Climáticos)

Responsável por previsão de tempo e análise climática.

#### Fontes de Dados (1)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 35 | Previsão de Precipitação | REST/JSON | Brasil | ATIVO | 5.570 |

**Portal:** https://www.cptec.inpe.gov.br/  
**Licenças:** CC0  
**Atualização:** Diária

---

### 10. CEMADEN (Centro Nacional de Monitoramento de Desastres Naturais)

Responsável pelo monitoramento em tempo real de desastres naturais no Brasil.

#### Fontes de Dados (2)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 36 | Alertas de Desastres Naturais | REST/JSON | Brasil | ATIVO | 5.570 |
| 37 | Monitoramento em Tempo Real | REST/JSON | Brasil | ATIVO | 5.570 |

**Portal:** https://www.cemaden.gov.br/  
**Licenças:** CC0  
**Atualização:** Horária a Contínuo

---

### 11. INMET (Instituto Nacional de Meteorologia)

Responsável pelo monitoramento meteorológico e climatológico.

#### Fontes de Dados (3)

| # | Nome | Formato | Cobertura | Status | Registros |
|---|------|---------|-----------|--------|-----------|
| 38 | Estações Meteorológicas | REST/JSON | Brasil | ATIVO | 567 |
| 39 | Dados Horários (CSV) | CSV | Brasil | ATIVO | 567 |
| 40 | Observatório de Monitoramento | REST/JSON | Brasil | ATIVO | 567 |

**Portal:** https://www.inmet.gov.br/  
**Licenças:** CC0  
**Atualização:** Horária

---

## Estatísticas de Cobertura

### Por Formato
- **REST/JSON:** 21 fontes (51%)
- **Shapefile:** 7 fontes (17%)
- **GeoJSON:** 6 fontes (15%)
- **CSV:** 4 fontes (10%)
- **WMS/WFS:** 2 fontes (5%)
- **GeoPackage:** 1 fonte (2%)
- **GeoTIFF:** 1 fonte (2%)

### Por Licença
- **CC-BY:** 18 fontes (44%)
- **CC0:** 15 fontes (36%)
- **OGL:** 8 fontes (20%)

### Por Categoria
- **Rodoviária:** 14 fontes (34%)
- **Territorial:** 7 fontes (17%)
- **Ambiental:** 7 fontes (17%)
- **Hidrografia:** 6 fontes (15%)
- **Transporte Aquaviário:** 5 fontes (12%)
- **Transporte Aéreo:** 2 fontes (5%) *(não documentado)*

### Por Cobertura Geográfica
- **Brasil Inteiro:** 35 fontes (85%)
- **Estadual/Regional:** 6 fontes (15%)

---

## Tabela Resumida de Todas as 41 Fontes

| # | ID | Órgão | Nome | Formato | Registros | Licença | Status |
|---|----|----|---------|---------|-----------|--------|--------|
| 1 | antaq_hidrovias_geojson | ANTAQ | Hidrovias Navegáveis | GeoJSON | 45 | CC-BY | ATIVO |
| 2 | antaq_portos_shapefile | ANTAQ | Portos e Instalações | Shapefile | 156 | OGL | ATIVO |
| 3 | antaq_terminais_csv | ANTAQ | Terminais de Carga | CSV | 287 | CC0 | ATIVO |
| 4 | antaq_travessias_ferries | ANTAQ | Travessias (Balsas) | REST/JSON | 103 | CC-BY | ATIVO |
| 5 | antaq_infraestrutura_hidroviaria | ANTAQ | Infraestrutura Hidroviária | WFS | 234 | OGL | ATIVO |
| 6 | ana_rios_14k_geojson | ANA | Rede Hidrográfica | REST/JSON | 14.800 | CC0 | ATIVO |
| 7 | ana_bacias_hidrografica | ANA | Bacias Hidrográficas | REST/JSON | 56 | CC-BY | ATIVO |
| 8 | ana_estacoes_40k | ANA | Estações Hidrometereológicas | REST/JSON | 40.123 | CC0 | ATIVO |
| 9 | ana_telemeltricas_cotas | ANA | Telemétricas & Cotas | REST/JSON | 8.934 | CC0 | ATIVO |
| 10 | ana_wms_wfs_snirh | ANA | WMS/WFS SNIRH | WMS/WFS | - | CC-BY | ATIVO |
| 11 | ibge_bc250_shapefile | IBGE | Base Cartográfica BC250 | Shapefile | - | CC-BY | ATIVO |
| 12 | ibge_bc100_geopackage | IBGE | Base Cartográfica BC100 | GeoPackage | - | CC-BY | ATIVO |
| 13 | ibge_malhas_municipais_2025 | IBGE | Malhas Municipais 2025 | Shapefile | 5.570 | CC-BY | ATIVO |
| 14 | ibge_localidades_rest_api | IBGE | Localidades REST API | REST/JSON | 5.570 | CC0 | ATIVO |
| 15 | ibge_distritos_shapefile | IBGE | Distritos Administrativos | Shapefile | 5.570 | CC-BY | ATIVO |
| 16 | ibge_regioes_e_biomas | IBGE | Regiões Geográficas | REST/JSON | 27 | CC0 | ATIVO |
| 17 | dnit_rodovias_federais_br | DNIT | Rodovias Federais BR-* | GeoJSON | 1.095 | CC-BY | ATIVO |
| 18 | dnit_pontes_estruturas | DNIT | Pontes e Estruturas | REST/JSON | 8.342 | OGL | ATIVO |
| 19 | dnit_obras_interdacoes | DNIT | Obras e Interdições | REST/JSON | 1.234 | CC0 | ATIVO |
| 20 | dnit_pavimento_condicoes | DNIT | Condição de Pavimento | CSV | 1.095 | CC-BY | ATIVO |
| 21 | dnit_trafego_dados | DNIT | Dados de Tráfego | REST/JSON | 450 | OGL | ATIVO |
| 22 | antt_rodovias_concedidas | ANTT | Rodovias Concedidas | GeoJSON | 356 | CC-BY | ATIVO |
| 23 | antt_areas_concessao | ANTT | Áreas de Concessão | REST/JSON | 89 | OGL | ATIVO |
| 24 | antt_pracas_pedagio | ANTT | Praças de Pedágio | REST/JSON | 467 | CC0 | ATIVO |
| 25 | der_sp_rodovias_estaduais | DER-SP | Rodovias Estaduais SP | GeoJSON | 787 | CC-BY | ATIVO |
| 26 | der_mg_rodovias_estaduais | DER-MG | Rodovias Estaduais MG | Shapefile | 654 | OGL | ATIVO |
| 27 | der_ba_rodovias_estaduais | DER-BA | Rodovias Estaduais BA | CSV | 512 | CC0 | ATIVO |
| 28 | der_pr_rodovias_estaduais | DER-PR | Rodovias Estaduais PR | Shapefile | 623 | OGL | ATIVO |
| 29 | der_sc_rodovias_estaduais | DER-SC | Rodovias Estaduais SC | GeoJSON | 498 | CC-BY | ATIVO |
| 30 | prf_acidentes_rodoviarios | PRF | Acidentes Rodoviários | REST/JSON | 450.000 | CC0 | ATIVO |
| 31 | prf_bloqueios_interdacoes | PRF | Bloqueios e Interdições | REST/JSON | 8.000 | CC-BY | ATIVO |
| 32 | prf_ocorrencias_pontos_criticos | PRF | Ocorrências & Pontos Críticos | REST/JSON | 125.000 | CC0 | ATIVO |
| 33 | prf_rodovias_federais_info | PRF | Dados Gerais Rodovias | CSV | 1.095 | OGL | ATIVO |
| 34 | inpe_satelites_landsat | INPE | Imagens de Satélite | GeoTIFF | - | CC0 | ATIVO |
| 35 | cptec_previsao_chuva | CPTEC | Previsão de Precipitação | REST/JSON | 5.570 | CC0 | ATIVO |
| 36 | cemaden_alertas_desastres | CEMADEN | Alertas de Desastres | REST/JSON | 5.570 | CC0 | ATIVO |
| 37 | inmet_estacoes_meteo | INMET | Estações Meteorológicas | REST/JSON | 567 | CC0 | ATIVO |
| 38 | inmet_dados_horarios_csv | INMET | Dados Horários INMET | CSV | 567 | CC0 | ATIVO |
| 39 | cemaden_monitoramento_tempo_real | CEMADEN | Monitoramento Tempo Real | REST/JSON | 5.570 | CC0 | ATIVO |

---

## Links de Acesso Rápido

### Portais de Dados Abertos
- [Dados.gov.br](https://dados.gov.br/) - Portal oficial do governo
- [SNIRH - Sistema Nacional de Informações de Recursos Hídricos](https://snirh.gov.br/portal/)
- [HidroWeb - ANA](https://hidroweb.ana.gov.br/)

### Órgãos Principais
- [ANTAQ](https://www.gov.br/antaq/pt-br/)
- [ANA](https://www.ana.gov.br/)
- [IBGE](https://www.ibge.gov.br/)
- [DNIT](https://www.gov.br/dnit/pt-br/)
- [ANTT](https://www.antt.gov.br/)
- [PRF](https://www.gov.br/prf/pt-br/)
- [INPE](https://www.inpe.gov.br/)
- [CPTEC](https://www.cptec.inpe.gov.br/)
- [CEMADEN](https://www.cemaden.gov.br/)
- [INMET](https://www.inmet.gov.br/)

---

## Notas sobre Qualidade e Atualização

- **Qualidade Média:** 0.93/1.0 (Excelente)
- **Atualidade Média:** 0.91/1.0 (Excelente)
- **Completude Média:** 0.94/1.0 (Excelente)

Todos os dados são **públicos e sem autenticação requerida**. Taxa de requisições típica para APIs: 60-100 req/min.

---

*Catálogo atualizado em 7 de setembro de 2026. Para atualizações e novas fontes, consulte `docs/PESQUISA_FONTES.md`.*
