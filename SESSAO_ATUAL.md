# Sessao Atual — AI Dev Orchestrator

**Ultima atualizacao:** 04/04/2026
**Branch:** main

---

## Fluxo atual (implementado)

```
Voce (task)
  --> Planner (Claude) gera plano v1          [recebe session_context]
  --> Critico (Gemini) avalia [min 2, max 5 rounds]  [recebe session_context]
        se nao consenso: Planner refina --> Critico reavalia
  --> Plano Final
  --> Executor (Claude Agent SDK) implementa
        se reprovado (max 3x): Executor corrige com feedback
  --> Reviewer (Gemini) avalia codigo         [recebe session_context]
  --> Decisor (Gemini) valida coerencia com plano  [recebe session_context]
  --> Aprovado --> SESSAO_ATUAL.md atualizado automaticamente
               --> Voce confirma commit
  --> ESCALADO  --> Voce intervem manualmente
```

---

## Status das fases

| Fase | Descricao | Status |
|------|-----------|--------|
| 1 — MVP | Planner + Executor + Reviewer + Orquestrador + CLI | COMPLETA |
| 2.1 — Multi-Provider | BaseAgent, ClaudeProvider, GeminiProvider, OpenAIProvider, make_provider | COMPLETA |
| 2.2 — Critico do Plano | critic.py, critic_system.md, planner.refine_plan, loop min/max rounds | COMPLETA |
| 2.3 — Decisor | decisor.py, decisor_system.md, DecisionResult, integrado no orchestrator.py | COMPLETA |
| 2.4 — SESSAO_ATUAL.md auto | session.py, session_update_system.md, load/update em todos os agentes | COMPLETA |
| 2.5 — Robustez | retry com backoff, fix _get_diff Windows (os.devnull), fix diff no CLI | COMPLETA |
| 2.6 — Logging/Historico | logger.py, orchestrate history/status, commit hash | COMPLETA |
| 3+ | Multi-task, contexto inteligente, git avancado, metricas | pendente |

---

## Ultima tarefa aprovada

**Tarefa:** Fase 2.6 + correcoes do teste end-to-end
**Commit:** 2fcebef

**Arquivos criados:**
- orchestrator/logger.py
- tests/test_logger.py

**Arquivos modificados:**
- orchestrator/cli.py — logger integrado, commit hash capturado, `orchestrate history` e `orchestrate status` implementados
- orchestrator/providers/retry.py — parametros `delay_extractor` e `max_retry_delay`
- orchestrator/providers/google.py — `_extract_gemini_delay` para extrair retryDelay do 429 Gemini
- orchestrator/prompts/executor_context.md — instrucao para examinar convencoes do projeto antes de criar arquivos
- cobaia/divide.py + cobaia/test_divide.py — funcao divide com protecao contra divisao por zero

**Resultado dos testes:** 104 passed (orchestrator) + 28 passed (cobaia)

---

## Teste end-to-end executado

Ciclo completo rodado contra o projeto cobaia com a task:
"Criar uma funcao divide(a, b) que retorna a divisao de dois numeros, com protecao contra divisao por zero"

**O que funcionou:**
- Planner gerou plano estruturado
- Critic rodou 2 rounds com consenso (score 9/10)
- Executor criou os arquivos corretos
- Reviewer identificou bug de import (validacao funcionou)
- Retry logic ativou ao encontrar 429
- Logger salvou registro do ciclo escalado

**Bugs encontrados e corrigidos:**
1. Executor usava `from cobaia.divide import divide` em vez de `from divide import divide` — corrigido via executor_context.md
2. Retry delay ignorava o `retryDelay` informado pela API Gemini — corrigido com `_extract_gemini_delay`
3. Quota diaria Gemini free tier (20 req/dia) esgotada durante o teste — sistema agora detecta e nao tenta retry nesses casos

---

## Arquitetura atual

### Providers (`orchestrator/providers/`)

```
BaseAgent (ABC)
  async call(prompt, system) -> str

ClaudeProvider   -- anthropic SDK (AsyncAnthropic) + retry (RateLimitError, APITimeoutError, InternalServerError)
GeminiProvider   -- google-genai SDK + retry com _extract_gemini_delay (respeita retryDelay da API)
OpenAIProvider   -- openai SDK (AsyncOpenAI) + retry (RateLimitError, APITimeoutError, InternalServerError)

call_with_retry(fn, *, max_attempts, base_delay, max_delay, retryable, delay_extractor, max_retry_delay)
  -- delay_extractor: extrai delay real da excecao (ex: retryDelay do Gemini 429)
  -- max_retry_delay: se delay > limite, re-raise imediato (quota diaria esgotada)

make_provider(name, config) -> BaseAgent
```

### Agentes

| Agente | Arquivo | Provider configuravel | Recebe session_context |
|--------|---------|----------------------|------------------------|
| Planner | `planner.py` | `config.planner_provider` (default: anthropic) | sim |
| Critico | `critic.py` | `config.critic_provider` (default: google) | sim |
| Executor | `executor.py` | sempre Claude Agent SDK | nao |
| Reviewer | `reviewer.py` | `config.reviewer_provider` (default: google) | sim |
| Decisor | `decisor.py` | `config.decisor_provider` (default: google) | sim |

### Logger (`orchestrator/logger.py`)

```
logger.save(record, diff, log_dir) -> Path
  Salva CycleRecord + diff em logs/YYYYMMDD_HHMMSS_ffffff_<slug>.json
  Chamado pelo CLI em todos os caminhos (aprovado, escalado por Reviewer, escalado por Decisor)

logger.list_runs(log_dir, limit) -> list[dict]
  Lista execucoes mais recentes (newest-first por nome de arquivo)

logger.load_last(log_dir) -> dict | None
  Retorna a execucao mais recente

orchestrate history --log-dir logs -n 20   -- tabela com as ultimas N execucoes
orchestrate status  --log-dir logs          -- painel detalhado da ultima execucao
```

### Config (campos relevantes)

```
ANTHROPIC_API_KEY     -- obrigatorio
GOOGLE_API_KEY        -- obrigatorio (Critico + Reviewer + Decisor usam Gemini)
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
DecisionResult -- approved, reasoning, inconsistencies
CycleRecord    -- task, status, plan, review, decision, attempt,
                  started_at, finished_at, commit_hash
```

---

## Proximos passos imediatos

1. **Fase 3.1 — Contexto Inteligente:** carregar README, estrutura de pastas e arquivos relevantes como contexto automatico
2. **Fase 3.2 — Multi-task (Batch):** aceitar arquivo com lista de tasks, executar sequencialmente
3. **Fase 3.3 — Git Avancado:** branch por task, Conventional Commits, PR description
4. **Testar ciclo end-to-end completo** apos reset da quota Gemini (free tier: 20 req/dia)

---

## Como rodar

```bash
# Instalar dependencias
pip install -e .

# Rodar uma task
python -m orchestrator.cli run "sua task aqui" -d /caminho/do/projeto -y

# Ver ultima execucao
python -m orchestrator.cli status

# Ver historico
python -m orchestrator.cli history -n 10

# Rodar testes unitarios
pytest tests/ -v
```

---

## Projeto cobaia

Pasta `cobaia/` na raiz — submodulo Git separado usado para testar o orquestrador.
Contem: `main.py`, `hello.py`, `add.py`, `multiply.py`, `subtract.py`, `divide.py` e respectivos testes pytest.
