# AI Dev Orchestrator — Fase 5: Dashboard Visual

**Autor:** Lucas Donnangelo + Claude
**Data:** 06/04/2026
**Status:** Planejamento

---

## Objetivo

Criar uma interface web local (localhost) que permita:
- Descrever tasks e executar ciclos sem decorar comandos
- Visualizar em tempo real o que cada IA esta pensando e fazendo
- Intervir a qualquer momento (pausar, editar, cancelar)
- Monitorar custos e tokens em tempo real
- Gerenciar multiplos projetos
- Executar por fases com validacao incremental

---

## Arquitetura

```
Browser (localhost:3000)
    |
    | WebSocket (tempo real) + REST API
    |
    v
FastAPI Backend (localhost:8000)
    |
    | Chama orchestrator internamente
    |
    v
Orchestrator (planner, critic, executor, reviewer, decisor)
    |
    v
Projetos-alvo (FinanceAI, cobaia, etc.)
```

### Stack da Fase 5

| Componente | Tecnologia | Motivo |
|------------|-----------|--------|
| Backend | FastAPI + uvicorn | Async nativo, WebSocket built-in, consistente com o projeto |
| Frontend | React + Tailwind | Interface moderna, responsiva, componentes reutilizaveis |
| Comunicacao | WebSocket + REST | WebSocket pra streaming, REST pra CRUD |
| Estado | React useState/useReducer | Sem overengineering, projeto local |
| Build | Vite | Rapido, zero config |

---

## Sub-fases

### 5.1 Backend API e WebSocket

**Objetivo:** Expor o orchestrator como servico local com streaming de eventos.

**Tasks:**

**Task 5.1.1 — Event System**
Criar `orchestrator/events.py` com um sistema de eventos pub/sub:
- Classe `EventBus` com metodos `emit(event_type, data)` e `subscribe(callback)`
- Tipos de evento: `plan_started`, `plan_completed`, `critic_round`, `critic_consensus`, `execute_started`, `execute_completed`, `review_started`, `review_completed`, `decision_started`, `decision_completed`, `cycle_approved`, `cycle_escalated`, `token_usage`
- Cada evento carrega: timestamp, tipo, dados relevantes (prompt enviado, resposta recebida, score, etc.)
- Integrar no `orchestrator.py`: emitir eventos em cada etapa do ciclo

**Task 5.1.2 — FastAPI Server**
Criar `orchestrator/server.py` com:
- `POST /api/run` — inicia um ciclo (recebe task + project_dir), retorna run_id
- `POST /api/batch` — inicia batch (recebe lista de tasks + project_dir), retorna batch_id
- `POST /api/cancel/{run_id}` — cancela execucao em andamento
- `GET /api/projects` — lista projetos registrados
- `POST /api/projects` — registra um novo projeto (path + nome)
- `DELETE /api/projects/{id}` — remove projeto da lista
- `GET /api/history` — retorna historico de ciclos
- `GET /api/metrics` — retorna metricas calculadas
- `GET /api/templates` — lista templates disponiveis
- `POST /api/init` — cria projeto a partir de template

**Task 5.1.3 — WebSocket Streaming**
Adicionar endpoint WebSocket em `orchestrator/server.py`:
- `WS /ws/run/{run_id}` — stream de eventos em tempo real para um ciclo
- Cada evento do EventBus e enviado como JSON pro WebSocket
- Suporte a multiplos clients conectados no mesmo run
- Eventos incluem: o que o agente esta fazendo, prompt enviado, resposta (streaming), tokens consumidos, custo estimado

**Task 5.1.4 — Controle de Execucao**
Adicionar mecanismo de pausa/resume no orchestrator:
- Flag `paused` no ciclo que checa entre cada etapa
- `POST /api/pause/{run_id}` — pausa antes da proxima etapa
- `POST /api/resume/{run_id}` — retoma execucao
- `POST /api/edit-plan/{run_id}` — recebe plano editado e retoma com ele
- Timeout de 30 minutos em pausa antes de cancelar automaticamente

**Task 5.1.5 — Comando CLI**
Adicionar comando `orchestrate dashboard` ao cli.py:
- Inicia o servidor FastAPI em localhost:8000
- Inicia o servidor de frontend (se build existir) em localhost:3000
- Abre o browser automaticamente
- `Ctrl+C` para ambos

**Criterio de aceite:** `orchestrate dashboard` sobe o servidor, `POST /api/run` executa um ciclo, WebSocket recebe eventos em tempo real.

---

### 5.2 Frontend — Dashboard Base

**Objetivo:** Interface funcional para executar tasks e ver resultados.

**Tasks:**

**Task 5.2.1 — Setup React + Vite**
Criar pasta `dashboard/` na raiz do projeto:
- `npm create vite@latest dashboard -- --template react`
- Instalar Tailwind CSS
- Configurar proxy para localhost:8000
- Componentes base: Layout, Sidebar, Header

**Task 5.2.2 — Tela Inicial (Home)**
- Campo de texto grande para descrever a task
- Dropdown para selecionar projeto (carregado de `/api/projects`)
- Botao "Novo Projeto" que abre modal com templates
- Botao "Executar" que chama `POST /api/run`
- Lista das ultimas 5 execucoes com status

**Task 5.2.3 — Painel de Execucao em Tempo Real**
A tela principal quando um ciclo esta rodando:
- 5 cards horizontais: Planner | Critico | Executor | Reviewer | Decisor
- Card ativo (etapa atual) com borda colorida e animacao de loading
- Cada card expandivel para ver: prompt enviado, resposta recebida (streaming), tempo decorrido
- Barra de progresso geral: etapa 2/5
- Contador de tokens e custo estimado (atualizado em tempo real)
- Botoes: Pausar | Cancelar | Editar Plano (disponivel quando pausado)

**Task 5.2.4 — Painel do Plano**
Quando o Planner gera o plano e o Critico termina:
- Exibir o plano formatado: steps, files, acceptance criteria, complexidade
- Historico dos rounds do Critico (score por round, observacoes)
- Se pausado: editor JSON inline para modificar o plano antes de executar

**Task 5.2.5 — Painel de Review e Decision**
Apos Reviewer e Decisor:
- Diff viewer com syntax highlighting (estilo GitHub)
- Score do review com issues coloridas por severidade
- Resultado do Decisor com reasoning e inconsistencies
- Botoes: Aprovar e Commitar | Rejeitar | Editar e Resubmeter

---

### 5.3 Frontend — Gestao de Projetos

**Objetivo:** Gerenciar multiplos projetos sem sair da interface.

**Tasks:**

**Task 5.3.1 — Tela de Projetos**
- Lista de projetos registrados com: nome, path, stack detectada, ultima execucao
- Botao "Adicionar Projeto Existente" — file picker para selecionar pasta
- Botao "Novo Projeto" — wizard: nome -> template -> path -> criar
- Cada projeto clicavel para ver detalhes

**Task 5.3.2 — Detalhes do Projeto**
- Info: stack, README preview, estrutura de pastas (tree)
- Config: `.orchestrator.yaml` editavel inline
- Historico: tabela de todas as execucoes nesse projeto
- Atalho: campo de task + botao executar (pre-selecionado nesse projeto)

**Task 5.3.3 — Configuracao Visual**
- Editor visual do `.orchestrator.yaml`: dropdowns para provider, model, campos de texto para prompts customizados
- Preview do system prompt resultante (3 camadas resolvidas)
- Salvar grava no `.orchestrator.yaml` do projeto

---

### 5.4 Frontend — Execucao por Fases

**Objetivo:** Permitir planejamento e execucao incremental, fase por fase.

**Tasks:**

**Task 5.4.1 — Planejamento de Fases**
- Campo de texto grande: "Descreva o projeto inteiro ou a proxima fase"
- Botao "Gerar Plano de Fases" — chama o Planner com prompt especial que quebra em fases e tasks
- Exibe: lista de fases, cada fase com lista de tasks
- Usuario pode editar, reordenar, adicionar/remover tasks antes de executar

**Task 5.4.2 — Execucao Controlada por Fase**
- Botao "Executar Fase 1" — roda as tasks daquela fase em batch
- Progresso visual: task 3/6 da Fase 1, com status de cada uma
- Ao final da fase: resumo do que foi feito, botao "Revisar e Aprovar Fase"
- Apos aprovacao: "Executar Fase 2" fica disponivel
- Pode pausar entre fases para testar manualmente

**Task 5.4.3 — Timeline de Progresso**
- Visualizacao tipo kanban ou timeline: fases como colunas, tasks como cards
- Cores por status: pendente (cinza), executando (azul), aprovado (verde), escalated (vermelho)
- Clique numa task para ver detalhes (plano, diff, review, decisor)

---

### 5.5 Frontend — Historico e Metricas Visual

**Objetivo:** Dashboards bonitos com os dados que ja temos.

**Tasks:**

**Task 5.5.1 — Tela de Historico**
- Tabela paginada com todas as execucoes
- Filtros: por projeto, por status, por data
- Clique numa execucao para ver o ciclo completo detalhado

**Task 5.5.2 — Tela de Metricas**
- Cards com KPIs: total de runs, taxa de aprovacao, score medio, custo total
- Grafico de linha: aprovacoes ao longo do tempo
- Grafico de pizza: distribuicao por status
- Grafico de barras: custo por projeto
- Tabela: top 5 tasks mais caras

**Task 5.5.3 — Detalhes de Ciclo**
- Timeline visual do ciclo: Planning -> Critic (rounds) -> Execute -> Review -> Decision
- Cada etapa expandivel com prompt, resposta, tempo, tokens
- Diff viewer com syntax highlighting
- Issues do reviewer com cores por severidade

---

## Dependencias Novas

```
# Backend
fastapi>=0.115.0
uvicorn>=0.30.0
websockets>=13.0

# Frontend (dentro de dashboard/)
react
react-dom
tailwindcss
@tailwindcss/vite
lucide-react       # icones
recharts           # graficos
```

---

## Cronograma Estimado

| Semana | Sub-fase | Entregavel |
|--------|----------|-----------|
| 1 | 5.1 (Backend) | API REST + WebSocket + Event System |
| 2 | 5.2 (Dashboard Base) | Tela inicial + painel de execucao em tempo real |
| 3 | 5.3 (Projetos) | Gestao de projetos + config visual |
| 4 | 5.4 + 5.5 (Fases + Metricas) | Execucao por fases + dashboards |

---

## Principios de Design

1. **Local-first** — tudo roda em localhost, nenhum dado sai da maquina
2. **CLI continua funcionando** — o dashboard e um complemento, nao substitui o terminal
3. **Tempo real** — o usuario vê o que cada IA esta fazendo enquanto faz
4. **Intervencao a qualquer momento** — pausar, editar, cancelar sem perder progresso
5. **Custo visivel** — tokens e custo estimado sempre na tela

---

*Este documento complementa o AI_Dev_Orchestrator_Plano.md principal.*
