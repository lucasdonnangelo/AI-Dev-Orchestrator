# Sessao Atual — AI Dev Orchestrator

**Ultima atualizacao:** 05/04/2026
**Branch:** main

---

## Fluxo atual (implementado)

```
Voce (task)
  --> context.load_project_context()              [stack, README, arvore de dirs]
  --> Planner (Claude) gera plano v1              [recebe session_context + project_ctx]
  --> Critico (Gemini) avalia [min 2, max 5 rounds]  [recebe session_context]
        se nao consenso: Planner refina --> Critico reavalia
  --> Plano Final
  --> Executor (Claude Agent SDK) implementa
        se reprovado (max 3x): Executor corrige com feedback
  --> Reviewer (Gemini) avalia codigo             [recebe session_context]
  --> Decisor (Gemini) valida coerencia com plano [recebe session_context]
  --> Aprovado --> SESSAO_ATUAL.md atualizado automaticamente
               --> Voce confirma commit (mensagem convencional automatica)
               --> Se git_auto_branch=True: PR description gerada
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
| 3.1 — Contexto Inteligente | context.py: stack detection, README, arvore de dirs; integrado no Planner | COMPLETA |
| 3.2 — Multi-task Batch | orchestrate batch: arquivo .txt/.json, execucao sequencial, resumo final | COMPLETA |
| 3.3 — Git Avancado | git.py: branch por task, conventional commits, PR description | COMPLETA |
| 3.4 — Melhorias de CLI | stage messages coloridas [1/5..5/5], --quiet/-q, --verbose/-v | COMPLETA |
| 3.5 — Metricas | orchestrate metrics: stats agregadas de todos os logs | COMPLETA |
| 4+ | Templates, plugins, modo interativo | pendente |

---

## Ultima tarefa aprovada

**Tarefa:** Fase 3 completa (3.1 a 3.5)
**Commits:** feat: Phase 3.1 (context loader) + fases 3.2-3.5 pendentes de commit

**Arquivos criados:**
- orchestrator/context.py
- orchestrator/git.py

**Arquivos modificados:**
- orchestrator/orchestrator.py — context loader integrado, stage messages coloridas [1/5..5/5]
- orchestrator/config.py — campos git_auto_branch e git_conventional_commits
- orchestrator/logger.py — list_runs suporta limit=0 (todos os logs)
- orchestrator/cli.py — batch, metrics, quiet/verbose, git hooks no commit

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

| Agente | Arquivo | Provider configuravel | Recebe session_context | Recebe project_ctx |
|--------|---------|----------------------|------------------------|--------------------|
| Planner | `planner.py` | `config.planner_provider` (default: anthropic) | sim | sim |
| Critico | `critic.py` | `config.critic_provider` (default: google) | sim | nao |
| Executor | `executor.py` | sempre Claude Agent SDK | nao | nao |
| Reviewer | `reviewer.py` | `config.reviewer_provider` (default: google) | sim | nao |
| Decisor | `decisor.py` | `config.decisor_provider` (default: google) | sim | nao |

### Context Loader (`orchestrator/context.py`)

```
load_project_context(project_dir) -> str
  -- _detect_stack(): pyproject.toml, package.json, go.mod, Cargo.toml, etc.
  -- _load_readme(): README.md/.rst/.txt (truncado em 6k chars)
  -- _build_tree(): arvore de dirs (ignora .git, __pycache__, node_modules etc; max 80 itens, profundidade 4)
  -- cap total: 24k chars
  Chamado em orchestrator.run_cycle() antes do Planner
```

### Git Helpers (`orchestrator/git.py`)

```
detect_commit_type(task) -> str      -- keywords PT+EN: fix, docs, test, refactor, chore, perf, feat
make_branch_name(task) -> str        -- "feat/criar-funcao-divide-a-b"
make_commit_message(task) -> str     -- "feat: Criar funcao divide(a, b)" (max 72 chars)
create_branch(project_dir, branch)   -- git checkout -b
get_current_branch(project_dir)      -- branch atual
build_pr_description(task, record)   -- markdown com plan/review/decision sem chamada de AI
```

### CLI (`orchestrator/cli.py`)

```
orchestrate run TASK [OPTIONS]
  -d   project dir
  -y   skip confirmations
  -v   verbose (mostra issues/suggestions sempre)
  -q   quiet (suprime panels, so erros e commit)

orchestrate batch TASKS_FILE [OPTIONS]
  -d   project dir
  -y   skip all confirmations
  -q / -v   propagados para cada task
  --stop-on-failure   para no primeiro erro sem perguntar
  Formatos: .txt (uma task por linha, # = comentario) ou .json (array)

orchestrate metrics [--log-dir logs]
  -- total/aprovados/escalados + %, taxa 1a tentativa
  -- score medio, tentativas medias, duracao media
  -- barra visual proporcional
  -- tabela "Last 5 Runs"

orchestrate history [-n 20] [--log-dir logs]
orchestrate status [--log-dir logs]
```

### Stage messages (orchestrator.py)

```
[blue]    [1/5] Planning...[/blue]
[cyan]    [2/5] Critic loop...[/cyan]
[green]   [3/5] Executing (attempt N/M)...[/green]
[yellow]  [4/5] Reviewing...[/yellow]
[magenta] [5/5] Decisor...[/magenta]
```

### Logger (`orchestrator/logger.py`)

```
logger.save(record, diff, log_dir) -> Path
logger.list_runs(log_dir, limit) -> list[dict]   -- limit=0 retorna todos
logger.load_last(log_dir) -> dict | None
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

GIT_AUTO_BRANCH=false           # true: cria branch feat/task-slug por task
GIT_CONVENTIONAL_COMMITS=true   # true: mensagem feat:/fix:/etc automatica
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

1. **Fase 4.1 — Templates de Projeto:** `orchestrate init --template fastapi/python-cli/react`
2. **Fase 4.2 — Prompts Customizaveis:** override de system prompts via `.orchestrator.yaml`
3. **Fase 4.3 — Plugin de Providers:** interface para adicionar Mistral, Llama, etc.
4. **Fase 4.4 — Modo Interativo:** editar plano/codigo antes de resubmeter, chat com agente
5. **Testar ciclo end-to-end** apos reset da quota Gemini (free tier: 20 req/dia)

---

## Como rodar

```bash
# Instalar dependencias
pip install -e .

# Rodar uma task
python -m orchestrator.cli run "sua task aqui" -d /caminho/do/projeto -y

# Rodar batch de tasks
python -m orchestrator.cli batch tasks.txt -d /caminho/do/projeto -y

# Ver metricas agregadas
python -m orchestrator.cli metrics

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
