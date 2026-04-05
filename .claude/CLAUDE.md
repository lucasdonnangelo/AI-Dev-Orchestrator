# CLAUDE.md — Contexto para Claude Code

## O Que E Este Projeto

**AI Dev Orchestrator** — sistema CLI em Python que automatiza o ciclo de desenvolvimento usando multiplas IAs com papeis separados e validacao em camadas.

### Papeis das IAs

| Papel | O que faz | Provider |
|-------|-----------|----------|
| **Planner** | Gera plano estruturado a partir de uma task | Claude (Anthropic) |
| **Critico** | Critica e melhora o plano (2-5 rounds) | Gemini (Google) |
| **Executor** | Implementa o codigo seguindo o plano | Claude Code (Agent SDK) |
| **Reviewer** | Avalia qualidade do codigo gerado | Gemini (Google) |
| **Decisor** | Valida coerencia com o plano geral | Gemini (Google) |

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
- **claude-agent-sdk** v0.1.54 — Executor
- **google-genai** >= 1.0.0 — Gemini (Critico, Reviewer, Decisor)
- **openai** >= 1.50.0 — OpenAI como fallback opcional (implementado, nao usado por padrao)
- **click** — CLI framework
- **rich** — output formatado no terminal
- **python-dotenv** + **pyyaml** — configuracao

## Estrutura do Projeto

```
ai-dev-orchestrator/
├── orchestrator/
│   ├── __init__.py
│   ├── cli.py               # CLI com click (entrypoint: orchestrate)
│   ├── config.py             # Carrega .env + YAML, resolve Config
│   ├── models.py             # TaskPlan, ReviewResult, CycleRecord
│   ├── planner.py            # [OK] Planner — usa providers/
│   ├── executor.py           # [OK] Executor — claude-agent-sdk
│   ├── reviewer.py           # [OK] Reviewer — usa providers/
│   ├── orchestrator.py       # [OK] Loop Planner->Executor->Reviewer
│   ├── critic.py             # [FASE 2.2] Critico do Plano
│   ├── decisor.py            # [FASE 2.3] Decisor pos-review
│   ├── providers/
│   │   ├── __init__.py       # [OK] Factory make_provider()
│   │   ├── base.py           # [OK] BaseAgent(ABC)
│   │   ├── anthropic.py      # [OK] ClaudeProvider
│   │   ├── google.py         # [OK] GeminiProvider (gemini-2.5-flash)
│   │   └── openai.py         # [OK] OpenAIProvider (fallback)
│   └── prompts/
│       ├── planner_system.md     # [OK]
│       ├── reviewer_system.md    # [OK]
│       ├── executor_context.md   # [OK]
│       ├── critic_system.md      # [FASE 2.2]
│       └── decisor_system.md     # [FASE 2.3]
├── configs/
│   └── default.yaml
├── logs/
├── docs/
│   └── AI_Dev_Orchestrator_Plano_v2.md
├── SESSAO_ATUAL.md           # [FASE 2.4] Atualizado automaticamente
├── .env
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Status Atual

### [OK] Fase 1 — MVP Funcional (COMPLETA)
- Planner, Executor, Reviewer, Orquestrador, CLI — tudo funcionando
- Testado end-to-end com projeto cobaia

### [OK] Fase 2.1 — Arquitetura Multi-Provider (COMPLETA)
- BaseAgent abstrato com metodo `async call(prompt, system) -> str`
- ClaudeProvider (anthropic SDK)
- GeminiProvider (google-genai, modelo padrao: gemini-2.5-flash)
- OpenAIProvider (openai SDK, fallback opcional)
- Factory `make_provider(name, config)` em providers/__init__.py
- Config atualizada com campos por provider e por papel
- Planner e Reviewer ja migrados para usar providers
- Backward compatible — default continua anthropic se nao configurar

### [>>] Fase 2.2 — Critico do Plano (PROXIMA)
- Criar `orchestrator/critic.py`
- Criar `orchestrator/prompts/critic_system.md`
- Loop iterativo Planner <-> Critico (min 2, max 5 rounds)
- Critico usa Gemini via `make_provider(config.critic_provider, config)`
- Retorna `CriticResult` (nova dataclass em models.py)
- Integrar no orchestrator.py (entre Planner e Executor)

### [ ] Fase 2.3 — Decisor
### [ ] Fase 2.4 — SESSAO_ATUAL.md Automatizado
### [ ] Fase 2.5 — Robustez
### [ ] Fase 2.6 — Logging e Historico
### [ ] Fase 3 — Orquestracao Avancada
### [ ] Fase 4 — Extensibilidade

## Modelos de Dados (models.py)

### Existentes
```python
class TaskPlan:        # description, files_to_create, files_to_modify, steps, acceptance_criteria, estimated_complexity
class ReviewResult:    # approved, score, issues, suggestions, summary
class ReviewIssue:     # severity, description, file, line, suggestion
class CycleRecord:     # task, status, plan, review, attempt, started_at, finished_at, commit_hash
```

### Novos (Fase 2.2+)
```python
class CriticResult:    # consensus, observations, suggestions, score, round
class DecisionResult:  # approved, reasoning, inconsistencies
```

## Config (.env)

```
ANTHROPIC_API_KEY=sk-ant-...      # Obrigatorio
GOOGLE_API_KEY=AIza...            # Obrigatorio (Critico, Reviewer, Decisor usam Gemini)
OPENAI_API_KEY=sk-...             # Opcional (fallback)
ORCHESTRATOR_MODEL=claude-sonnet-4-6
GOOGLE_MODEL=gemini-2.5-flash
PLANNER_PROVIDER=anthropic        # default
CRITIC_PROVIDER=google            # default
REVIEWER_PROVIDER=google          # default
DECISOR_PROVIDER=google           # default
```

## Convencoes de Codigo

- Python 3.10+ com `from __future__ import annotations`
- Type hints em tudo
- Async/await para chamadas de API e Agent SDK
- Formatacao: ruff (line-length 100)
- Testes: pytest + pytest-asyncio
- Sem emojis Unicode no output (compatibilidade Windows cp1252)
- Marcadores ASCII: [OK], [X], [!]

## Referencias

- Plano completo: `docs/AI_Dev_Orchestrator_Plano.md`
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- Claude Agent SDK: https://pypi.org/project/claude-agent-sdk/
- Google GenAI SDK: https://github.com/googleapis/python-genai
