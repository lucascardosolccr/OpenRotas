# Motor Nacional de Inteligência Logística para Exames

> **Sistema de roteamento inteligente para alocação de candidatos a exames**  
> Combina dados oficiais brasileiros (IBGE, ANA/SNIRH, DNIT, ANTAQ, ANTT) para encontrar a **menor rota válida e operacionalmente benéfica** entre município de origem e polo de destino.

> **Status:** ✅ Produção — Gates: 239 OK / 0 FALHAS | `decidir` 38/38 | `relatorio` 203 linhas  
> **Versão:** geração 447 (selo interno `_VERSAO_APP`) | **Branch:** `main`

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
| | Agregados — Censo 2022 (pop./densidade/área) | 5.570 | ✅ API v3 (gratuita, sem chave) |
| **Rodoviária** | OSRM/FOSSGIS/Valhalla/GraphHopper | Tempo real | ✅ API |
| **OSRM** | Principais vias/rodovias (BR/estaduais) | Por trecho (steps) | ✅ keyless |
| **GraphHopper** | Perfil de vias (pavimento/classe/balsa) | Por trecho | ✅ path details |
| **SNIRH/ANA HidroWeb** | Séries (cotas/vazões/chuvas) | Estatística + gráfico | ✅ API v1 |

---

## 🚀 Quick Start

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Compilar e validar
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py

# 3. Testes completos (239 testes)
py -X utf8 _testes_motor_rotas.py validar
# ✅ 239 OK / 0 FALHAS

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
| **Testes unitários** | `py -X utf8 _testes_motor_rotas.py validar` | **239 OK / 0 FALHAS** |
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

### Reconhecimento de Endereços (100% Gratuito)
Somente fontes **gratuitas, sem chave e sem cota**: base oficial do **IBGE** (municípios/sedes, O(1)) + geocoders **ArcGIS · Nominatim · Photon** em consenso, e cascata de **CEP** (**BrasilAPI · ViaCEP · OpenCEP · Postmon · Nominatim**). Pré-processamento com **expansão de abreviações** (Av./R./Estr./Pres./Dr./Eng.…, com blindagem das 27 UFs) e **geocodificação estruturada do CEP** (endpoints por campo + número da casa). Cada geocoder agora expõe o **sinal de precisão do casamento** que antes era descartado — `Addr_type` do ArcGIS (rooftop → via com número → via → aproximado), `type/class` do OSM — traduzido num **rótulo de precisão auditável** exibido na explicabilidade (sem alterar a pontuação de consenso calibrada).

### Auditoria Física da Distância da Referência (Comparador)
Na comparação com o estudo de referência, a aplicação **aponta e explica** quando a distância da referência é **fisicamente impossível**: se ela for **menor que a linha reta geodésica** (WGS-84) entre origem e destino — o piso físico absoluto —, está **comprovadamente errada** (nenhuma estrada é mais curta que o voo de pássaro). Cada caso vem com explicação quantificada (km e % abaixo do piso, causas prováveis) e corroboração da rota viária real medida pela app. Presente na **planilha** (colunas na aba *Comparacao* + aba dedicada *Distancias Impossiveis Ref*) e no **relatório HTML** (seção própria). Um segundo veredito, *implausível*, sinaliza distâncias "retas demais para ser estrada" (fator < 1,05× a geodésica).

### Estudo de Impacto nos Candidatos (Processamento em Lote)
Quando a planilha traz a **coluna de candidatos/inscritos** por município, a aplicação gera um **estudo analítico ponderado pelo número de candidatos** — não pelo número de municípios —, revelando o **impacto humano real** do deslocamento. Métricas: **candidato-km total** e **candidato-hora total**, **deslocamento médio ponderado** (vs. média simples), **mediana/P90/P95 ponderados**, **candidatos em deslocamento longo** (limiar configurável), **distribuição por faixas de distância**, **recortes por balsa e por risco operacional** (quantos candidatos atravessam travessia fluvial ou rota crítica) e **por UF**, além dos **municípios de maior peso**. A **concentração** é medida por **coeficiente de Gini** do candidato-km e pela **fatia dos 10% de municípios de maior carga**. Presente no **relatório HTML** (seção própria com KPIs, narrativa e tabelas) e na **planilha** (abas *Impacto Candidatos*, *Impacto por Faixa*, *Impacto por UF* e *Impacto Top Municipios*). **Fail-open e aditivo**: só aparece quando há a coluna de candidatos, nunca inventa números.

### Perfil Estatístico do Município (IBGE Censo 2022)
Aproveitamento máximo da API já usada do IBGE: além de `/localidades` e `/malhas`, o **Explorador Global** passa a consultar sob demanda a **API v3 de Agregados** (agregado 4714, Censo 2022) e mostra **população**, **densidade demográfica** e **área territorial** (derivada exata: `área = população ÷ densidade`) quando o filtro isola um único município. Cacheado 7 dias, **fail-open** (se a API não responder, o cartão só não aparece) e **nunca inventa** — só números oficiais. Fonte gratuita, sem chave e sem cota.

### Conta do Usuário
Login por **e-mail/senha** e **Google** (OAuth PKCE, Supabase Auth); perfil com isolamento por usuário (**RLS**), política de senha reforçada, **estudos salvos** persistentes (atrelados à conta), foto de perfil e anotações. Ver `auth/`.

### Compartilhamento de Estudos entre Perfis
Um estudo salvo pode ser **compartilhado com outro perfil pelo e-mail** do destinatário — que passa a **ver e baixar** o estudo (abrir na aplicação ou exportar CSV) na seção **📥 Estudos recebidos**. Tudo sob **RLS** (sem `service_role`): o dono nunca precisa descobrir o id do outro usuário (casa-se por e-mail); uma tabela `estudos_compartilhados` liga o estudo ao e-mail e uma policy de SELECT adicional em `estudos_salvos` libera a leitura só para o destinatário certo. O dono vê com quem compartilhou e pode **revogar** a qualquer momento. **Notificações:** ao receber um estudo, o destinatário vê um **badge 📥 no botão Perfil** (quantos há de novo) e recebe um **e-mail** de aviso (mesmo relay SMTP do cadastro; best-effort, nunca bloqueia). O badge zera quando ele abre a seção (marca-se a data no próprio perfil).

---

## 📊 Resultados Alcançados

| Métrica | Baseline | Final (baseline geração 436) | Δ |
|---------|----------|-------------|---|
| **Derrotas Reference** | 109 | **~88** | **−21** |
| **Aplicação** | 23 | **~43** | **+20** |
| **Empate** | 31 | **~32** | **+1** |
| **km Total** | 10.976 | **~10.700** | **−276 km** |
| **Capturas Fluviais** | 0 | **21** | **+21** |
| **Grafo Nós** | 1.216M | **1.467M** | **+251K** |
| **Grafo Arestas** | 1.223M | **1.724M** | **+501K** |

**Gates:** ✅ 239 OK / 0 FALHAS | `decidir` 38/38 | `relatorio` 203 linhas

---

## 📁 Estrutura do Projeto

```
new_rotas-main/
├── streamlit_app.py              # Código principal (~60k linhas)
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
py -X utf8 _testes_motor_rotas.py validar    # 239 OK / 0 FALHAS
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
| **Testes unitários (239)** | ✅ 239 OK / 0 FALHAS |
| **Decisão real (38 casos)** | ✅ 38/38 pass |
| **Relatório comparativo** | ✅ 203 linhas |
| **Zero regressão** | ✅ Garantido por arquitetura aditiva |

---

## 📈 Roadmap

| Prioridade | Item | Status |
|------------|------|--------|
| **Infraestrutura** | Brazil OSM PBF + osmium/GDAL | ⏳ Windows env sem GDAL |
| **Infraestrutura** | Self-hosted Valhalla multi-modal | ⏳ Docker + Brazil PBF |
| **Dados** | BC250/BC100 Shapefiles completos | ✅ `data/brasil/ibge/` (1.6GB, 71 camadas BC250 + BC100 por UF) |
| **Dados** | Camadas derivadas IBGE (Parquet local) | ✅ 12 camadas em `data/brasil/ibge/derivadas/` + `bases_locais.py` (pontes, balsas, hidrovias, eclusas, rodovias, drenagem, municípios) |
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
- **Selo interno atual:** geração 447 (`_VERSAO_APP`)

---

> **Última atualização:** 2026-09-14 | **Selo interno:** geração 447