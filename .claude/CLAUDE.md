# CLAUDE.md — Contexto para Claude Code

## O Que E Este Projeto

**AI Dev Orchestrator** — sistema CLI + dashboard web que automatiza o ciclo de desenvolvimento usando multiplas IAs com papeis separados e validacao em camadas.

### Papeis das IAs

| Papel | O que faz | Provider | Modelo |
|-------|-----------|----------|--------|
| **Planner** | Gera plano estruturado | Claude (Anthropic) | claude-sonnet-4-6 |
| **Critico** | Critica e melhora o plano (2-5 rounds) | Gemini (Google) | gemini-2.5-flash |
| **Executor** | Implementa o codigo | Claude Code (Agent SDK) | — |
| **Reviewer** | Avalia qualidade do codigo | Gemini (Google) | gemini-2.5-flash |
| **Decisor** | Valida coerencia com o plano | Gemini (Google) | gemini-2.5-flash |

**Principio:** Claude planeja e executa. Gemini critica, revisa e valida. Elimina vies.

### Fluxo Completo

```
Voce (task)
  --> Planner (Claude) gera plano
  --> Critico (Gemini) critica [2-5 rounds ate consenso]
  --> Plano Final
  --> Executor (Agent SDK) implementa
  --> Reviewer (Gemini) avalia codigo [max 3 retries]
  --> Decisor (Gemini) valida coerencia com plano
  --> Atualiza SESSAO_ATUAL.md
  --> Proxima tarefa (ou escala para voce)
```

## Stack

- **Python 3.10+**
- **anthropic** SDK — Planner
- **claude-agent-sdk** — Executor
- **google-genai** — Gemini (Critico, Reviewer, Decisor)
- **openai** — fallback opcional
- **click** + **rich** — CLI
- **FastAPI** + **uvicorn** — Backend do dashboard [Fase 5]
- **React** + **Tailwind** + **Vite** — Frontend do dashboard [Fase 5]
- **WebSocket** — streaming tempo real [Fase 5]

## Status Atual

### [OK] Fase 1 — MVP (COMPLETA)
### [OK] Fase 2 — Multi-Model e Robustez (COMPLETA)
### [OK] Fase 3 — Orquestracao Avancada (COMPLETA)
### [OK] Fase 4 — Extensibilidade (COMPLETA)

175 testes passando. 6/6 tasks do batch cobaia aprovadas. Sistema validado end-to-end.

### [>>] Fase 5 — Dashboard Visual (PROXIMA)

Plano detalhado em: `docs/Fase5_Dashboard_Plano.md`

#### 5.1 Backend API e WebSocket
- `orchestrator/events.py` — EventBus pub/sub com tipos de evento por etapa
- `orchestrator/server.py` — FastAPI com REST + WebSocket
- Endpoints: /api/run, /api/batch, /api/cancel, /api/pause, /api/resume, /api/projects, /api/history, /api/metrics
- WS /ws/run/{run_id} — streaming de eventos tempo real
- Comando `orchestrate dashboard` no cli.py

#### 5.2 Frontend — Dashboard Base
- React + Vite + Tailwind em `dashboard/`
- Tela inicial: campo de task, selecao de projeto, botao executar
- Painel de execucao: 5 cards com status de cada agente em tempo real
- Controles: pausar, cancelar, editar plano
- Monitor de tokens e custo

#### 5.3 Frontend — Gestao de Projetos
- Lista de projetos registrados com stack, historico
- Novo projeto via wizard com templates
- Config visual do .orchestrator.yaml

#### 5.4 Frontend — Execucao por Fases
- Descrever projeto inteiro, Planner quebra em fases/tasks
- Executar fase por fase com revisao entre cada uma
- Timeline/kanban de progresso

#### 5.5 Frontend — Historico e Metricas Visual
- Graficos de aprovacao, custos, tempo
- Diff viewer com syntax highlighting
- Detalhes expandiveis de cada ciclo

## Estrutura do Projeto

```
ai-dev-orchestrator/
├── orchestrator/
│   ├── __init__.py
│   ├── cli.py               # [OK] CLI com click
│   ├── config.py             # [OK] Config com 3-layer resolution
│   ├── models.py             # [OK] TaskPlan, ReviewResult, CycleRecord, CriticResult, DecisionResult
│   ├── planner.py            # [OK] Planner via provider
│   ├── executor.py           # [OK] Executor via Agent SDK
│   ├── reviewer.py           # [OK] Reviewer via provider
│   ├── critic.py             # [OK] Critico iterativo
│   ├── decisor.py            # [OK] Decisor pos-review
│   ├── chat.py               # [OK] REPL interativo
│   ├── context.py            # [OK] Contexto inteligente
│   ├── git.py                # [OK] Branch, commit, PR description
│   ├── logger.py             # [OK] Logging JSON
│   ├── metrics.py            # [OK] Analytics
│   ├── session.py            # [OK] SESSAO_ATUAL.md automatizado
│   ├── templates.py          # [OK] Templates de projeto
│   ├── events.py             # [FASE 5.1] EventBus
│   ├── server.py             # [FASE 5.1] FastAPI backend
│   ├── providers/
│   │   ├── __init__.py       # [OK] Factory + plugin registry
│   │   ├── base.py           # [OK] BaseAgent
│   │   ├── anthropic.py      # [OK] ClaudeProvider
│   │   ├── google.py         # [OK] GeminiProvider
│   │   ├── openai.py         # [OK] OpenAIProvider
│   │   └── retry.py          # [OK] Retry com backoff
│   └── prompts/              # [OK] System prompts (6 arquivos)
├── dashboard/                # [FASE 5.2] React + Vite
├── configs/
├── logs/
├── docs/
│   ├── AI_Dev_Orchestrator_Plano.md
│   └── Fase5_Dashboard_Plano.md
├── tests/                    # [OK] 175 testes
└── ...
```

## Convencoes de Codigo

- Python 3.10+ com `from __future__ import annotations`
- Type hints em tudo
- Async/await para chamadas de API e Agent SDK
- Formatacao: ruff (line-length 100)
- Testes: pytest + pytest-asyncio
- Sem emojis Unicode no output (compatibilidade Windows cp1252)
- Marcadores ASCII: [OK], [X], [!]
- Frontend: React funcional com hooks, Tailwind utility classes

## Referencias

- Plano geral: `docs/AI_Dev_Orchestrator_Plano.md`
- Plano Fase 5: `docs/Fase5_Dashboard_Plano.md`
- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- Claude Agent SDK: https://pypi.org/project/claude-agent-sdk/
- Google GenAI SDK: https://github.com/googleapis/python-genai
