# AI Dev Orchestrator — Fase 7: Dashboard para Execução por Plano Hierárquico

**Autor:** Lucas Donnangelo + Claude  
**Data:** 22/04/2026  
**Status:** Planejamento

---

## Objetivo

Integrar o fluxo de `orchestrate plan run` ao dashboard visual, oferecendo visibilidade
em tempo real da execução hierárquica (fases → subfases → tasks) com controles de
intervenção humana nos pontos de pausa.

O sistema já executa tudo corretamente via CLI. A Fase 7 não muda o comportamento —
ela torna o processo **observável e controlável** através de uma interface visual dedicada,
sem substituir o CLI.

---

## Princípios de UX

1. **Mostre o que importa, esconda o ruído** — o usuário precisa saber: o que está rodando agora, o que já foi feito, e o que precisa da minha atenção. Nada além disso em primeiro plano.
2. **Ação clara em pontos de pausa** — quando o sistema espera o usuário, a interface deixa isso óbvio. Nenhuma ambiguidade sobre "preciso fazer algo agora?"
3. **Hierarquia visual = hierarquia do plano** — Fase → Subfase → Task mapeiam diretamente para a estrutura visual. O usuário entende onde está no projeto só de olhar.
4. **Contexto sem scroll excessivo** — tasks concluídas não desaparecem, mas ficam compactas. A task atual tem destaque. As próximas ficam visíveis mas em segundo plano.
5. **Progressão fluida** — a UI avança com a execução, sem precisar de refresh manual.

---

## O que mostrar vs. o que esconder

| Informação | Visível? | Onde |
|------------|----------|------|
| Fase/Subfase/Task atual em execução | Sim — destaque principal | Painel central |
| Progresso global (X/Y tasks, % por fase) | Sim | Header da página |
| Output do agente em tempo real (Executor) | Sim — streaming | Card central |
| Status de cada task (done/running/pending/escalated) | Sim — ícone + cor | Árvore lateral |
| Score do Review | Sim — ao concluir task | Badge na task |
| Commit gerado | Sim — ao concluir task | Badge na task com hash |
| Rounds internos do Critic | Não (por padrão) | Expansível em modo verbose |
| Raciocínio do Decisor | Não (aprovações) | Expansível em modo verbose |
| Logs técnicos de infraestrutura | Não | Disponível via CLI |
| Detalhes do Reviewer em tasks aprovadas | Não (por padrão) | Expansível ao clicar na task |

---

## Sub-fases

---

### 7.1 — Backend: Suporte ao `plan run` via API e WebSocket

**Objetivo:** Expor o `run_plan` do `plan_runner.py` via FastAPI, com streaming de eventos
por WebSocket, para que o frontend possa acompanhar a execução em tempo real.

---

**7.1.1 — Novos tipos de evento no EventBus**

Adicionar ao `orchestrator/events.py` os seguintes tipos de evento específicos do plan runner:

| Evento | Payload | Quando emitido |
|--------|---------|----------------|
| `plan_loaded` | `{ name, phases: [{id, name, task_count}], total_tasks, done_tasks }` | Ao carregar o PLANO.md |
| `task_started` | `{ task_id, description, phase_id, subphase_id, attempt }` | Ao iniciar execução de uma task |
| `task_done` | `{ task_id, commit_hash, score, duration_s }` | Ao concluir task com sucesso |
| `task_escalated` | `{ task_id, reason }` | Ao escalar task |
| `task_skipped` | `{ task_id }` | Ao pular task já done/skipped |
| `subphase_complete` | `{ subphase_id, done, escalated, skipped, duration_s }` | Ao fim de subfase |
| `phase_complete` | `{ phase_id, done, escalated, skipped, duration_s }` | Ao fim de fase |
| `plan_paused` | `{ reason: "subphase" | "phase" | "escalation", context }` | Ao pausar para validação |
| `plan_resumed` | `{}` | Ao retomar após pausa |
| `plan_complete` | `{ total, done, escalated, skipped, duration_s }` | Ao concluir plano inteiro |
| `plan_aborted` | `{ reason }` | Ao abortar execução |

Os eventos existentes do ciclo (`cycle_planning`, `cycle_executing`, etc.) continuam
sendo emitidos normalmente — o frontend os usa para o streaming do agente atual.

**Critério de aceite:** ao rodar `run_plan` manualmente, os eventos são emitidos
no EventBus na ordem correta.

---

**7.1.2 — Endpoints REST para plan runner**

Adicionar ao `orchestrator/server.py`:

```
POST   /api/plan/run              inicia run_plan, retorna plan_run_id
GET    /api/plan/run/{id}         estado atual do plan run
POST   /api/plan/pause/{id}       pausa na próxima boundary (subphase/phase)
POST   /api/plan/resume/{id}      confirma pausa e continua
POST   /api/plan/abort/{id}       aborta execução

GET    /api/plan/load             lê PLANO.md do projeto e retorna ProjectPlan parseado
POST   /api/plan/generate         chama generate_project_plan + critic loop (6.5)
POST   /api/plan/save             salva PLANO.md no projeto

Body de /api/plan/run:
{
  "project_id": "...",
  "phase": "1",          // opcional — filtro de fase
  "subtask": "1.1",      // opcional — filtro de subfase
  "auto_continue": false,
  "pause_after_subtask": true,
  "pause_after_phase": true
}
```

Estado do plan run (`PlanRunState`):
```python
@dataclass
class PlanRunState:
    id: str
    project_id: str
    status: str          # "running" | "paused" | "complete" | "aborted" | "error"
    plan: ProjectPlan
    current_task_id: str | None
    current_run_id: str | None    # run_id do ciclo atual (para WS do agente)
    pause_reason: str | None      # "subphase" | "phase" | "escalation"
    pause_context: dict | None    # resumo do que foi feito até agora
    started_at: datetime
    results: list[TaskResult]
```

**Critério de aceite:** `POST /api/plan/run` inicia execução e retorna `plan_run_id`.
`GET /api/plan/run/{id}` retorna estado atualizado. `POST /api/plan/resume/{id}`
desbloqueia pausa e continua.

---

**7.1.3 — WebSocket para plan run**

Adicionar endpoint WebSocket:

```
WS /ws/plan/{plan_run_id}
```

Comportamento:
- Emite todos os eventos do `plan_loader` (7.1.1) em tempo real
- Emite também os eventos do ciclo atual (`cycle_*`) para streaming do agente em execução
- Suporte a history replay ao reconectar (mesmo padrão do `/ws/run/{run_id}`)
- Keepalive 30s (mesmo padrão existente)
- Ao receber mensagem `{ "action": "resume" }` do cliente, desbloqueia pausa

**Critério de aceite:** conectar ao WS e receber eventos em ordem conforme
o plan runner executa tasks.

---

**Critério de aceite da sub-fase 7.1:** rodar `run_plan` via API, conectar ao WebSocket
e receber todos os eventos de progresso em tempo real, incluindo pausa e retomada.

---

### 7.2 — Frontend: Página `/plan`

**Objetivo:** Criar a página principal de execução por plano hierárquico no dashboard React.

---

**7.2.1 — Hook `usePlanSocket`**

Criar `dashboard/src/hooks/usePlanSocket.js`:

```javascript
usePlanSocket(planRunId) => {
  plan,              // ProjectPlan atual
  status,            // "idle" | "running" | "paused" | "complete" | "aborted"
  currentTaskId,     // id da task em execução
  currentRunId,      // run_id do ciclo atual (para streaming do agente)
  pauseReason,       // "subphase" | "phase" | "escalation" | null
  pauseContext,       // { done, escalated, commits, duration_s }
  results,           // TaskResult[]
  resume,            // fn: POST /api/plan/resume
  abort,             // fn: POST /api/plan/abort
}
```

Mesmo padrão de reconexão automática do `useRunSocket` (5x / backoff 2s).

**Critério de aceite:** ao iniciar plan run via API e conectar com o hook,
o estado atualiza em tempo real conforme os eventos chegam.

---

**7.2.2 — Layout da página `/plan`**

A página tem 3 zonas principais:

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER: [Nome do Projeto]  [Progresso global]  [Controles] │
├──────────────────┬──────────────────────────────────────────┤
│                  │                                           │
│  ÁRVORE DO       │  PAINEL CENTRAL                          │
│  PLANO           │                                           │
│  (lateral)       │  - Task atual em execução (destaque)     │
│                  │  - Streaming do agente                    │
│  Fase 1          │  - Resultado ao concluir                 │
│    1.1 [x]       │                                           │
│    1.2 [>]       ├──────────────────────────────────────────┤
│      1.2.1 [x]   │                                           │
│      1.2.2 [>]   │  PAINEL DE PAUSA (aparece quando pausado)│
│      1.2.3 [ ]   │  - Resumo do que foi feito               │
│  Fase 2          │  - Botão "Continuar" ou "Abortar"        │
│    2.1 [ ]       │                                           │
│                  │                                           │
└──────────────────┴──────────────────────────────────────────┘
```

Comportamento da árvore lateral:
- Fases colapsáveis — clique no header para expandir/colapsar
- Fase ativa fica expandida automaticamente
- Task atual tem indicador pulsante
- Tasks done ficam com ícone de check e hash do commit ao hover
- Tasks escaladas ficam com ícone de alerta em vermelho

**Critério de aceite:** página renderiza com estrutura correta e árvore
reflete o estado do plano.

---

**7.2.3 — Árvore do plano (PlanTree)**

Componente `dashboard/src/components/PlanTree.jsx`:

```
Props:
  plan: ProjectPlan
  currentTaskId: string | null
  results: TaskResult[]

Renderização por item:
  Phase:    ícone de fase + nome + contador "X/Y" + chevron collapse
  SubPhase: indentação L1 + nome + contador "X/Y"
  Task:     indentação L2 + ícone de status + id + descrição (truncada)
            hover: tooltip com descrição completa + commit hash (se done)
```

Ícones de status por task:
- `[ ]` pending — círculo vazio, cor neutra
- `[>]` running — ícone pulsante animado, cor primária
- `[x]` done — check, cor verde
- `[!]` escalated — alerta, cor vermelha
- `[-]` skipped — traço, cor cinza

**Critério de aceite:** árvore renderiza corretamente para um plano com 3 fases,
6 subfases e 20 tasks.

---

**7.2.4 — Painel central de execução (PlanExecutionPanel)**

Componente `dashboard/src/components/PlanExecutionPanel.jsx`:

**Estado: idle (nenhum plan run ativo)**
- Botão "Iniciar Execução" → abre modal de configuração
- Exibe último estado do PLANO.md (tasks done/escalated do histórico)

**Estado: running**
- Card da task atual: id + descrição + fase/subfase de origem
- Abaixo: streaming do agente atual (reutiliza `AgentCard` existente via `currentRunId`)
- Badge de tentativa (ex: "Tentativa 2/3") se for retry

**Estado: task concluída (transição)**
- Card da task flipa para mostrar: aprovado ✓ + score + commit hash + duração
- Fica visível por 2s antes de iniciar a próxima task

**Estado: paused**
- Painel de pausa ocupa o centro (7.2.5)

**Estado: complete**
- Resumo final: X tasks concluídas, Y escaladas, Z puladas
- Lista de commits gerados (clicáveis se GitHub URL disponível)
- Duração total
- Botão "Novo Plano" ou "Ver Histórico"

**Critério de aceite:** painel reflete corretamente cada estado conforme
eventos chegam via WebSocket.

---

**7.2.5 — Painel de pausa (PlanPausePanel)**

Componente `dashboard/src/components/PlanPausePanel.jsx`:

Aparece quando `status === "paused"`. Ocupa o centro da tela com destaque visual
claro (não pode ser ignorado acidentalmente).

Conteúdo:
```
[ícone de pausa]

Subfase 1.2 concluída          ← ou "Fase 1 concluída" / "Task escalada"

Tasks concluídas: 3
Tasks escaladas:  0
Commits gerados:  3
  feat: criar modelos base (abc1234)
  feat: configurar banco (def5678)
  feat: adicionar migrations (ghi9012)
Duração: 4m 32s

[Continuar para Subfase 1.3]   [Abortar]
```

Para escalações, o painel exibe a mensagem de escalação e as opções:
`[Tentar novamente]` `[Pular task]` `[Abortar]`

**Critério de aceite:** painel aparece corretamente ao receber evento `plan_paused`
e some ao clicar em "Continuar" após confirmação via API.

---

**7.2.6 — Modal de configuração de execução**

Componente `dashboard/src/components/PlanRunModal.jsx`:

Abre ao clicar "Iniciar Execução" na página `/plan`.

Campos:
```
Projeto:           [dropdown com projetos cadastrados]
Escopo:            ○ Plano completo  ○ Fase  ○ Subfase
                   [input: "1" ou "1.1" se escopo específico]
Pausas:            [x] Pausar ao fim de cada subfase
                   [x] Pausar ao fim de cada fase
Modo automático:   [ ] Executar tudo sem pausas

[Cancelar]  [Iniciar]
```

Ao clicar "Iniciar":
1. `POST /api/plan/run` com as configurações
2. Redireciona para `/plan/{plan_run_id}`
3. WebSocket conecta automaticamente

**Critério de aceite:** modal abre, valida campos, inicia run e redireciona
para a página de acompanhamento.

---

**Critério de aceite da sub-fase 7.2:** página `/plan` funcional com árvore lateral,
painel central com streaming, e painel de pausa operacional.

---

### 7.3 — Integração com a navegação existente

**Objetivo:** Conectar a nova página `/plan` ao dashboard existente de forma coerente,
sem quebrar nenhuma funcionalidade das Fases 5.

---

**7.3.1 — Rota e Sidebar**

Adicionar ao React Router:
```javascript
<Route path="/plan" element={<Plan />} />
<Route path="/plan/:planRunId" element={<PlanRun />} />
```

Adicionar à `Sidebar`:
- Item "Plano" com ícone de mapa/hierarquia
- Badge de "em execução" quando há plan run ativo (mesmo padrão do badge de runs ativos)

**Critério de aceite:** navegação para `/plan` funciona via sidebar e URL direta.

---

**7.3.2 — Geração de plano via dashboard**

Na página `/plan` (estado idle), botão "Gerar Plano com IA" além de "Iniciar Execução":

Abre modal com:
```
Descrição do projeto:  [textarea]
Stack (opcional):      [input]
Premissas (opcional):  [textarea]

[Cancelar]  [Gerar]
```

Fluxo:
1. `POST /api/plan/generate` → inicia geração + loop Critic
2. Exibe loading com mensagem "Claude está planejando... Gemini está revisando..."
3. Exibe o PLANO.md gerado em preview (Markdown renderizado)
4. Botões: `[Aprovar e Salvar]` `[Editar]` `[Descartar]`
5. Se aprovado: `POST /api/plan/save` → salva no projeto

**Critério de aceite:** gerar plano via dashboard, aprovar e iniciar execução
sem tocar no terminal.

---

**7.3.3 — Link de plan run no histórico existente**

Na página `/history`, quando um ciclo faz parte de um plan run:
- Adicionar coluna "Plano" com link para o plan run correspondente
- Tooltip: "Task 1.2.3 do plano FinanceAI"

Isso conecta o histórico granular de ciclos com o contexto hierárquico do plano.

**Critério de aceite:** ciclos gerados por plan run aparecem com referência
ao plano no histórico.

---

**Critério de aceite da sub-fase 7.3:** dashboard integrado — sidebar com acesso ao
plano, geração via UI, e histórico com contexto de plano.

---

## Arquivos novos

```
orchestrator/
└── (nenhum arquivo novo — apenas modificações em server.py e events.py)

dashboard/src/
├── pages/
│   ├── Plan.jsx              # Página /plan (idle + configuração)
│   └── PlanRun.jsx           # Página /plan/:id (execução em tempo real)
├── components/
│   ├── PlanTree.jsx          # Árvore lateral do plano
│   ├── PlanExecutionPanel.jsx # Painel central de execução
│   ├── PlanPausePanel.jsx    # Painel de pausa com confirmação
│   └── PlanRunModal.jsx      # Modal de configuração de execução
└── hooks/
    └── usePlanSocket.js      # WebSocket hook para plan run
```

## Arquivos modificados

```
orchestrator/
├── events.py     # Novos tipos de evento do plan runner
└── server.py     # Novos endpoints /api/plan/* e WS /ws/plan/*

dashboard/src/
├── App.jsx       # Novas rotas /plan e /plan/:id
└── components/
    ├── Sidebar.jsx      # Item "Plano" + badge de ativo
    └── History.jsx      # Coluna "Plano" em ciclos de plan run
```

---

## Comandos novos (API)

```
POST   /api/plan/run              inicia execução hierárquica
GET    /api/plan/run/{id}         estado atual
POST   /api/plan/pause/{id}       sinaliza pausa na próxima boundary
POST   /api/plan/resume/{id}      confirma e retoma
POST   /api/plan/abort/{id}       aborta
GET    /api/plan/load             carrega PLANO.md do projeto
POST   /api/plan/generate         gera PLANO.md via IA + Critic
POST   /api/plan/save             salva PLANO.md no projeto
WS     /ws/plan/{plan_run_id}     streaming de eventos
```

---

## O que NÃO muda

- CLI continua funcionando exatamente igual — `orchestrate plan run` é independente do dashboard
- Fluxo de task única (`orchestrate run`) e batch não são afetados
- Dados históricos existentes não são migrados
- Nenhuma mudança em `plan.py`, `plan_runner.py`, `critic.py` ou `orchestrator.py`

---

## Cronograma estimado

| Sub-fase | Descrição | Estimativa |
|----------|-----------|------------|
| 7.1 | Backend: eventos, endpoints, WebSocket | 1-2 sessões |
| 7.2 | Frontend: página /plan completa | 2-3 sessões |
| 7.3 | Integração: sidebar, geração, histórico | 1 sessão |

---

## Critério de aceite global

Dado um projeto com `PLANO.md` com 3 fases e 10 tasks:

1. Abrir o dashboard, navegar para "Plano"
2. Clicar "Iniciar Execução", configurar e confirmar
3. Acompanhar a execução em tempo real:
   - Árvore lateral atualiza conforme tasks são concluídas
   - Painel central mostra o agente em execução com streaming
   - Ao fim de cada subfase, painel de pausa aparece com resumo
   - Clicar "Continuar" retoma execução
4. Ao fim do plano, ver resumo com todos os commits gerados

Tudo isso sem tocar no terminal.

---

*Este documento complementa o AI_Dev_Orchestrator_Plano.md e Fase6_Plano_Hierarquico.md.*
