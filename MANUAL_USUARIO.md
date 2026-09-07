# MANUAL DO USUÁRIO — Motor de Rotas Inteligente
## Guia Rápido de Operação

> **Versão:** 4.36 | **Público:** Operadores, Analistas, Gestores  
> **Acesso:** `streamlit run streamlit_app.py`

---

## 1. INÍCIO RÁPIDO

### Executar a Aplicação
```bash
streamlit run streamlit_app.py
```
Acesse: `http://localhost:8501`

### Executar Testes
```bash
# Validação completa (192 testes)
py -X utf8 _testes_motor_rotas.py validar

# Decisão real (38 casos críticos)
py -X utf8 _testes_motor_rotas.py decidir

# Relatório comparativo
py -X utf8 _testes_motor_rotas.py relatorio
```

---

## 2. INTERFACE PRINCIPAL

### Abas Principais
| Aba | Função |
|-------|--------|
| **📊 Alocação** | Motor principal de decisão de hubs |
| **📈 Monitor** | Telemetria de APIs, falhas, performance |
| **🗺️ Mapa** | Visualização de rotas, travessias, balsas |
| **📋 Relatório** | Exportação ANTES×DEPOIS, CSV, Excel |

### Painel de Alocação — Colunas Principais
| Coluna | Significado |
|--------|-------------|
| **Origem** | Município de origem do candidato |
| **Destino App** | Hub escolhido pelo motor |
| **Distância App** | km calculados pelo motor |
| **Referência** | Hub do estudo de referência |
| **Dist. Ref** | km do estudo de referência |
| **Vencedor** | App / Referência / Empate |
| **Critério** | Regra que decidiu (ex: "menor distância viária") |
| **Balsa** | Sim/Não + Rio identificado |
| **Índice Confiança** | 0-100 (qualidade da rota) |

---

## 3. COMO INTERPRETAR OS RESULTADOS

### Status de Vencedor
| Status | Significado | Ação |
|--------|-------------|------|
| **Aplicação** | Motor venceu a referência | ✅ OK |
| **Referência** | Estudo de referência venceu | ⚠️ Investigar |
| **Empate** | Diferença ≤ 1 km | ℹ️ Neutro |

### Coluna "Critério" — Códigos
| Código | Significado |
|--------|-------------|
| `menor distância viária` | Rota rodoviária pura venceu |
| `menor custo logístico global (desempate)` | Empate técnico resolvido por custo logístico |
| `balsa demovida (§7)` | Balsa removida por política de banda |
| `família FLUVIAL/nome-igual` | Rota fluvial identificada (mesmo nome) |
| `família §24 (derrota real medida ao vivo)` | Medição ao vivo FOSSGIS |
| `rota fluvial real` | Rota aquaviária do grafo nacional |

### Índice de Confiança (0-100)
| Faixa | Interpretação |
|-------|---------------|
| 90-100 | Rota real, direta, sem balsa/divergência |
| 70-89 | Boa, pequena incerteza |
| 50-69 | Moderada, geodésica/estimada |
| 30-49 | Baixa, rota impossível ou alta incerteza |
| <30 | Mínima, rota impossível (viária < reta) |

---

## 4. FUNCIONALIDADES AVANÇADAS

### 4.1 Travessias e Balsas
Quando aparecer **"Balsa: Sim"**, clique na linha para ver:
- **Rio identificado** (ex: "Rio Amazonas", "Rio Paraná")
- **Bacia hidrográfica**
- **Distância hidrovia** (km por água)
- **Ponto de travessia** (coordenadas)
- **Estação hidrológica próxima** (se houver)

> **Nota:** Se o rio aparecer como "corpo_sem_nome" ou "nao_determinado", a identificação foi incerta — verifique manualmente.

### 4.2 Alternativas Sem Balsa
Na coluna **"Alternativa sem balsa"** (relatório):
- Mostra a menor rota **sem atravessar água**
- Compare: `Distância com balsa` vs `Alternativa sem balsa`
- Se diferença for pequena → prefira rota sem balsa

### 4.3 Auditoria de Rota (Botão "Auditar")
Gera relatório completo:
```
Origem: Município X (UF)
Destino: Município Y (UF)
Distância: XXX km
Modal: Rodoviário + Balsa
Balsa: Sim → Rio: Rio X
Bacia: Bacia Y
Rodovias: BR-XXX, BR-YYY
Ponte: Não identificada
Alternativa sem balsa: XXX km
Fonte hidrográfica: ANA/SNIRH
Fonte territorial: IBGE
Fonte rodoviária: DNIT/OSRM
Fonte aquaviária: ANTAQ
Confiança: Alta (95)
```

---

## 5. MONITOR DE APIs (Aba 📈 Monitor)

### O que monitorar
| Métrica | Normal | Alerta |
|---------|--------|--------|
| **OSRM público** | < 2s | > 5s ou SSL error |
| **FOSSGIS** | < 3s | > 10s ou rate limit |
| **Valhalla** | < 5s | Timeout ou divergência > 30km |
| **SNIRH/ANA** | < 2s | Timeout ou 5xx |
| **IBGE/geocoding** | < 1s | Falha sistemática |

### Últimas Falhas (Painel)
Mostra últimas 50 falhas com:
- **Timestamp** + **UF** + **Motor** + **Erro**
- Agrupamento por UF (identifica instabilidade regional)

---

## 6. EXPORTAÇÃO DE DADOS

### Relatório ANTES×DEPOIS
```bash
py -X utf8 _testes_motor_rotas.py relatorio
# Gera: _RELATORIO_ANTES_DEPOIS.md (203 linhas)
```

### Exportar CSV da Alocação
Na aba **Alocação** → Botão **"Exportar CSV"** → `alocacao_YYYYMMDD_HHMMSS.csv`

Colunas exportadas:
```
Origem, UF, Destino_App, Dist_App, Destino_Ref, Dist_Ref, 
Vencedor, Critério, Balsa, Rio, Bacia, Indice_Confianca
```

---

## 7. CHECKLIST DE VALIDAÇÃO (Pré-Deploy)

```bash
# 1. Compilação
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py

# 2. Testes unitários (192 testes)
py -X utf8 _testes_motor_rotas.py validar
# Deve mostrar: RESULTADO: 192 OK, 0 FALHAS

# 3. Decisão real (38 casos)
py -X utf8 _testes_motor_rotas.py decidir
# Deve mostrar: TODOS OS CASOS PASSARAM

# 4. Relatório
py -X utf8 _testes_motor_rotas.py relatorio
# Gera _RELATORIO_ANTES_DEPOIS.md (203 linhas)

# 4. Commit & Push
git add -A
git commit -m "mensagem"
git push
```

---

## 7. PROBLEMAS COMUNS (FAQ)

| Problema | Causa | Solução |
|----------|-------|---------|
| **"ModuleNotFoundError: fiona/gdal"** | Windows sem GDAL | Use WSL2/Ubuntu ou Docker |
| **OSRM timeout / SSL error** | Rede/instância pública | Fallback automático → FOSSGIS (já implementado) |
| **Valhalla não engaja** | `_valhalla_ativo()` = False | Configure `VALHALLA_URL` no .env |
| **hidrografia_nacional.pkl.gz não carrega** | Arquivo corrompido/ausente | Re-download do IBGE BC250 |
| **Município errado no resultado** | Geocoding falhou | Verifique `_geocodificar_municipio()` |
| **Balsa não detectada** | OSRM público sem ferry | FOSSGIS fallback automático ativo |
| **Rota fluvial None** | Snap > 8km (sede longe do rio) | Snap expandido 30km ativo (432a) |

---

## 8. ARQUIVOS DE REFERÊNCIA

| Arquivo | Descrição |
|---------|-----------|
| `HANDBOOK.md` | Este manual completo |
| `_REGISTRO_DERROTAS.md` | Histórico completo (890 linhas) |
| `_RELATORIO_ANTES_DEPOIS.md` | Comparativo ANTES×DEPOIS |
| `_testes_motor_rotas.py` | Testes + decisão + relatório |
| `streamlit_app.py` | Código principal (~54k linhas) |
| `requirements.txt` | Dependências Python |

---

## 9. CONTATOS E RECURSOS

| Recurso | Link |
|---------|------|
| **Repositório** | https://github.com/lucascardosolccr/OpenRotas |
| **IBGE GeoFTP** | https://geoftp.ibge.gov.br/ |
| **ANA HidroWeb** | https://www.ana.gov.br/hidroweb |
| **SNIRH REST API** | http://www.snirh.gov.br/hidroweb/rest |
| **FOSSGIS OSRM** | https://routing.openstreetmap.de |
| **Valhalla** | https://valhalla.readthedocs.io |

---

## 10. COMANDOS RÁPIDOS (CHEAT SHEET)

```bash
# Tudo de uma vez (validação completa)
py -X utf8 -m py_compile streamlit_app.py _testes_motor_rotas.py && \
py -X utf8 _testes_motor_rotas.py validar && \
py -X utf8 _testes_motor_rotas.py decidir && \
py -X utf8 _testes_motor_rotas.py relatorio

# Ver logs de decisão
grep "VENCEDOR\|FLUVIAL\|FERRY" logs/*.log

# Ver decisões de balsa
grep "Balsa.*Sim" _RELATORIO_ANTES_DEPOIS.md

# Ver rotas fluviais
grep "fluvial" _RELATORIO_ANTES_DEPOIS.md

# Ver estatísticas de confiança
grep "Indice Confianca" _RELATORIO_ANTES_DEPOIS.md
```

---

> **Dica:** Mantenha este manual aberto durante a operação. Em caso de dúvida, consulte `HANDBOOK.md` para documentação técnica completa ou `_REGISTRO_DERROTAS.md` para histórico de decisões.

---

*Manual atualizado em 2026-09-06 | Versão 4.36 | Build 436*