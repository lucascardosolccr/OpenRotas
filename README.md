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
| **Suíte pytest** | `python3 -m pytest -q` | **435 passed** |
| **Smoke E2E da UI** | `python3 -m pytest test_smoke_painel.py` | Painel Estratégico + fragmentos renderizam **sem exceção** |

O **smoke test end-to-end** (`test_smoke_painel.py`) sobe o app real na engine do Streamlit (`AppTest`) — autentica, injeta um estudo sintético, navega até o Painel Estratégico e confere que o painel inteiro (incluindo o `@st.fragment` e o fragmento aninhado do Data Explorer) renderiza sem exceção. É a única camada que pega erros no **caminho de render** (uso indevido de `st.*`, coluna quebrada, um fragmento que deixou de executar) que os testes de função pura não alcançam. Roda em **subprocesso isolado** para ficar imune ao estado global do Streamlit poluído por outros arquivos da suíte.

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
Quando a planilha traz a **coluna de candidatos/inscritos** por município, a aplicação gera um **estudo analítico ponderado pelo número de candidatos** — não pelo número de municípios —, revelando o **impacto humano real** do deslocamento. Métricas: **candidato-km total** e **candidato-hora total**, **tempo médio/mediano ponderado por candidato**, **deslocamento médio ponderado** (vs. média simples), **quantis ponderados P25/mediana/P75/P90/P95** e a **faixa central (P25–P75)**, **candidatos em deslocamento longo** (limiar configurável), **distribuição por faixas de distância** (com mini-barras no HTML) e **recortes por UF**. Traz três lentes de política pública: **equidade de acesso** — a **iniquidade P95÷mediana** (quantas vezes os 5% mais distantes percorrem em relação à mediana); **exposição operacional** — recortes por **balsa**, por **risco alto/crítico** e a **dupla exposição** (candidatos que enfrentam balsa **e** risco na mesma rota, o público prioritário para contingência); e **concentração** — **coeficiente de Gini** do candidato-km, análise de **Pareto** (quantos municípios concentram 50% e 80% de toda a carga) e a **curva de Lorenz por decil** de municípios, além dos **municípios de maior peso** com **% acumulado**. Presente no **relatório HTML** (seção própria com KPIs, narrativa, barras e tabelas), na **planilha** (abas *Impacto Candidatos*, *Impacto por Faixa*, *Impacto por UF*, *Impacto Top Municipios* e *Impacto Concentracao*) e **na tela** (métricas, gráficos e abas, incluindo *Concentração/Pareto*). **Fail-open e aditivo**: só aparece quando há a coluna de candidatos, nunca inventa números.

### Perfil Estatístico do Município (IBGE Censo 2022)
Aproveitamento máximo da API já usada do IBGE: além de `/localidades` e `/malhas`, o **Explorador Global** passa a consultar sob demanda a **API v3 de Agregados** (agregado 4714, Censo 2022) e mostra **população**, **densidade demográfica** e **área territorial** (derivada exata: `área = população ÷ densidade`) quando o filtro isola um único município. Cacheado 7 dias, **fail-open** (se a API não responder, o cartão só não aparece) e **nunca inventa** — só números oficiais. Fonte gratuita, sem chave e sem cota.

### Conta do Usuário
Login por **e-mail/senha** e **Google** (OAuth PKCE, Supabase Auth); perfil com isolamento por usuário (**RLS**), política de senha reforçada, **estudos salvos** persistentes (atrelados à conta), foto de perfil e anotações. Ver `auth/`.

**Sessão que não cai à toa.** A sessão é renovada silenciosamente pelo `refresh_token` e a revalidação periódica **nunca desloga por soluço de rede** — só encerra numa rejeição *definitiva* do token (revogado/expirado); falha transitória (rede/servidor 5xx/timeout) mantém o login e revalida em ~45 s. Além disso, os tokens podem ser guardados na **`sessionStorage` do navegador** (`auth/browser_session.py`), então um **F5 ou reconexão com a aba aberta reidrata a sessão** em vez de exigir novo login; ao fechar a aba/navegador a `sessionStorage` some (efêmera, mais segura que cookie — não vai a servidor nenhum). Tudo **fail-open** e com **kill-switch** (`PERSISTIR_SESSAO_NAVEGADOR = "false"` em `st.secrets` desliga na hora).

**Consentimento LGPD (opt-in e revogável).** Essa persistência é **opcional e só acontece com o consentimento do usuário** (`auth/consent.py`, Lei 13.709/2018): ao entrar, um **banner** explica — sem juridiquês — o que se guarda, por quê, por quanto tempo e como revogar (Art. 9), e a persistência **só liga se o usuário aceitar** (base legal: consentimento, Art. 7, I). Enquanto não decide, **nada é guardado**. A decisão fica num **cookie próprio** de 12 meses (`openrotas_consent_v1`, lido nativamente por `st.context.cookies`, sem round-trip) e pode ser **alterada/revogada a qualquer momento** em **Perfil → Privacidade** (Art. 8, §5) — revogar apaga o token guardado. **Sem rastreamento/publicidade e sem compartilhamento com terceiros**; os cookies técnicos do Streamlit (sessão da aplicação) são estritamente necessários e apenas informados.

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