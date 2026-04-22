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
### [OK] Fase 5 — Dashboard Visual (COMPLETA — 5.4 pulada intencionalmente)
### [OK] Fase 6 — Orquestracao por Plano Hierarquico (COMPLETA)
### [>] Fase 7 — Dashboard para Execucao por Plano Hierarquico (EM ANDAMENTO)

468 testes passando. 7.1.1 e 7.1.2 concluidas.

Plano detalhado em: `docs/Fase7_Dashboard_Plano_Hierarquico.md`

#### [OK] 6.1 Parser e Modelo de Dados
- `orchestrator/plan.py` — PlanTaskStatus, PlanTask, SubPhase, Phase, ProjectPlan
- `parse_plan(path)` / `parse_plan_text(text)` — parser Markdown hierarquico
- `write_plan(plan, path)` — writer in-place (preserva formatacao, atualiza so checkboxes)
- CLI: `orchestrate plan status` / `plan next` / `plan reset TASK_ID`

#### [OK] 6.2 Motor de Execucao por Plano
- `orchestrator/plan_runner.py` — RunPlanOptions, run_plan, _build_phase_context, pausas, retomada idempotente

#### [OK] 6.3 Critic de Coerencia Entre Tasks
- `orchestrator/critic.py` — `critique_plan` e `run_critic_loop` aceitam `phase_context: str | None`
- `orchestrator/prompts/critic_system.md` — criterio Coherence adicionado

#### [OK] 6.4 Comando CLI Principal
- `orchestrate plan run` com `--phase/--subtask/--auto/--dry-run/-y/-q/-v`
- `_print_plan_view` — snapshot visual do plano antes e apos execucao

#### [OK] 6.5 Geracao de Plano por IA
- `orchestrator/project_planner.py` — `generate_project_plan`, `refine_project_plan`, `run_project_plan_critic_loop`
- `orchestrator/critic.py` — `critique_project_plan` com role `plan_critic`
- `orchestrator/prompts/project_planner_system.md` — prompt especializado para geracao de PLANO.md
- `orchestrator/prompts/plan_critic_system.md` — prompt de avaliacao estrutural do plano hierarquico
- `orchestrate plan generate DESCRIPTION [-p PREMISES] [-s STACK] [-y] [--no-critic]`

#### [OK] 7.1.1 — Novos tipos de evento no EventBus
- `orchestrator/events.py` — 11 novos EventType para o plan runner: PLAN_LOADED, TASK_STARTED, TASK_DONE, TASK_ESCALATED, TASK_SKIPPED, SUBPHASE_COMPLETE, PHASE_COMPLETE, PLAN_PAUSED, PLAN_RESUMED, PLAN_COMPLETE, PLAN_ABORTED
- Docstring atualizada com payload reference para os novos tipos

#### [OK] 7.1.2 — Endpoints REST para plan runner
- `orchestrator/plan_runner.py` — `run_plan` aceita `event_bus` e `pause_event` opcionais; emite eventos em cada etapa; `_maybe_pause_boundaries` e async; pause semantica "after current task"
- `orchestrator/server.py` — `PlanRunState` dataclass; `_active_plan_runs`; `_run_plan_bg`; 8 endpoints: POST/GET /api/plan/run, POST /api/plan/pause|resume|abort/{id}, GET /api/plan/load, POST /api/plan/generate, POST /api/plan/save

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
│   ├── events.py             # [OK] EventBus + 11 plan runner EventTypes (Fase 7)
│   ├── server.py             # [OK] FastAPI backend + /api/plan/* endpoints (Fase 7)
│   ├── plan.py               # [OK] Modelo hierarquico + parse_plan + write_plan (Fase 6)
│   ├── plan_runner.py        # [OK] Motor de execucao + event_bus/pause_event API (Fase 7)
│   ├── project_planner.py    # [OK] Geracao de PLANO.md por IA + loop Critic (Fase 6.5)
│   ├── providers/
│   │   ├── __init__.py       # [OK] Factory + plugin registry
│   │   ├── base.py           # [OK] BaseAgent
│   │   ├── anthropic.py      # [OK] ClaudeProvider
│   │   ├── google.py         # [OK] GeminiProvider
│   │   ├── openai.py         # [OK] OpenAIProvider
│   │   └── retry.py          # [OK] Retry com backoff
│   └── prompts/              # [OK] System prompts (6 arquivos)
├── dashboard/                # [OK] React + Vite (5.2–5.5)
├── configs/
├── logs/
├── docs/
│   ├── AI_Dev_Orchestrator_Plano.md
│   └── Fase5_Dashboard_Plano.md
├── tests/                    # [OK] 468 testes
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
- Plano Fase 7: `docs/Fase7_Dashboard_Plano_Hierarquico.md`
- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- Claude Agent SDK: https://pypi.org/project/claude-agent-sdk/
- Google GenAI SDK: https://github.com/googleapis/python-genai
