# OpenRotas — Edição Desktop

Software instalável para Windows que roda o **mesmo** motor do OpenRotas localmente, aproveitando
CPU/RAM/SSD e dados locais do computador — **sem tocar na aplicação web** (que continua no Streamlit
Cloud, intacta). Tudo da edição desktop vive **isolado nesta pasta `desktop/`**.

> Estado atual: **Etapa 1 — Fundação** (scaffold funcional + empacotamento). Builds são iterativos
> (§37 do plano): esta é a base sólida sobre a qual as próximas etapas se apoiam. A compilação do
> instalador e o teste em máquina limpa acontecem **no seu Windows** (este repositório é editado num
> ambiente Linux na nuvem, que não compila `.exe` nem testa Windows).

---

## 1. Decisão de arquitetura

Avaliadas as 4 opções do plano (§4). **Escolhida: Opção B — Streamlit local + launcher desktop.**

| Opção | Resumo | Veredito |
|---|---|---|
| A — Streamlit puro local | só `streamlit run` | funciona, mas sem janela/instalador — não é "produto" |
| **B — Streamlit local + launcher (pywebview) + instalador** | **reusa 100% do app; janela nativa; instalador** | **ESCOLHIDA** |
| C — backend Python + UI desktop nova (Qt/Electron) | reescrever toda a UI | **rejeitada**: risco altíssimo de perder funcionalidades (viola §21/§44 "zero perda") e meses de trabalho |
| D — outra | — | B cobre melhor o custo-benefício |

**Por quê B:** o app web tem ~66 mil linhas e dezenas de abas/análises. Reescrever a UI (C)
quase certamente perderia recursos — exatamente o que o plano proíbe. A Opção B **reaproveita o
app inteiro** (zero perda garantida) e ainda assim entrega um software de verdade: janela nativa
(WebView2/Edge, sem barra de navegador), instalador, atalhos, diretório de dados, diagnóstico e
desinstalador. As vantagens locais entram por **configuração**, não por reescrita.

### O ganho não é cosmético
Os três piores problemas da versão web **nascem do ambiente de nuvem** e **somem** no desktop:

- **Google bloqueado** (IP de datacenter) → no seu PC, IP residencial, o Google volta a responder →
  **velocidade + participação total do Google** (o maior ganho isolado);
- **Sessão/estudo morto no meio** (redeploy/WebSocket/container efêmero) → processo local não é morto;
- **Cache apagado a cada deploy** → cache **persistente** no perfil do usuário.

Além disso: a app **já dimensiona os workers pelos núcleos da CPU** — num PC de 8/16 núcleos ela usa
mais paralelismo **automaticamente**, sem mudar nada.

---

## 2. Estrutura da pasta

```
desktop/
├── app/
│   ├── launcher.py          # bootstrapper: motor local + sobe o Streamlit + janela nativa
│   ├── desktop_config.py    # hardware, cache persistente, secrets/env (ativa vantagens locais)
│   └── diagnostics.py       # autodiagnóstico de bases/cache/motor (§17/§18)
├── engines/                 # MOTOR de rotas local (Etapa 3)
│   ├── osrm_manager.py      # detecta/sobe/valida um OSRM local; injeta OSRM_URL
│   ├── benchmark.py         # mede OSRM local × público (§9/§29), stdlib
│   └── sample_pairs.csv     # 10 pares O/D reais do Brasil p/ o benchmark
├── config/
│   └── desktop.example.json # modelo de config (Supabase, OSRM_URL, offline) — copie p/ o perfil
├── scripts/
│   ├── run_dev.bat          # rodar SEM instalar (cria venv, instala, abre) — uso imediato
│   └── diagnostico.bat      # roda o autodiagnóstico
├── packaging/
│   └── launcher.spec        # PyInstaller (ONEDIR) — empacota app + runtime + bases
├── installer/
│   ├── openrotas.iss        # Inno Setup — gera "OpenRotas Setup.exe"
│   └── build.ps1            # build reproduzível: limpa→empacota→instalador→valida (§36)
├── requirements-desktop.txt # = requirements da web + pywebview + psutil + pyinstaller
└── README.md
```

**Isolamento (§35):** nada aqui é importado pelo app web; o app web não sabe que o desktop existe.
O launcher apenas *lança* o `streamlit_app.py` da raiz (reuso, não cópia — §34).

---

## 3. Como usar AGORA (modo dev, sem instalar)

Pré-requisitos: Windows, Python 3.12, o repositório clonado.

1. Copie `desktop/config/desktop.example.json` para `%LOCALAPPDATA%\OpenRotas\config\desktop.json`
   e preencha `SUPABASE_URL` e `SUPABASE_ANON_KEY` (as mesmas da nuvem). `OSRM_URL` é opcional.
2. Duplo-clique em `desktop\scripts\run_dev.bat` (na 1ª vez ele cria o ambiente e instala tudo;
   depois abre direto). O app abre numa **janela nativa**.

## 4. Como gerar o INSTALADOR (no seu Windows)

```powershell
cd desktop
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```
Gera `desktop\installer\dist_installer\OpenRotas Setup.exe`. (Requer o
[Inno Setup 6](https://jrsoftware.org/isdl.php) instalado; sem ele, o build para no bundle onedir,
que já é executável.)

---

## 5. Matriz de funcionalidades (web × desktop) — §21

A edição desktop roda o **mesmo** `streamlit_app.py`, então **toda** aba/análise/exportação da web
existe no desktop por construção. A coluna "Ganho local" indica onde o desktop supera a web.

| Funcionalidade | Web | Desktop | Ganho local |
|---|:--:|:--:|---|
| Processamento em Lote | ✓ | ✓ | + rápido (Google desbloqueado), + workers, cache persistente |
| Decidir / Validador | ✓ | ✓ | rota rápida com Google real |
| Roteamento multi-motor | ✓ | ✓ | OSRM local opcional (offline) via `OSRM_URL` |
| Inteligência geográfica | ✓ | ✓ | bases locais já embarcadas; sem limite de container |
| Hidrografia / rios / balsas | ✓ | ✓ | idem (dados locais) |
| Mapas / gráficos | ✓ | ✓ | = |
| Comparador / Auditoria | ✓ | ✓ | = |
| Exportações (Excel/HTML/CSV) | ✓ | ✓ | grava direto no disco do usuário |
| Login / perfis / compartilhar | ✓ | ✓ | mesmo Supabase → estudos aparecem nos dois |
| Estabilidade em estudos longos | ⚠️ cai | ✓ | processo local não é morto por deploy/timeout |

Validação formal dessa matriz (clicar cada aba no desktop) faz parte da Etapa 4.

---

## 6. Roadmap (etapas seguintes)

- **Etapa 1 — Fundação (ESTA):** scaffold, launcher, config, diagnóstico, spec, instalador, matriz. ✔
- **Etapa 2 — Build real no Windows:** rodar `build.ps1`, resolver hidden-imports/datas que faltarem
  (builds iterativos, §37), validar a janela e o 1º processamento; ícone/versão/assinatura (§38).
- **Etapa 3 — Motor de rotas local de 1ª classe (§9/§10): ✔ (camada entregue)** — ver seção 8.
  O desktop agora gerencia um OSRM local (modo `docker`/`external`) e há um harness de benchmark.
  Pendente, no seu Windows: preparar o grafo do Brasil (guias já entregues) e rodar o benchmark.
- **Etapa 4 — Dados completos + offline (§6/§12/§32):** avaliar grafos/mapas completos como
  componentes de 1ª classe (instalados à parte em `data_local/`, com *lazy loading* e índices —
  §16), e o modo offline fim-a-fim (fallback local quando sem internet).
- **Etapa 5 — Processamento em 2º plano + progresso real (§27/§28)** e **config de desempenho** (§25).
- **Etapa 6 — Testes de performance web×desktop (§29)** e **teste de máquina limpa (§30/§31)**.

### Decisões que precisam de você (ficam para a etapa certa, não decido sozinho)
- **Offline incluindo login:** hoje o portão de auth exige Supabase (internet). Rodar offline-de-verdade
  pede um *bypass* local **opt-in** (ativado só pelo sinalizador `OPENROTAS_DESKTOP`), que é uma
  mudança sensível de segurança no código compartilhado — proponho e implemento com sua aprovação,
  mantendo a web 100% inalterada.
- **Tamanho do instalador:** incluir o grafo/mapas completos deixa o `.exe` com vários GB. Avaliamos
  juntos o custo-benefício (§32) antes de embutir.

---

## 8. Motor de rotas local (Etapa 3) — §9/§10

### Decisão de engenharia (com benchmark, não "no chute")
O plano (§9) pede avaliar OSMnx/NetworkX/igraph e **fazer benchmark** antes de escolher. Análise:

- **Roteador em processo (NetworkX/OSMnx/igraph):** elegante, mas para a malha do **Brasil inteiro**
  (milhões de nós/arestas) é *ordens de grandeza* mais lento e teria de reimplementar o que o OSRM
  já faz bem — snapping de coordenadas à via, restrições de conversão, rotas alternativas. NetworkX
  em grafo nacional é inviável; igraph/scipy melhoram, mas ainda muito abaixo do OSRM e sem a
  qualidade de roteamento. Reimplementar OSRM mal violaria "zero perda de precisão".
- **OSRM (C++) local:** o mesmo motor que o app já consome por HTTP. Rápido (ms/rota), correto, com
  alternativas — e roda **offline** com o grafo do Brasil. **Escolhido.**

A integração "de 1ª classe": o desktop **gerencia o ciclo de vida** do seu OSRM (sobe/valida/encerra)
e injeta a URL — sem reescrever o cliente de rotas. Reuso do caminho de produção = zero perda.

### Como ativar (no `desktop.json`)
1. Prepare o grafo do Brasil uma vez (ver o guia **OSRM local** já entregue: `extract/partition/customize`).
   Guarde os arquivos `brazil-latest.osrm*` em `%LOCALAPPDATA%\OpenRotas\data_local\`.
2. No `desktop.json`, bloco `"osrm"`:
   - `"mode": "docker"` + `"graph_path"` apontando para o `.osrm` → o app **sobe o OSRM sozinho** ao abrir
     e o **encerra** ao fechar (precisa do Docker Desktop);
   - ou `"mode": "external"` + `"url"` se você prefere subir o OSRM por fora.
3. Pronto: o roteamento fica rápido e **offline**, e (pela melhoria já no código) o scraper do Google
   sai da frente sozinho quando há motor confiável. `mode:"off"` (padrão) mantém o OSRM público online.

### Benchmark (§9/§29) — comprovar o ganho com números
```
cd desktop\engines
..\..\venv\Scripts\python benchmark.py                 # compara OSRM local × público
..\..\venv\Scripts\python benchmark.py --url http://localhost:5000 --rotulo "OSRM local"
```
Mede latência (média/mediana/p95), vazão (rotas/s) e taxa de sucesso sobre 10 pares reais do Brasil.
A tabela final é a evidência objetiva do benefício do motor local.

---

## 9. Segurança (§42)
Segredos (Supabase) ficam **só** no perfil do usuário (`%LOCALAPPDATA%\OpenRotas\config\desktop.json`),
nunca no git (ver `.gitignore`). O `secrets.toml` local é gerado em tempo de execução a partir dele.
Mantém-se a regra do projeto: só a **anon key** pública no cliente; nunca a `service_role`.
