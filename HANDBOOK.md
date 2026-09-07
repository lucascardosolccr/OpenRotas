# HANDBOOK — Motor Nacional de Inteligência Logística para Exames
## Manual do Usuário e Documentação Técnica Completa

> **Versão:** 4.36 (Build 436)  
> **Data:** 2026-09-06  
> **Status:** ✅ Produção — Gates: 192 OK / 0 FALHAS | `decidir` 38/38 | `relatorio` 203 linhas  
> **Branch:** `main` → `origin/main` (up to date)  
> **Commit:** `c75eb1c` — feat(aquaviaria 436)

---

## 1. VISÃO GERAL

O **Motor Nacional de Inteligência Logística para Exames** é um sistema de roteamento inteligente para alocação de candidatos a exames, capaz de combinar dados oficiais brasileiros (IBGE, ANA/SNIRH, DNIT, ANTAQ, ANTT, IBGE, OSRM, FOSSGIS, Valhalla) para encontrar a **menor rota válida e operacionalmente benéfica** entre município de origem e polo de destino.

### Princípio Central
> **"Quanto mais dados oficiais brasileiros confiáveis puderem ajudar a aplicação a compreender a realidade territorial, rodoviária, hidrográfica e de transporte do Brasil, mais dessas informações devem ser pesquisadas, avaliadas e, quando comprovadamente úteis, incorporadas ao sistema."**

---

## 2. ARQUITETURA DO SISTEMA

```
MOTOR DE ROTEAMENTO
         │
    ┌────┴────┐
    │ CAMADA GEOESPACIAL │
    └────┬────┘
         │
┌────────┼────────┐
│        │        │
IBGE     ANA      DNIT
│        │        │
Municípios Rios   Rodovias
Limites  Bacias   Pontes
Localidades Hidrologia Pavimento
         │        │
         └────┬───┘
              │
          ANTAQ
              │
       Hidrovias/Balsas
              │
          ANTT/DER
              │
       Rodovias/Concessões
              │
              ▼
    INTELIGÊNCIA DE ROTA
```

### Camadas de Dados

| Camada | Fonte | Atualização | Formato |
|--------|-------|-------------|---------|
| **Territorial** | IBGE (Malhas 2025, BC250/BC100/BCIM) | Anual | Shapefile, GeoPackage, PostGIS |
| **Hidrográfica** | ANA/SNIRH HidroWeb REST | Tempo real | HAL+JSON API |
| **Rodoviária** | DNIT/ANTT/OSRM/FOSSGIS/Valhalla | Tempo real | OSRM/Valhalla API |
| **Aquaviária** | ANTAQ/SNIRH + IBGE BC250 | Trimestral | Shapefile/GeoPackage |
| **Municipal** | IBGE + SNIRH | Anual | CSV/API |

---

## 3. FUNCIONALIDADES PRINCIPAIS

### 3.1 Roteamento Multimodal
- **Rodoviário:** OSRM público → fallback automático FOSSGIS (usa ferry)
- **Aquaviário:** Grafo fluvial nacional (1.46M nós, 1.72M arestas) + Dijkstra on-demand
- **Multi-hop:** Roteamento com transbordos em confluências (450 confluências mapeadas)
- **Valhalla:** 3ª perna de consenso para casos suspeitos (V/R ≥ 2.6 ou balsa ≥ 2.0)

### 3.2 Inteligência de Travessias (Balsas)
| Feature | Descrição |
|---------|-----------|
| **Detecção** | `_capturar_travessias_osrm` extrai steps `ferry` do OSRM |
| **Identificação** | `_nome_rio_na_travessia` cruza com grafo hidrográfico (cKDTree + `edic`) |
| **Multi-Rio** | `nomes_rios` lista TODOS os rios no raio (foz/confluência) |
| **Rotulagem** | `Travessia por balsa — Rio X (N travessias)` |

### 3.3 Fluvial Inteligente (Geração 435)
| Função | Descrição |
|--------|-----------|
| `_rio_e_navegavel()` | 80+ rios navegáveis + heurísticas (confiança 0-100) |
| `_rio_tem_obstrucao()` | 50+ barragens + 12 cachoeiras (bloqueio total) |
| `_calcular_score_navegabilidade()` | Score 0-100 (distância, obstruções, confiança) |
| `_fluvial_custo_com_navegabilidade()` | Custo efetivo = km × fator_penalidade (1.0-2.0) |

### 3.4 Fluvial Advanced Routing (Geração 434)
| Feature | Descrição |
|---------|-----------|
| **Componentes Conexos** | 1.171 componentes (1.2M nós no principal) via BFS |
| **Confluências** | 450 nós grau ≥3 com rios diferentes |
| **Multi-Hop** | Sede → Rio A → Confluência → Rio B → ... → Sede |
| **Densidade Adaptativa** | Raio 50-500km baseado em densidade hidrográfica |
| **Sweep Otimizado** | Raio 300km, multi-hop nativo, prioridade por componente/confluência |

---

## 4. DADOS OFICIAIS INTEGRADOS

| Fonte | Dataset | Registros | Status |
|-------|---------|-----------|--------|
| **SNIRH/ANA HidroWeb REST** | Estações | 40.745 | ✅ API HAL+JSON |
| | Telemétricas | 6.803 | ✅ |
| | Rios | 14.135 | ✅ |
| | Bacias | 9 + 84 sub | ✅ |
| | Municípios | 5.714 | ✅ |
| | Estados | 39 | ✅ |
| | Cotas/Vazões/Sedimentos | Milhões | ✅ API |
| **IBGE** | BC250 v2025 | 1.46M nós | ✅ Shapefile/GPKG/PostGIS |
| | BC100 | Por UF | ✅ |
| | Malhas Municipais 2025 | 5.570 | ✅ |
| | BCIM 1:1M | Nacional | ✅ |

### Dados Exportados (CSVs)
```
snirh_estacaos.csv        # 40.745 estações
snirh_telemetricas.csv    # 6.803 estações telemétricas
snirh_rios.csv            # 14.135 rios
snirh_bacias.csv          # 9 bacias
snirh_subbacias.csv       # 84 sub-bacias
snirh_municipios_all.csv  # 5.714 municípios
snirh_estados.csv         # 39 estados
```

---

## 5. GATES DE QUALIDADE

```bash
# Compilação
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py

# Testes unitários (192 testes)
py -X utf8 _testes_motor_rotas.py validar
# RESULTADO: 192 OK / 0 FALHAS

# Decisão real (38 casos críticos)
py -X utf8 _testes_motor_rotas.py decidir
# TODOS OS CASOS PASSARAM

# Relatório comparativo
py -X utf8 _testes_motor_rotas.py relatorio
# _RELATORIO_ANTES_DEPOIS.md → 203 linhas
```

### Seções de Teste (22 seções)
1. Bandas adaptativas
2. Balsa evitável
3. Vantagem banda balsa
4. V316 decidir terrestre
5. Seleção hub multicritério
6. Universo-fechado
7. Bordas exatas da banda
8. Reflexividade comparador
9. Favorável §11 (Dormentes)
10. Fallback OSRM → FOSSGIS
11. Valhalla divergência
12. Memória geográfica
13. Índice de Confiança
14. Roteador fluvial offline
15. Eventos cronológicos API
16. Geometria anômala
17. Valhalla investigação
18. Sensores de risco
19. Métrica fluvial justa
20. Consenso segundo motor
21. Travessia explícita (TRAVESSIA-RIO)
22. Resgate-ferries + Hidrografia (421-432)

---

## 6. FLUXO DE DECISÃO (PIPELINE)

```
ORIGEM + DESTINO
       │
       ▼
┌──────────────────┐
│  GEOCODING (IBGE) │
│  Validação coords │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  TOP-K ADAPTATIVO │
│  (teto 48, sinal  │
│   malha)          │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  MATRIZ COMPETITIVA│
│  OSRM + FOSSGIS   │
│  (ferry-aware)    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  UNIVERSO FECHADO │
│  Fundo shortlist  │
│  + matriz         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  FERRY-CANDIDATO  │
│  (hall fluvial)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  FLUVIAL-ROTA-   │
│  DIRETA (426a)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  FLUVIAL-SWEEP   │
│  OTIMIZADO (434) │
│ Multi-hop + raio │
│ adaptativo       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  REATRIBUIÇÃO    │
│  MULTICRITÉRIO   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  CONSENSO        │
│  SEGUNDO MOTOR   │
│ (Valhalla opt-in)│
└────────┬─────────┘
         │
         ▼
   VENCEDOR FINAL
```

---

## 7. COMANDOS ÚTEIS

```bash
# Compilação
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py

# Testes completos
py -X utf8 _testes_motor_rotas.py validar

# Decisão real (38 casos)
py -X utf8 _testes_motor_rotas.py decidir

# Relatório comparativo
py -X utf8 _testes_motor_rotas.py relatorio

# Execução da aplicação
streamlit run streamlit_app.py
```

### Variáveis de Ambiente Úteis
```bash
export VALHALLA_URL="http://localhost:8002"  # Valhalla self-hosted
export OSRM_URL="http://router.project-osrm.org"  # OSRM público
export FOSSGIS_URL="https://routing.openstreetmap.de/routed-car/route/v1"  # FOSSGIS
```

---

## 8. ESTRUTURA DE ARQUIVOS

```
new_rotas-main/
├── streamlit_app.py              # Código principal (~54k linhas)
├── _testes_motor_rotas.py        # Testes + relatório + decisão
├── _REGISTRO_DERROTAS.md         # Registro histórico (890 linhas)
├── _RELATORIO_ANTES_DEPOIS.md    # Relatório comparativo (203 linhas)
├── requirements.txt              # Dependências
├── HANDBOOK.md                   # Este arquivo
├── _REGISTRO_DERROTAS.md         # Registro histórico (890 linhas)
├── _RELATORIO_ANTES_DEPOIS.md    # Relatório comparativo
├── requirements.txt
├── snirh_estacaos.csv            # 40.745 estações
├── snirh_telemetricas.csv        # 6.803 telemétricas
├── snirh_rios.csv                # 14.135 rios
├── snirh_bacias.csv              # 9 bacias
├── snirh_subbacias.csv           # 84 sub-bacias
├── snirh_municipios_all.csv      # 5.714 municípios
├── snirh_estados.csv             # 39 estados
├── hidrografia_nacional.pkl.gz   # Grafo fluvial (800MB+)
├── hidrografia_nacional_ne10m.pkl.gz  # Grafo + NE10M
├── data/
│   ├── brasil/
│   │   ├── ibge/ (malhas, BC250, BC100)
│   │   ├── ana/ (SNIRH exports)
│   │   ├── antaq/
│   │   ├── dnit/
│   │   └── hidrografia/
└── .streamlit/config.toml
```

---

## 9. COMANDOS DE MANUTENÇÃO

### Atualizar Dados SNIRH
```bash
# Re-fetch all SNIRH data
py -X utf8 -c "
import requests, csv, json, os
# ... (scripts em C:\Users\lucas\AppData\Local\Temp\opencode\fetch_all_snirh.py)
"
```

### Rebuild Grafo Fluvial (após novos shapefiles)
```bash
# Script: construir_grafo_hidrografia_nacional.py
# Requer: GDAL/osmium (não disponível no Windows atual)
# Alternativa: usar IBGE BC250/BC100 Shapefiles baixados manualmente
```

### Rebuild Cache
```bash
# Limpar caches
rm -rf cache_* __pycache__ .streamlit/cache

# Rebuild
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py
py -X utf8 _testes_motor_rotas.py validar
```

---

## 10. TROUBLESHOOTING

### Problemas Comuns

| Sintoma | Causa | Solução |
|---------|-------|---------|
| `ModuleNotFoundError: fiona` | GDAL não instalado | `conda install -c conda-forge fiona gdal` ou use Linux/WSL |
| `OSRM timeout` | Rede/instância | Fallback automático → FOSSGIS |
| `Valhalla não engaja` | `_valhalla_ativo()` = False | Configure `VALHALLA_URL` |
| `hidrografia_nacional.pkl.gz` não carrega | Arquivo corrompido/ausente | Re-download do IBGE BC250 |
| `ModuleNotFoundError: fiona/gdal` | Windows sem GDAL | Use WSL2/Ubuntu ou Docker |

### Logs Importantes
```python
# Monitorar logs de decisão
logger = logging.getLogger("MotorGeodesicoCorp")
logger.setLevel(logging.DEBUG)

# Logs de API
tail -f logs_google/*.log

# Auditoria de rotas
grep "RESGATE-FERRIES\|FLUVIAL-ROTA\|FLUVIAL-SWEEP" logs/*.log
```

---

## 11. ROADMAP / PRÓXIMOS PASSOS

### Imediato (Infraestrutura)
- [ ] **Download BC250/BC100 completos** (1.6GB+ shapefiles IBGE)
- [ ] **Self-hosted Valhalla** (Docker + Brazil PBF 4GB+)
- [ ] **Brazil OSM PBF + osmium** (hidrografia completa OSM)
- [ ] **FOSSGIS self-hosted** (remover limite 300/sessão)

### Curto Prazo (Dados)
- [ ] PRF API (acidentes/bloqueios)
- [ ] Defesa Civil/CEMADEN (enchentes/deslizamentos)
- [ ] CPTEC/INPE/INMET (dados meteorológicos)
- [ ] DNIT SICRO (condições pavimento, obras, tráfego)

### Médio Prazo (Arquitetura)
- [ ] Camada Geoespacial unificada (GeoParquet/DuckDB/SpatiaLite)
- [ ] Cache distribuído (Redis) para rotas frequentes
- [ ] API GraphQL para consulta de rotas/alternativas

---

## 12. CONTATO E SUPORTE

- **Repositório:** https://github.com/lucascardosolccr/OpenRotas
- **Branch:** `main` (protegida)
- **Commits:** 19 gerações (421-436)
- **Último deploy:** `c75eb1c` — feat(aquaviaria 436)

---

> **Última atualização:** 2026-09-06  
> **Próxima revisão:** Após integração de novos datasets (OSM PBF, Valhalla self-hosted, BC250 completo)

---

*Este documento deve ser atualizado a cada nova geração implementada. Consulte `_REGISTRO_DERROTAS.md` para histórico completo e `_RELATORIO_ANTES_DEPOIS.md` para comparações ANTES×DEPOIS.*