# Motor Nacional de Inteligência Logística para Exames

> **Sistema de roteamento inteligente para alocação de candidatos a exames**  
> Combina dados oficiais brasileiros (IBGE, ANA/SNIRH, DNIT, ANTAQ, ANTT) para encontrar a **menor rota válida e operacionalmente benéfica** entre município de origem e polo de destino.

> **Status:** ✅ Produção — Gates: 192 OK / 0 FALHAS | `decidir` 38/38 | `relatorio` 203 linhas  
> **Versão:** 4.36 (Build 436) | **Branch:** `main` | **Commit:** `c75eb1c`

---

## 🎯 Objetivo

Transformar a aplicação em um motor de roteamento **geograficamente consciente**, capaz de combinar dados oficiais brasileiros (IBGE, ANA/SNIRH, DNIT, ANTAQ, ANTT, IBGE, OSRM, FOSSGIS, Valhalla) para encontrar a **menor rota válida e operacionalmente benéfica** entre município de origem e polo de destino.

> **Princípio Central:** *"Quanto mais dados oficiais brasileiros confiáveis puderem ajudar a aplicação a compreender a realidade territorial, rodoviária, hidrográfica e de transporte do Brasil, mais dessas informações devem ser pesquisadas, avaliadas e, quando comprovadamente úteis, incorporadas ao sistema."*

---

## 🏗️ Arquitetura

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

---

## 📊 Dados Oficiais Integrados

| Fonte | Dataset | Registros | Status |
|-------|---------|-----------|--------|
| **SNIRH/ANA HidroWeb REST** | Estações | 40.745 | ✅ API HAL+JSON |
| | Telemétricas | 6.803 | ✅ |
| | Rios | 14.135 | ✅ |
| | Bacias | 9 + 84 sub | ✅ |
| | Municípios | 5.714 | ✅ |
| | Estados | 39 | ✅ |
| **IBGE** | BC250/BC100/BCIM | 1.46M nós | ✅ Shapefile/GPKG/PostGIS |
| | Malhas Municipais 2025 | 5.570 | ✅ |
| **Rodoviária** | OSRM/FOSSGIS/Valhalla | Tempo real | ✅ API |

---

## 🚀 Quick Start

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Compilar e validar
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py

# 3. Testes completos (192 testes)
py -X utf8 _testes_motor_rotas.py validar
# ✅ 192 OK / 0 FALHAS

# 4. Decisão real (38 casos críticos)
py -X utf8 _testes_motor_rotas.py decidir

# 5. Relatório comparativo
py -X utf8 _testes_motor_rotas.py relatorio

# 6. Executar aplicação
streamlit run streamlit_app.py
# Acesse: http://localhost:8501
```

---

## 🧪 Gates de Qualidade

| Gate | Comando | Critério de Sucesso |
|-----|---------|---------------------|
| **Compilação** | `py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py` | Sem erros |
| **Testes unitários** | `py -X utf8 _testes_motor_rotas.py validar` | **192 OK / 0 FALHAS** |
| **Decisão real** | `py -X utf8 _testes_motor_rotas.py decidir` | **38/38 pass** |
| **Relatório** | `py -X utf8 _testes_motor_rotas.py relatorio` | 203 linhas |

---

## 🏗️ Funcionalidades Principais

### Roteamento Multimodal
- **Rodoviário:** OSRM público → fallback automático FOSSGIS (usa ferry)
- **Aquaviário:** Grafo fluvial nacional (1.46M nós, 1.72M arestas) + Dijkstra on-demand
- **Multi-hop:** Roteamento com transbordos em 450 confluências mapeadas
- **Valhalla:** 3ª perna de consenso para casos suspeitos (V/R ≥ 2.6 ou balsa ≥ 2.0)

### Inteligência de Travessias (Balsas)
| Feature | Descrição |
|---------|-----------|
| **Detecção** | `_capturar_travessias_osrm` extrai steps `ferry` do OSRM |
| **Identificação** | `_nome_rio_na_travessia` cruza com grafo hidrográfico (cKDTree + `edic`) |
| **Multi-Rio** | `nomes_rios` lista TODOS os rios no raio (foz/confluência) |
| **Rotulagem** | `Travessia por balsa — Rio X (N travessias)` |

### Fluvial Inteligente (Geração 435)
| Função | Descrição |
|--------|-----------|
| `_rio_e_navegavel()` | 80+ rios navegáveis + heurísticas (confiança 0-100) |
| `_rio_tem_obstrucao()` | 50+ barragens + 12 cachoeiras (bloqueio total) |
| `_calcular_score_navegabilidade()` | Score 0-100 (distância, obstruções, confiança) |
| `_fluvial_custo_com_navegabilidade()` | Custo efetivo = km × fator_penalidade (1.0-2.0) |

### Fluvial Advanced Routing (Geração 434)
| Feature | Descrição |
|---------|-----------|
| **Componentes Conexos** | 1.171 componentes (1.2M nós no principal) via BFS |
| **Confluências** | 450 nós grau ≥3 com rios diferentes |
| **Multi-Hop** | Sede → Rio A → Confluência → Rio B → ... → Sede |
| **Densidade Adaptativa** | Raio 50-500km baseado em densidade hidrográfica |
| **Sweep Otimizado** | Raio 300km, multi-hop nativo, prioridade por componente/confluência |

---

## 📊 Resultados Alcançados

| Métrica | Baseline | Final (436) | Δ |
|---------|----------|-------------|---|
| **Derrotas Reference** | 109 | **~88** | **−21** |
| **Aplicação** | 23 | **~43** | **+20** |
| **Empate** | 31 | **~32** | **+1** |
| **km Total** | 10.976 | **~10.700** | **−276 km** |
| **Capturas Fluviais** | 0 | **21** | **+21** |
| **Grafo Nós** | 1.216M | **1.467M** | **+251K** |
| **Grafo Arestas** | 1.223M | **1.724M** | **+501K** |

**Gates:** ✅ 192 OK / 0 FALHAS | `decidir` 38/38 | `relatorio` 203 linhas

---

## 📁 Estrutura do Projeto

```
new_rotas-main/
├── streamlit_app.py              # Código principal (~54k linhas)
├── _testes_motor_rotas.py        # Testes + relatório + decisão
├── _REGISTRO_DERROTAS.md         # Registro histórico (890 linhas)
├── _RELATORIO_ANTES_DEPOIS.md    # Relatório comparativo (203 linhas)
├── HANDBOOK.md                   # Documentação técnica completa
├── MANUAL_USUARIO.md             # Manual do usuário
├── requirements.txt              # Dependências (auditado)
├── snirh_estacaos.csv            # 40.745 estações
├── snirh_telemetricas.csv        # 6.803 telemétricas
├── snirh_rios.csv                # 14.135 rios
├── snirh_bacias.csv              # 9 bacias
├── snirh_subbacias.csv           # 84 sub-bacias
├── snirh_municipios_all.csv      # 5.714 municípios
├── snirh_estados.csv             # 39 estados
├── hidrografia_nacional.pkl.gz   # Grafo fluvial (800MB+)
└── hidrografia_nacional_ne10m.pkl.gz  # Grafo + NE10M
```

---

## 📚 Documentação

| Arquivo | Descrição |
|---------|-----------|
| `HANDBOOK.md` | Documentação técnica completa (arquitetura, APIs, dados, gates) |
| `MANUAL_USUARIO.md` | Manual do usuário (operação, interface, troubleshooting) |
| `_REGISTRO_DERROTAS.md` | Histórico completo de gerações (890 linhas) |
| `_RELATORIO_ANTES_DEPOIS.md` | Relatório comparativo ANTES×DEPOIS |

---

## 🔧 Comandos Úteis

```bash
# Compilação e testes
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py
py -X utf8 _testes_motor_rotas.py validar    # 192 OK / 0 FALHAS
py -X utf8 _testes_motor_rotas.py decidir    # 38/38 pass
py -X utf8 _testes_motor_rotas.py relatorio  # 203 linhas

# Execução
streamlit run streamlit_app.py
# http://localhost:8501
```

---

## 📋 Gates de Qualidade (Zero Regressão)

| Gate | Status |
|------|--------|
| **Compilação** | ✅ |
| **Testes unitários (192)** | ✅ 192 OK / 0 FALHAS |
| **Decisão real (38 casos)** | ✅ 38/38 pass |
| **Relatório comparativo** | ✅ 203 linhas |
| **Zero regressão** | ✅ Garantido por arquitetura aditiva |

---

## 📈 Roadmap

| Prioridade | Item | Status |
|------------|------|--------|
| **Infraestrutura** | Brazil OSM PBF + osmium/GDAL | ⏳ Windows env sem GDAL |
| **Infraestrutura** | Self-hosted Valhalla multi-modal | ⏳ Docker + Brazil PBF |
| **Dados** | BC250/BC100 Shapefiles completos | ⚠️ Download 1.6GB+ |
| **Infraestrutura** | Self-hosted Valhalla multi-modal | ⏳ Docker + Brazil PBF |
| **Infraestrutura** | FOSSGIS budget increase | ⚠️ 300/sessão limitante |
| **Dados** | PRF/Defesa Civil/CEMADEN APIs | 🔴 Pendente |
| **Dados** | INPE/CPTEC/INMET/CEMADEN | 🔴 Pendente |

---

## 📜 Licença

Uso interno — Dados oficiais brasileiros (domínio público / licenças abertas).

---

## 📞 Contato

- **Repositório:** https://github.com/lucascardosolccr/OpenRotas
- **Branch:** `main` (protegida)
- **Último deploy:** `c75eb1c` — feat(aquaviaria 436)

---

> **Última atualização:** 2026-09-06 | **Versão:** 4.36 | **Build:** 436