# Sessao Atual — AI Dev Orchestrator

**Ultima atualizacao:** 10/04/2026
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
                --> Modo interativo: editar plano/codigo, chat com agente, resubmeter
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
| 4.1 — Templates de Projeto | orchestrate init --template fastapi/python-cli/react | COMPLETA |
| 4.2 — Prompts Customizaveis | override de system prompts via .orchestrator.yaml, 3-layer resolution | COMPLETA |
| 4.3 — Plugin de Providers | registro dinamico de providers em runtime via config | COMPLETA |
| 4.4 — Modo Interativo | chat REPL com agentes, editar plano/codigo pos-escalacao, retry/edit | COMPLETA |
| 5 — Dashboard Visual | FastAPI backend + React frontend + WebSocket streaming | PROXIMA |

---

## Ultima tarefa aprovada

**Tarefa:** Fase 4.4 — Modo Interativo (chat REPL, post-escalation retry/edit)
**Commit:** 29c6938 feat: Phase 4.4 - interactive mode with chat REPL, post-escalation retry/edit

**Arquivos criados/modificados na Fase 4:**
- orchestrator/templates.py — templates FastAPI, Python CLI, React
- orchestrator/chat.py — REPL interativo e single-turn com agentes
- orchestrator/config.py — suporte a 3-layer resolution de prompts
- orchestrator/providers/__init__.py — plugin registry + registro dinamico
- orchestrator/cli.py — comandos init, chat; modo interativo pos-escalacao

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
Plugin registry: register_provider(name, cls) para providers externos em runtime
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

### Templates (`orchestrator/templates.py`)

```
Template(name, description, files: dict[str, str])
  -- fastapi     : pyproject.toml + app/main.py + tasks.txt + .orchestrator.yaml
  -- python-cli  : pyproject.toml + src/main.py + tasks.txt + .orchestrator.yaml
  -- react       : package.json + src/App.jsx + tasks.txt + .orchestrator.yaml

orchestrate init --template <name> [-d project_dir]
  -- cria estrutura de arquivos do template no diretorio alvo
```

### Chat / Modo Interativo (`orchestrator/chat.py`)

```
chat_with_agent(role, message, config, project_dir) -> str
  -- single-turn: envia mensagem para qualquer agente e retorna resposta
  -- roles: planner, critic, reviewer, decisor

interactive_chat(role, config, project_dir)
  -- REPL interativo: loop de conversa com agente escolhido
  -- /exit ou /quit para sair

post_escalation_menu(record, config, project_dir)
  -- pos-escalacao: opcoes de editar plano, editar codigo, chat, resubmeter
```

### Config — 3-layer resolution

```
1. Defaults globais (codigo)
2. ~/.orchestrator/config.yaml (usuario)
3. <project_dir>/.orchestrator.yaml (projeto) -- maior prioridade

Campos de override de prompts:
  planner_prompt_extra: "..."   -- append ao system prompt do Planner
  critic_prompt_extra: "..."    -- append ao system prompt do Critico
  reviewer_prompt_extra: "..."  -- append ao system prompt do Reviewer
  decisor_prompt_extra: "..."   -- append ao system prompt do Decisor
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

orchestrate init --template <name> [-d project_dir]
  -- cria estrutura de projeto a partir de template

orchestrate chat --role <role> [-d project_dir]
  -- REPL interativo com agente escolhido (planner/critic/reviewer/decisor)

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

1. **Fase 5.1 — Backend API e WebSocket:**
   - `orchestrator/events.py` — EventBus pub/sub com tipos de evento por etapa
   - `orchestrator/server.py` — FastAPI com REST + WebSocket
   - Endpoints: /api/run, /api/batch, /api/cancel, /api/pause, /api/resume, /api/projects, /api/history, /api/metrics
   - WS /ws/run/{run_id} — streaming de eventos tempo real
   - Comando `orchestrate dashboard` no cli.py

2. **Fase 5.2 — Frontend Dashboard Base:**
   - React + Vite + Tailwind em `dashboard/`
   - Tela inicial: campo de task, selecao de projeto, botao executar
   - Painel de execucao: 5 cards com status de cada agente em tempo real
   - Controles: pausar, cancelar, editar plano
   - Monitor de tokens e custo

3. **Fases 5.3 a 5.5** — gestao de projetos, execucao por fases, historico e metricas visual

Plano detalhado: `docs/Fase5_Dashboard_Plano.md`

---

## Como rodar

```bash
# Instalar dependencias
pip install -e .

# Rodar uma task
python -m orchestrator.cli run "sua task aqui" -d /caminho/do/projeto -y

# Rodar batch de tasks
python -m orchestrator.cli batch tasks.txt -d /caminho/do/projeto -y

# Iniciar projeto a partir de template
python -m orchestrator.cli init --template fastapi -d /caminho/do/novo/projeto

# Chat interativo com agente
python -m orchestrator.cli chat --role planner -d /caminho/do/projeto

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
6/6 tasks do batch cobaia aprovadas em validacao end-to-end.
