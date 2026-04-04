# Sessao Atual — AI Dev Orchestrator

**Ultima atualizacao:** 04/04/2026
**Branch:** main

---

## Fluxo atual (implementado)

```
Voce (task)
  --> Planner (Claude) gera plano v1
  --> Critico (Gemini) avalia [min 2 rounds, max 5]
        se nao consenso: Planner refina --> Critico reavalia
  --> Plano Final
  --> Executor (Claude Agent SDK) implementa
        se reprovado (max 3x): Executor corrige com feedback
  --> Reviewer (Gemini) avalia codigo
  --> Aprovado --> Voce confirma commit
  --> ESCALADO  --> Voce intervem manualmente
```

---

## Status das fases

| Fase | Descricao | Status |
|------|-----------|--------|
| 1 — MVP | Planner + Executor + Reviewer + Orquestrador + CLI | COMPLETA |
| 2.1 — Multi-Provider | BaseAgent, ClaudeProvider, GeminiProvider, OpenAIProvider, make_provider | COMPLETA |
| 2.2 — Critico do Plano | critic.py, critic_system.md, planner.refine_plan, loop min/max rounds | COMPLETA |
| 2.3 — Decisor | decisor.py, decisor_system.md, DecisionResult | PROXIMA |
| 2.4 — SESSAO_ATUAL.md auto | Gerar/atualizar apos cada aprovacao | pendente |
| 2.5 — Robustez | Retry de API, fix _get_diff Windows, fix diff no CLI | pendente |
| 2.6 — Logging/Historico | logs/ JSON, orchestrate history/status | pendente |
| 3+ | Multi-task, contexto inteligente, git avancado, metricas | pendente |

---

## Arquitetura atual

### Providers (`orchestrator/providers/`)

```
BaseAgent (ABC)
  async call(prompt, system) -> str

ClaudeProvider   -- anthropic SDK (AsyncAnthropic)
GeminiProvider   -- google-genai SDK (client.aio.models.generate_content)
OpenAIProvider   -- openai SDK (AsyncOpenAI) [fallback, nao usado por padrao]

make_provider(name, config) -> BaseAgent
  "anthropic" -> ClaudeProvider(config.api_key, config.model)
  "google"    -> GeminiProvider(config.google_api_key, config.google_model)
  "openai"    -> OpenAIProvider(config.openai_api_key, config.openai_model)
```

### Agentes

| Agente | Arquivo | Provider configuravel |
|--------|---------|----------------------|
| Planner | `planner.py` | `config.planner_provider` (default: anthropic) |
| Critico | `critic.py` | `config.critic_provider` (default: google) |
| Executor | `executor.py` | sempre Claude Agent SDK |
| Reviewer | `reviewer.py` | `config.reviewer_provider` (default: google) |
| Decisor | `decisor.py` | `config.decisor_provider` (default: google) [NAO IMPL] |

### Config (campos relevantes)

```
ANTHROPIC_API_KEY     -- obrigatorio
GOOGLE_API_KEY        -- obrigatorio (Critico + Reviewer usam Gemini)
OPENAI_API_KEY        -- opcional (fallback)

PLANNER_PROVIDER=anthropic
CRITIC_PROVIDER=google
REVIEWER_PROVIDER=google
DECISOR_PROVIDER=google

GOOGLE_MODEL=gemini-2.5-flash
CRITIC_MIN_ROUNDS=2
CRITIC_MAX_ROUNDS=5
ORCHESTRATOR_MAX_RETRIES=3
```

### Modelos de dados (`models.py`)

```python
TaskPlan       -- description, files_to_create, files_to_modify, steps,
                  acceptance_criteria, estimated_complexity
CriticResult   -- consensus, observations, suggestions, score, round
ReviewResult   -- approved, score, issues (list[ReviewIssue]), suggestions, summary
ReviewIssue    -- severity, description, file, line, suggestion
CycleRecord    -- task, status, plan, review, attempt, started_at, finished_at, commit_hash
# pendente:
DecisionResult -- approved, reasoning, inconsistencies
```

---

## Proximos passos imediatos

1. **2.3 — Decisor:** `decisor.py` + `decisor_system.md` + `DecisionResult` + integrar no orchestrator.py
2. **2.4 — SESSAO_ATUAL.md auto:** gerar/atualizar este arquivo apos cada aprovacao
3. **2.5 — Robustez:** retry de API, fix `_get_diff` Windows (`/dev/null` -> `NUL`), fix exibicao de diff no CLI
4. **2.6 — Logging:** salvar execucoes em `logs/` (JSON), implementar `orchestrate history` e `orchestrate status`

---

## Como rodar

```bash
# Instalar dependencias
pip install -e .

# Rodar uma task
python -m orchestrator.cli run "sua task aqui" -d /caminho/do/projeto -y

# Rodar testes unitarios
pytest tests/ -v
```

---

## Projeto cobaia

Pasta `cobaia/` na raiz — projeto Git separado usado para testar o orquestrador.
Contem: `main.py`, `hello.py`, `add.py`, `multiply.py`, `subtract.py` e respectivos testes pytest.
