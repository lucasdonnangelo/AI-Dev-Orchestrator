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

406 testes passando. 6/6 tasks do batch cobaia aprovadas. Sistema validado end-to-end.

### [>>] Fase 6 — Orquestracao por Plano Hierarquico (EM ANDAMENTO)

Plano detalhado em: `docs/Fase6_Plano_Hierarquico.md`

#### [OK] 6.1 Parser e Modelo de Dados
- `orchestrator/plan.py` — PlanTaskStatus, PlanTask, SubPhase, Phase, ProjectPlan
- `parse_plan(path)` / `parse_plan_text(text)` — parser Markdown hierarquico
- `write_plan(plan, path)` — writer in-place (preserva formatacao, atualiza so checkboxes)
- CLI: `orchestrate plan status` / `plan next` / `plan reset TASK_ID`
- `tests/test_plan.py` — 94 testes

#### [OK] 6.2 Motor de Execucao por Plano (COMPLETA)
- `orchestrator/plan_runner.py` — RunPlanOptions, run_plan, _build_phase_context, pausas, retomada idempotente
- `orchestrator/plan.py` — fix: parser reconhece `[-]` como SKIPPED
- `tests/test_plan_runner.py` — 32 testes. Total: 406 testes

#### [OK] 6.3 Critic de Coerencia Entre Tasks (COMPLETA)
- `orchestrator/critic.py` — `critique_plan` e `run_critic_loop` aceitam `phase_context: str | None`
- `orchestrator/orchestrator.py` — `run_cycle` propaga `phase_context` para o Critic
- `orchestrator/prompts/critic_system.md` — criterio Coherence adicionado
- `orchestrator/plan_runner.py` — `_get_commit_files`, `_build_phase_context` enriquecido com arquivos por commit

#### [OK] 6.4 Comando CLI Principal (COMPLETA)
- `orchestrate plan run` com `--phase/--subtask/--auto/--dry-run/-y/-q/-v`
- `_print_plan_view` — snapshot visual do plano antes e apos execucao

#### [>>] 6.5 Geracao de Plano por IA (PROXIMA)

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
│   ├── events.py             # [OK] EventBus
│   ├── server.py             # [OK] FastAPI backend
│   ├── plan.py               # [OK] Modelo hierarquico + parse_plan + write_plan (Fase 6)
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
