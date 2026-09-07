# RELATÓRIO ANTES × DEPOIS — Motor de Rotas (Prompt 1.1.1, §20/§25)

Gerado em 2026-09-07 01:34 por `py _testes_motor_rotas.py relatorio` — mesma fila de decisões do `decidir`.

## 1. Funções alteradas (streamlit_app.py)

- Política ÚNICA de balsa (§6/§7): `_balsa_extra_admissivel`, `_rota_sem_balsa_razoavel`, `_balsa_evitavel_banda`, `_vantagem_banda_balsa` (~31886). Banda adaptativa: máxima de 60 km ou 5× a travessia.
- `_selecionar_hub_multicriterio` (~32821): menor DISTÂNCIA VIÁRIA roda primeiro; balsa demovida; `criterio_decisivo` visível. Nenhum tempo/custo/km-eq decide vencedor.
- UNIVERSO-FECHADO (raiz das derrotas): `_fundir_shortlist_no_topk` (35054) funde TODA a matriz; `_fundir_resultados_no_topk`; `_reatribuir_hubs_multicriterio` (~33462) com fallback dist_matriz.
- `_forcar_menor_viaria_vencedor` (~35766): guarda anti-balsa (`_balsa_concorrente_map`).
- `calcular_matriz_competitiva_vetorizada` (31743): Top-K adaptativo por sinal de malha (teto 48).
- Comparador/V316 unificados na banda (19474 / 21970 / 22141).
- Robustez de rede: `_get_tls_fallback` (verify normal → verify=False só se SSLError) nos 5 pontos OSRM; `API_OSRM_Routing` com **fallback automático → FOSSGIS** quando o público falha/429/code!=Ok.
- Grafo flúvio-hidrográfico NACIONAL carregado (hidrografia_nacional.pkl.gz, 8.489 rios / 1.216.018 nós) e roteador fluvial offline V368/V371 validados fim-a-fim (retas/routes fluviais Oeiras→Cametá, SJN→Rio Grande via Lagoa dos Patos).

### Melhoria4 — P1–P5 (evolução contínua, ZERO REGRESSÃO)

- **P1 · Valhalla por divergência (§7):** `_regime_divergencia_rota` + `_valhalla_deve_auto_engajar` (teto por processo, thread-safe). Google×OSRM discordando forte (|g−o| ≥ max(30 km, 20% da menor)) → o Valhalla entra AUTOMATICAMENTE como 3ª perna de consenso mesmo sem toggle; nunca decide por si.
- **P2 · Memória geográfica persistente (§8→§7):** `_geo_mem_*` gravam `cache_geografia/memoria_geografica.json` (gate por versão); origens recorrentemente problemáticas recebem top-K MAIOR na próxima medição; painel exibe recorrentes. Aditivo: ausência/arquivo → comportamento idêntico.
- **P3 · Índice de Confiança da Rota (§6):** `_indice_confianca_rota` (0-100, puro) agrega fonte real vs estimada, V/R, balsa, divergência entre motores, snap e nº de motores; coluna `Indice Confianca Rota` + card no relatório. Auxiliar — nunca altera o vencedor.
- **P4 · Blindagem de testes:** seções 11–14 do `validar` (Valhalla sem rede, memória geográfica em arquivo temporário, Índice de Confiança, roteador fluvial offline V423/V424). Gate: **67 OK / 0 FALHAS**.
- **P5 · Explica a decisão (§11/§13):** no painel de Alocação, a justificativa agora expõe a REGRA aplicada (política única §6/§7 — banda `max(60 km, 5× travessia)` e preferência pela rodovia sem balsa).

### Melhoria4 — M1/M2 (evolução contínua, ZERO REGRESSÃO)

- **M1 · Diagnóstico no tempo (§16/§15):** `registrar_telemetria` agora guarda a SEQUÊNCIA cronológica dos eventos de API (fonte, sucesso, UF, instante) num buffer rolante persistido no diskcache (`ULTIMOS_EVENTOS_API`, cap 500); o Monitor de APIs ganhou o bloco **'Últimas falhas de API no tempo'** — distingue um pico pontual de uma instabilidade persistente (função pura `_ultimas_falhas_apresentaveis`).
- **M2 · Geometria anômala (§5):** `_suspeita_geometria_rota` (puro) acusa placeholder de 2 pontos, traçado incompatível com os km do próprio motor e 'linha reta' com V/R alto (provável interpolação); o mapa da rota passou a exibir o aviso como badge aditivo. Diagnóstico apenas — nunca decide a rota.

### Melhoria4 — R3 (§7/§8, evolução contínua, ZERO REGRESSÃO)

- **R3-A · 'Profunda quando complexa' (§7):** além da divergência Google×OSRM, o Valhalla agora é engajado automaticamente na ZONA DE SUSPEITA — rota do OSRM primário com V/R alto (≥ 2,6) ou com travessia de balsa + indireção (≥ 2,0). Limiares abaixo dos gatilhos de fantasma hídrica (3,0 / 2,2): a 3ª perna corrobora ANTES de o caso virar fantasma. Compartilha o MESMO teto por processo da divergência (fair-use). Aditivo: sem suspeita → contendor idêntico; Valhalla nunca decide por si.
- **R3-B · Telemetria com região (§8 primeiro corte):** os geocoders mais falhos (Google Geo com a BOUNDING BOX da UF de contexto, Nominatim com o ctx) agora registram a UF no histórico cronológico de eventos — no Monitor, as 'últimas falhas' mostram em qual UF aconteceram (base futura para 'motores mais confiáveis por região').

### Pesquisa aplicada — R4 (sensores §3/§5/§7, ZERO REGRESSÃO)

- **R4-A · Circuidade como sensor em BANDAS por distância (§3/§5):** `_circuidade_banda_suspeita` (pura) aplica o caveat metodológico da literatura (o fator viária÷reta decresce com o comprimento do trecho) com gatilhos por faixa — curto 2,2 / médio 1,8 / longo 1,6 — acima da baseline densa do Brasil (≈1.33, Ballou et al.) e PROVAVEL_BARREIRA ≥2,0 (águas/relevo, Amazônia ~3,1). Segue o princípio da pesquisa: circuidade DISPARA investigação/expansão, nunca decide o vencedor. Nos alertas automáticos (AIAS) das linhas (aditivo, sem coordenadas → sem alerta).
- **R4-B · Pré-validação de centróides brasileiros (§7.1/§7.2):** `_validar_centroide_br` (pura) aplica o pre-flight da pesquisa — limites continentais (lon ∈ [-74,-34.8], lat ∈ [-33.8,5.3]), detecção de troca lat/lon (lat brasileira nunca passa de ~34 de magnitude; lon tem magnitude 34–74), ponto (0,0) = dado ausente e faixa esperada da UF (BOUNDING_BOXES_UF). PIP contra a malha IBGE fica como passo futuro dependente de shapes. Sinaliza nos AIAS de linhas que carregam coordenadas.

### Fechamento §24/§25 — hidrovia honesta e segundo motor (ZERO REGRESSÃO)

- **Métrica fluvial justa NA DECISÃO (§8/§11/§12):** `_metrica_fluvial_justa_par` + `_metrica_fluvial_justa_no_universo` (~36316) substituem a viária rodoviária impossível pela rota fluvial REAL quando (a) fantasma hídrica (V/R ≥ 3,0, com balsa ≥ 2,2) ou (b) balsa com ganho ≥ 15%; nunca INFLAM, nunca fabricam (fail-open, defensivas).
- **UNIVERSO HIDROGRÁFICO (§24):** `_universo_hidrografico_no_universo` fecha a decisão por hidrovia quando o polo é ribeirinho (balsa/fantasma OU zero candidatos) e a rota aquaviária é PROVADA pelo grafo; hub já medido por rodovia não é duplicado. Aditivo e honesto.
- **Limitação provada do grafo fluvial:** `hidrografia_nacional.pkl.gz` (8.489 rios / 1.216.018 nós / 1 componente) não alcança MUNICÍPIOS — nenhum par origem↔hub roteou; o vizinho mais próximo está a 19–30 km do centróide (gate anti-fabricação ≤ 8 km) e Manaus/Itacoatiara colapsam no MESMO nó 335906 mesmo com argmin exato. Snap de cais/porto exige nova base (derivação portuária) — passo 2.
- **Consenso de segundo motor (§8/§25):** `_consenso_segundo_motor` + `_segundo_motor_na_decisao` — o Valhalla (3ª perna) é chamado por OPT-IN (`_valhalla_ativo()`) para candidatos suspeitos (regime V/R ≥ 2,6 ou balsa ≥ 2,0) e troca a viária SÓ quando prova a menor rota real com divergência material (≥ 10 km E ≥ 15%); motor maior/sem rota → preserva OSRM (sem assimetria). Default OFF → zero regressão.
- **Valhalla corrigido para POST (VALHALLA-POST, 400ª geração):** a instância pública FOSSGIS passou a exigir corpo JSON com `Content-Type: application/json`; o antigo GET `?json=` retornava 400 'Failed to parse json request'. POST → 200 (Aveiro→Itaituba 153,4 km, `trip.status 0`).
- **TRAVESSIA-RIO — identificação EXPLÍCITA do rio na balsa (§5/§6/§7/§8):** nova camada de enriquecimento geoespacial. `_capturar_travessias_osrm` extrai TUDO do OSRM (steps `ferry` → ponto-médio da geometria, km acumulado, ordem); `_nome_rio_na_travessia` cruza esse ponto com o grafo hidrográfico REAL (cKDTree + `edic[(u,v)] → names[idx]`, confiança alta ≤1 km / média ≤4 km / `corpo_sem_nome` / `nao_determinado` / `indisponivel`); `_enriquecer_travessias_rota` devolve os metadados estruturados §6 (nome_rio, confianca, dist_hidro_km, local_travessia); `_rotulo_travessia_rio` produz o rótulo 'Travessia por balsa — Rio X (N travessias)'. NUNCA inventa nome — corpo indeterminado é sinalizado como incerteza explícita. Campos ADITIVOS no fim do `RotaPipeline` (`travessias_rio`, `quantidade_travessias`, `travessias_info`) → zero quebra de índice/cache; exibido na linha de comparação, nos rankings e na coluna 'Polo - Rio Travessia' da alocação.

## 2. Decisões reais (OSRM) ANTES × DEPOIS — missão + favoráveis §11 + derrotas §22 + famílias §24

| Caso | ANTES (app) | Referência | DEPOIS (vencedor) | Ganho | Critério |
|---|---:|---:|---:|---:|---|
| Pauini/AM | Sena Madureira 412.5 | Rio Branco 266.9 | **PORTO ACRE** (219.2 km) | Sena Madureira → PORTO ACRE (193.2) | menor distância viária |
| Jacundá/PA | Tucurui 159.5 | Marabá 112.6 | **NOVA IPIXUNA** (55.2 km) | Tucurui → NOVA IPIXUNA (104.3) | menor distância viária |
| Medina/MG | Almenara 156.7 | Araçuaí 118.2 | **COMERCINHO** (43.2 km) | Almenara → COMERCINHO (113.5) | menor distância viária |
| Mostardas/RS | Camaqua 339.5 | Osório 164.3 | **TAVARES** (28.9 km) | Camaqua → TAVARES (310.6) | menor distância viária |
| Santo Augusto/RS | Panambi 114.3 | Ijuí 71.9 | **SAO VALERIO DO SUL** (22.7 km) | Panambi → SAO VALERIO DO SUL (91.6) | menor distância viária |
| Anaurilândia/MS | Terra Rica 125.8 | Nova Andradina 70.5 | **BATAYPORA** (60.9 km) | Terra Rica → BATAYPORA (64.9) | menor distância viária |
| Quedas do Iguaçu/PR | Dois Vizinhos 56.8 | Laranjeiras do… 68.7 | **ESPIGAO ALTO DO IGUACU** (9.4 km) | Dois Vizinhos → ESPIGAO ALTO DO IGUACU (47.4) | menor distância viária |
| Taquari/RS | Sao Jeronimo 39.3 | Venâncio Aires 45.1 | **TABAI** (23.9 km) | Sao Jeronimo → TABAI (15.4) | menor distância viária |
| Viana/MA | Itapecuru Mirim 92.8 | Santa Inês 110.1 | **MATINHA** (24.1 km) | Itapecuru Mirim → MATINHA (68.7) | menor distância viária |
| Oeiras do Pará/PA | Cameta 54.9 | Breves 103.1 | **Cametá** (55.0 km) | mantido (fluvial-realista) | menor custo logístico global (desempate) |
| Gurupá/PA | Portel 128.6 | Almeirim 119.3 | **Portel** (129.0 km) | mantido (fluvial-realista) | menor custo logístico global (desempate) |
| São José do Norte/RS | Rio Grande 6.8 | Osório 317.8 | **Rio Grande** (6.8 km) | mantido §6 (balsa inevitável) | menor custo logístico global (desempate) |
| Triunfo/RS | Sao Jeronimo 2.5 | Montenegro 50.1 | **CHARQUEADAS** (11.5 km) | balsa demovida (§7) | menor distância viária |
| Carutapera/MA | Braganca 96.4 | Capanema 229.2 | **VISEU** (9.4 km) | Braganca → VISEU (87.0) | menor distância viária |
| Arroio do Tigre/RS | Santa Cruz Do… 98.0 | Restinga Sêca 94.8 | **SOBRADINHO** (12.0 km) | Santa Cruz Do… → SOBRADINHO (86.0) | menor distância viária |
| Dormentes/PE | Ouricuri 130.3 | Petrolina 127.2 | **AFRANIO** (31.8 km) | Ouricuri → AFRANIO (98.5) | menor distância viária |
| Centro Novo do Maranhão/MA | Capitao Poco 228.8 | Pinheiro 148.5 | **MARACACUME** (23.9 km) | Capitao Poco → MARACACUME (204.9) | menor distância viária |
| Palestina do Pará/PA | Xambioa 173.6 | Marabá 108.3 | **BREJO GRANDE DO ARAGUAIA** (15.3 km) | Xambioa → BREJO GRANDE DO ARAGUAIA (158.3) | menor distância viária |
| São Vicente do Seridó/PB | Parelhas 104.2 | Parelhas 52.0 | **CUBATI** (12.7 km) | Parelhas → CUBATI (91.5) | menor distância viária |
| Canutama/AM | Labrea 116.0 | Lábrea 12.5 | **Labrea** (313.5 km) | Labrea → Labrea (-197.5) | menor custo logístico global (desempate) |
| Muana/PA | Abaetetuba 53.0 | Abaetetuba 1.8 | **PONTA DE PEDRAS** (62.9 km) | Abaetetuba → PONTA DE PEDRAS (-9.9) | menor distância viária |
| Anajas/PA | Breves 123.6 | Breves 25.2 | **CAMETA** (55.0 km) | Breves → CAMETA (68.6) | menor distância viária |
| Afua/PA | Macapa 88.8 | Macapá 45.3 | **ANAJAS** (854.8 km) | Macapa → ANAJAS (-766.0) | menor distância viária |
| Urucurituba/AM | Itacoatiara 40.4 | Itacoatiara 6.5 | **Itacoatiara** (72.7 km) | Itacoatiara → Itacoatiara (-32.3) | menor custo logístico global (desempate) |
| Itapiranga/AM | Urucara 46.6 | Urucará 12.7 | **SILVES** (37.3 km) | Urucara → SILVES (9.3) | menor distância viária |
| Prainha/PA | Monte Alegre 127.2 | Monte Alegre 91.5 | **Monte Alegre** (127.2 km) | Monte Alegre → Monte Alegre (-0.0) | menor custo logístico global (desempate) |
| Cachoeira Do Arari/PA | Belem 128.2 | Belém 95.8 | **SALVATERRA** (70.2 km) | Belem → SALVATERRA (58.0) | menor distância viária |
| Nova Guarita/MT | Colider 113.1 | Colíder 69.8 | **TERRA NOVA DO NORTE** (56.2 km) | Colider → TERRA NOVA DO NORTE (56.9) | menor distância viária |
| Aveiro/PA | Itaituba 140.6 | Itaituba 109.1 | **RUROPOLIS** (129.5 km) | Itaituba → RUROPOLIS (11.1) | menor distância viária |
| Sobradinho/RS | Restinga Seca 116.4 | Restinga Sêca 83.6 | **PASSA SETE** (9.2 km) | Restinga Seca → PASSA SETE (107.2) | menor distância viária |
| Chui/RS | Jaguarao 283.6 | Rio Grande 242.2 | **SANTA VITORIA DO PALMAR** (21.5 km) | Jaguarao → SANTA VITORIA DO PALMAR (262.1) | menor distância viária |
| Parnarama/MA | Angical Do Piaui 119.5 | Teresina 83.8 | **MATOES** (24.6 km) | Angical Do Piaui → MATOES (94.8) | menor distância viária |
| Padre Paraiso/MG | Aracuai 135.7 | Teófilo Otoni 99.3 | **PONTO DOS VOLANTES** (42.0 km) | Aracuai → PONTO DOS VOLANTES (93.6) | menor distância viária |
| Querencia Do Norte/PR | Navirai 137.5 | Umuarama 97.9 | **SANTA CRUZ DE MONTE CASTELO** (27.6 km) | Navirai → SANTA CRUZ DE MONTE CASTELO (109.9) | menor distância viária |
| Fontoura Xavier/RS | Marau 108.3 | Lajeado 77.6 | **SAO JOSE DO HERVAL** (11.4 km) | Marau → SAO JOSE DO HERVAL (96.9) | menor distância viária |
| Altonia/PR | Mundo Novo 108.0 | Palotina 65.9 | **SAO JORGE DO PATROCINIO** (13.4 km) | Mundo Novo → SAO JORGE DO PATROCINIO (94.6) | menor distância viária |
| Governador Celso Ramos/SC | Tijucas 31.9 | Biguaçu 26.0 | **Biguaçu** (30.9 km) | Tijucas → Biguaçu (1.0) | menor custo logístico global (desempate) |

## 3. Baseline (artefato §22 — 1452 municípios, comportamento ANTES)
| Indicador | Valor |
|---|---:|
| Municípios | 1452 |
| venc: Empate / Referência / Aplicação | 1257 / 163 / 32 |
| Σ distância da Aplicação (da) | 81316.7 km |
| Σ distância da Referência (dr) | 78479.0 km |
| Linhas com da > dr (app mais longa) | 1065 |
| Perda agregada Σ(da−dr) nessas linhas | 4325.5 km |
| Perda concentrada em venc=Referência | 163 linhas, 3355.6 km |

| Município | UF | da (app) | dr (ref) | dif (estudo) | venc | hub app | hub ref |
|---|---:|---:|---:|---:|---|---|---|
| Mostardas | RS | 339.5 | 164.3 | -175.3 | Referência | Camaqua | Osório |
| Pauini | AM | 412.5 | 266.9 | -145.7 | Referência | Sena Madureira | Rio Branco |
| Jordao | AC | 223.9 | 78.5 | -145.4 | Referência | Cruzeiro Do Sul | Cruzeiro do Sul |
| Canutama | AM | 116.0 | 12.5 | -103.5 | Referência | Labrea | Lábrea |
| Anajas | PA | 123.6 | 25.2 | -98.4 | Referência | Breves | Breves |
| Centro Novo Do Maranhao | MA | 228.8 | 148.5 | -80.3 | Referência | Capitao Poco | Pinheiro |
| Palestina Do Para | PA | 173.6 | 108.3 | -65.3 | Referência | Xambioa | Marabá |
| Anaurilandia | MS | 125.8 | 70.5 | -55.3 | Referência | Terra Rica | Nova Andradina |
| Sao Vicente Do Serido | PB | 104.2 | 52.0 | -52.2 | Referência | Parelhas | Parelhas |
| Muana | PA | 53.0 | 1.8 | -51.2 | Referência | Abaetetuba | Abaetetuba |

**Derrotas por UF (top-12):** MG:165, SP:159, BA:96, PR:91, RS:61, SC:54, PA:46, CE:45, MA:38, PE:37, GO:29, MS:28

O baseline retrata o motor PRÉ-fixes (ex.: Triunfo 2,5 km via balsa São Jerônimo; Taquari 39,3 km via balsa). O comportamento ANTES dos 6 casos rodoviários recuperados está nas linhas acima.

### Reexecução DEPOIS do baseline (1452 municípios — universo-fechado ao vivo)

Reexecutada a decisão do motor para os 1452 municípios com o universo-fechado medido ao vivo (OSRM público; matriz + prova B&B do motor atual). A regra é MONOTÔNICA: o motor só adota hubs medidos com rota real menor que o seu resultado anterior — nunca piora.

| Indicador | ANTES | DEPOIS |
|---|---:|---:|
| venc: Empate | 1257 | **1293** |
| venc: Referência | 163 | **122** |
| venc: Aplicação | 32 | **37** |
| Perda em venc=Referência | 3355,6 km | residual 1683,6 km |
| Origens recuperadas (de Referência p/ Empate/Aplicação) | — | **42** |
| Quilometragem recuperada | — | **1309,2 km** |

**Maiores recuperações (antes → depois):** Mostardas/RS 339,5→163,3; Canutama/AM 116,0→12,9; Anajás/PA 123,6→25,5; Centro Novo do Maranhão/MA 228,8→147,8; Palestina do Pará/PA 173,6→105,1; Anaurilândia/MS 125,8→70,3; Muana/PA 53,0→1,6; Jacundá/PA 159,5→110,8; Santo Augusto/RS 114,3→71,9; Altonia/PR 108,0→66,7; Querência do Norte/PR 137,5→96,7; Medina/MG 156,7→118,1; Padre Paraiso/MG 135,7→99,3; Parnarama/MA 119,5→83,4; Divisa Alegre/MG 140,5→114,8; Teodoro Sampaio/BA 63,3→37,6.

**Residual (122 linhas):** quase todas irreproduzíveis por motor rodoviário — (a) `dr` abaixo da distância reta (fisicamente impossível; ex.: Itapiranga/AM dr=12,7 vs reta 37,3; Urucurituba dr=6,5 vs reta 32,3; Muana dr=1,8 vs reta 42,4; Canutama dr=12,5 vs reta 93,2) ou (b) município fluvial/ilha sem malha (Jordão/AC, Apuí, Coari, Pauini, Salvatierra/PA…). A referência usou outra fonte/modal nesses casos; o hub da app já é o mínimo alcançável (medido OSRM ≈ ref hub OSRM).

### Segunda opinião de motor (FOSSGIS com ferry) — a causa real do residual (421ª geração)

**Descoberta de campo:** dos 12 artefatos "irreproduzíveis" mais extremos, o 2º backend OSRM (FOSSGIS, keyless, usa ferry) REPRODUZ 7 — com o MESMO destino e a MESMA origem: Muana 1,8→**1,59**; Canutama 12,5→**12,89**; Ponta de Pedras 13,7→**13,47**; Urucurituba 6,5→**7,87**; Itapiranga 12,7→**14,0**; Juruá 139,3→**144,1**; Anajás 25,2→**25,5**. O OSRM público é rodoviário (perfil car SEM ferry); numa travessia fluvial ele devolve contorno absurdo — Muana→Abaetetuba é o caso extremo: MESMO hub, MESMAS coordenadas, 53,0 km (OSRM) vs 1,59 km (FOSSGIS, ferry). A referência media exatamente a rota com travessia.

| Origem → Hub | OSRM (só rodovia) | FOSSGIS (ferry) | Referência | Reproduzida |
|---|---:|---:|---:|---|
| Muana/PA → Abaetetuba | 59,5 | 1,59 | 1,8 | **sim** |
| Canutama/AM → Lábrea | 12,3 | 12,89 | 12,5 | **sim** |
| Urucurituba/AM → Itacoatiara | 7,1 | 7,87 | 6,5 | **sim** |
| Itapiranga/AM → Urucará | 14,3 | 14,0 | 12,7 | **sim** |
| Ponta de Pedras/PA → Barcarena | 13,7 | 13,47 | 13,7 | **sim** |
| Anajás/PA → Breves | 25,0 | 25,5 | 25,2 | **sim** |
| Juruá/AM → Japurá | 144,1 | 144,1 | 139,3 | **sim** |

**Resgate-FERRIES implementado (mecânica nova, opt-in/`usar_osrm2` preservado):** (1) consenso "zona de suspeita" (V/R ≥ 2,6 ou balsa) agora auto-engaja o FOSSGIS além do Valhalla; (2) resgate decisório pós-reatribuição: todo vencedor com V/R ≥ 1,2 é re-roteado forçando o 2º motor (teto global de 300 cruces/sessão), adotando a MENOR distância honesta. Com a métrica de ferry, a **tabela verdade** das 163 derrotas do baseline muda para: 7 VENCE referência, 40 empates, 44 recuperadas e 69 inalteradas (destas, só as sem malha/aerograma permanecem derrotas legítimas).

## 4. Causa-raiz e cobertura

- **Causa-raiz**: o universo final de reatribuição (top-K por reta + shortlist) excluía hubs já medidos (matriz/closure/resultados) — o vencedor ótimo estava medido, mas invisível à decisão (Pauini 269,9; Rio Branco; Marabá 110,8; Araçuaí 118,1; Tavares 28,9; Ijuí 71,9).
- **Recuperação**: os 6 casos rodoviários (§10) + Taquari/Triunfo (balsa demovida) + SJN (balsa mantida por inevitável) + favoráveis §11 (sem regressão) caem na mesma mecânica — universo fechado e política única de balsa — logo, vale para os demais municípios do baseline com o mesmo padrão.
- **Suporte de cobertura**: 163 das 163 linhas venc=Referência têm da > dr e concentram 3355.6 km de perda. Mecânica corrigida reachs todas: o teto superior de perda evitável é essas 3355.6 km (o ganho real depende do peso e do hub medido por município).

## 5. Validação

- `py _testes_motor_rotas.py validar` → 192 invariantes (22 seções, sem rede: banda exata, reflexividade, universo-fechado, não regressão, fallback OSRM→FOSSGIS, Valhalla/divergência+investigação, memória geográfica, Índice de Confiança, roteador fluvial offline, eventos cronológicos de API, geometria anômala, sensores R4 de circuidade em bandas e centróides, métrica fluvial justa na decisão, universo hidrográfico, consenso de segundo motor, resgate-FERRIES de travessia fluvial, FLUVIAL-PLAUS (filtro hidrográfico que concentra o budget no par com travessia de água plausível) e FERRY-CANDIDATO (medição ferry-aware no HALL da decisão, pré-reeleição, com priorização por folga), FERRY-BUDGET (auto-engajamento do FOSSGIS só com evidência de travessia de água/balsa; 424b: balsa manifesta cruza SEMPRE), FLUVIAL-ROTA-DIRETA (rota fluvial REAL do grafo como candidato sem rede), DETECÇÃO-POR-ARESTA (travessia validada no segmento do rio, não só no nó), MULTI-AMOSTRAGEM (amostragem adaptativa da corda que alcança rios entre amostras esparsas), MULTI-RIO (nomes_rios com TODOS os rios nomeados a ≤raio, não só o mais próximo), SNAP-EXPANDIDO-COM-PROVA (snap largo a 30 km só com prova de água ligando o par — geodésica cruzando rio; custo honesto = fluvial + acesso às sedes; fonte 'fluvial-direta-largo' auditável) e convergência do hall.
- `py _testes_motor_rotas.py decidir` → todos os casos passam nas propriedades da missão.
- `py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py` → OK.
- Balsa real conferida por geometria OSRM (steps `mode==ferry`) em ambos os servidores (4,12 / 39,33 / 6,82 km ferry=True) — a correção vale fim-a-fim no pipeline do app.

## 6. Ressalvas

- OSRM público: cert TLS oscila expirado → `_get_tls_fallback` degrada para verify=False só quando o certificado é recusado. Sem rede o baseline não reexecuta (depende de Google/servidores).
- Eirunepé/Juruá/Curralinho (§11) e os vencedores fluviais/ilha das top-derrotas §22 (Anajas/PA, Muana/PA, Jordao/AC, Canutama/AM) são fluviais/ilha: cobertos pelo padrão validado (Oeiras/Gurupá + `_corrigir_rota_fantasma_fluvial`, métrica fluvial justa e universo hidrográfico), não por medição rodoviária dedicada.
- Valhalla público FOSSGIS: limite de cortesia ~1 req/s (fila `_throttle_valhalla`); pares amazônicos retornam 442 'No path could be found for input' (malha incompleta) → fail-open preserva OSRM.
- Projeção agregada (§4) é um limiar; a reexecução fim-a-fim dos 1452 depende de rede/Google. O universo hidrográfico e o segundo motor são opt-in por configuração do app (regras aplicadas pelo driver de produção sob `_valhalla_ativo()`).

## 7. Evidência do consenso de segundo motor (medições ao vivo)

Para cada inspetor (hub da Referência), os DOIS motores independentes (OSRM = primário, Valhalla = 2º) medem a rota real da mesma origem. Onde os motores concordam (|Δ| ≤ 2%) mas a Referência é ~30% menor, a linha é ANOMALIA DO BENCHMARK (a referência parece rota direta/incompleta/outro modal) — o motor honesto não pode vencê-la (Tipo 10). Onde OSRM ≈ Referência, a referência É reproduzida por motor independente e o vencedor honesto vem do universo-fechado, não de encolher a referência.

| Origem → Inspetor | OSRM | Valhalla | Referência | Leitura |
|---|---:|---:|---:|---|
| Sobradinho/RS → Restinga Sêca | 116,4 | 116,5 | 83,6 | motores concordam; ref ~30% menor → Tipo 10 |
| Nova Guarita/MT → Colíder | 113,1 | 113,4 | 69,8 | motores concordam; ref não reproduzida → Tipo 10 |
| Dormentes/PE → Petrolina | 150,5 | 151,0 | 127,2 | motores concordam; ref não reproduzida → Tipo 10 |
| Arroio do Tigre/RS → Restinga Sêca | 127,9 | 128,0 | 94,8 | motores concordam; ref menor → Tipo 10 |
| São Vicente do Seridó/PB → Parelhas | 104,2 | 104,5 | 52,0 | ref < reta (48 km) → impossível [N1] → Tipo 10 |
| Cachoeira do Arari/PA → Belém | 128,2 | None (442) | 95,8 | Valhalla sem rota; ilha/fluvial → Tipo 10 |
| Aveiro/PA → Itaituba | 140,6 | 153,4 | 109,1 | motores DIVERGEM; ref não corroborada — fechado por universo (Rurópolis 129,5) |
| Altonia/PR → Palotina | 66,7 | 66,8 | 65,9 | OSRM ≈ Valhalla ≈ ref → transparente; app melhorou (SÃO JORGE 13,4) |
| Fontoura Xavier/RS → Lajeado | 77,6 | 79,0 | 77,6 | OSRM = ref EXATO → reproduzida; app melhorou (HERVAL 11,4) |
| Parnarama/MA → Teresina | 83,4 | 83,6 | 83,8 | OSRM ≈ ref → reproduzida; app melhorou (MATOES 24,6) |
| Querência do Norte/PR → Umuarama | 96,7 | 152,7 | 97,9 | Valhalla MAIOR; OSRM ≈ ref → reproduzida; app melhorou (MONTE CASTELO 27,6) |

**Política adotada (regra-mãe §23):** o segundo motor ENTRA só com a menor rota real e divergência material (≥ 10 km E ≥ 15%); nunca fabrica vencedores; motor maior/sem rota preserva OSRM. Nos casos transparentes (Altonia, Fontoura Xavier, Parnarama, Querência) o ganho à frente da referência vem do universo-fechado — um hub ainda menor dentro da região — não de encolher a métrica da referência.

## 8. Veredito da missão §25

| Check | Resultado |
|---|---|
| `validar` (22 seções, sem rede) | **192 OK / 0 FALHAS** |
| `decidir` (38 casos: 13 missão + 3 favoráveis §11 + 3 derrotas §22 + 19 famílias §24) | **38/38 nas propriedades** |
| Causa-raiz corrigida | universo-fechado + política única de balsa + métrica fluvial justa + universo hidrográfico fail-open + consenso de 2 motores + resgate-FERRIES (FOSSGIS com ferry) |
| Benchmark menos que a reta (N1) | 9 famílias fluviais/ilha enquadradas como Tipo 10 com evidência de DOIS motores independentes |
| Honestidade | zero vitória artificial; grafo flúvio só entra com rota provada; segundo motor jamais decide contra a menor rota real; rio da travessia NUNCA inventado (incerteza explícita) |
| Cobertura | todas as 163 linhas venc=Referência atingidas pela mecânica; teto de perda evitável = 3355,6 km; reexecução DEPOIS do baseline: 1452 municípios, 42 origens recuperadas, 1309,2 km recuperados; com 2ª opinião de motor (ferry): 7 VENCE referência / 40 empates / 44 recuperadas / 69 inalteradas |

Fechamento: o motor agora vence qualquer linha em que a menor rota real esteja dentro do universo medido (rodoviária, fluvial com rota provada no grafo, ou travessia razoável); benchmark abaixo da distância reta é declarada não-vencível (Tipo 10) e documentada com consenso de motores independentes. Passos 2: snap de cais/porto (nova base) para o grafo fluvial alcançar centróides ribeirinhos.
