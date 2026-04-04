# CLAUDE.md — Contexto para Claude Code

## O Que É Este Projeto

**AI Dev Orchestrator** — um sistema CLI em Python que automatiza o ciclo de desenvolvimento usando 3 agentes de IA:

1. **Planner** (API Anthropic) → recebe uma task em linguagem natural, gera um plano estruturado (JSON)
2. **Executor** (Claude Agent SDK) → recebe o plano e implementa o código no projeto-alvo
3. **Reviewer** (API Anthropic) → recebe o plano + diff do código, avalia qualidade e aprova/rejeita

O desenvolvedor humano confirma o commit no final.

```
Você (task) → Planner → Executor → Reviewer → Aprovado? → Você confirma commit
                                      ↑          ↓ NÃO
                                      └──────────┘ (max 3x, depois escala pro humano)
```

## Stack

- **Python 3.10+**
- **anthropic** SDK (Messages API) — para Planner e Reviewer
- **claude-agent-sdk** (Agent SDK Python, v0.1.54) — para Executor
- **click** — framework CLI
- **rich** — output bonito no terminal
- **python-dotenv** + **pyyaml** — configuração

## Estrutura do Projeto

```
ai-dev-orchestrator/
├── orchestrator/
│   ├── __init__.py          # Package init + __version__
│   ├── cli.py               # CLI com click (entrypoint: orchestrate)
│   ├── config.py            # Carrega .env + YAML, resolve Config
│   ├── models.py            # Dataclasses: TaskPlan, ReviewResult, CycleRecord
│   ├── planner.py           # ⬜ STUB — Fase 1.2
│   ├── executor.py          # ⬜ STUB — Fase 1.3
│   ├── reviewer.py          # ⬜ STUB — Fase 1.4
│   ├── orchestrator.py      # ⬜ STUB — Fase 1.5
│   └── prompts/
│       ├── planner_system.md    # ✅ System prompt do Planner (pronto)
│       ├── reviewer_system.md   # ✅ System prompt do Reviewer (pronto)
│       └── executor_context.md  # ✅ Contexto base do Executor (pronto)
├── configs/
│   └── default.yaml         # ✅ Config padrão
├── logs/
├── docs/
│   └── AI_Dev_Orchestrator_Plano.md  # Plano completo do projeto
├── .env                     # API key (não commitado)
├── .env.example             # Template do .env
├── .gitignore               # ✅
├── requirements.txt         # ✅
├── pyproject.toml           # ✅ Entrypoint: orchestrate = orchestrator.cli:cli
└── README.md                # ✅
```

## Status Atual

### ✅ Fase 1.1 — Setup (COMPLETA)
- Repositório criado e vinculado ao GitHub
- Estrutura de pastas criada
- `pyproject.toml` configurado com entrypoint CLI
- `pip install -e ".[dev]"` funcionando
- Config (.env + YAML) funcionando
- Models (TaskPlan, ReviewResult, CycleRecord) implementados
- System prompts dos agentes escritos
- CLI básica com click (orchestrate run/status/history)

### ⬜ Fase 1.2 — Planner Agent (PRÓXIMA)
- Implementar `orchestrator/planner.py`
- Chamar API Anthropic com system prompt de `prompts/planner_system.md`
- Enviar a task + contexto do projeto como user message
- Parsear resposta JSON em `TaskPlan` (dataclass em `models.py`)
- Modelo: `claude-sonnet-4-6`
- **Teste:** `"Criar um endpoint GET /health que retorna status 200"` → deve gerar TaskPlan válido

### ⬜ Fase 1.3 — Executor Agent
- Implementar `orchestrator/executor.py`
- Usar `claude-agent-sdk` (query + ClaudeAgentOptions)
- Receber TaskPlan, montar prompt com contexto do executor
- Executar no diretório do projeto-alvo
- Capturar diff das mudanças
- Controlar permissões com `allowed_tools`
- **API do Agent SDK:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Write", "Bash"],
    cwd="/path/to/project",
)

async for message in query(prompt=executor_prompt, options=options):
    # processar mensagens do agente
```

### ⬜ Fase 1.4 — Reviewer Agent
- Implementar `orchestrator/reviewer.py`
- Chamar API Anthropic com system prompt de `prompts/reviewer_system.md`
- Enviar plano original + diff como user message
- Parsear resposta JSON em `ReviewResult` (dataclass em `models.py`)
- Regras: critical issue → rejeição automática; score < 7 → rejeição

### ⬜ Fase 1.5 — Orquestrador + CLI
- Implementar `orchestrator/orchestrator.py` que conecta os 3 agentes
- Loop de correção: se Reviewer rejeita, reenvia pro Executor com feedback (max 3x)
- Conectar tudo no `cli.py` (comando `orchestrate run`)
- Mostrar diff e pedir confirmação de commit
- Gerar commit message automática

## Modelos de Dados Importantes (já implementados em models.py)

### TaskPlan (output do Planner)
```python
@dataclass
class TaskPlan:
    description: str
    files_to_create: list[str]
    files_to_modify: list[str]
    steps: list[str]
    acceptance_criteria: list[str]
    estimated_complexity: Complexity  # low | medium | high
```

### ReviewResult (output do Reviewer)
```python
@dataclass
class ReviewResult:
    approved: bool
    score: int  # 1-10
    issues: list[ReviewIssue]  # severity: critical | warning | info
    suggestions: list[str]
    summary: str
```

### CycleRecord (log de uma execução)
```python
@dataclass
class CycleRecord:
    task: str
    status: CycleStatus
    plan: TaskPlan | None
    review: ReviewResult | None
    attempt: int
    started_at: str
    finished_at: str | None
    commit_hash: str | None
```

## Config (já implementado em config.py)

A classe `Config` carrega em camadas: `configs/default.yaml` → `.orchestrator.yaml` do projeto → variáveis de ambiente.

Campos principais:
- `api_key` — ANTHROPIC_API_KEY
- `model` — modelo para Planner/Reviewer (default: claude-sonnet-4-6)
- `max_retries` — tentativas de correção (default: 3)
- `executor_allowed_tools` — ferramentas permitidas pro Executor
- `project_dir` — diretório do projeto-alvo

## Convenções de Código

- Python 3.10+ (use `from __future__ import annotations` para forward refs)
- Type hints em tudo
- Async/await para chamadas de API e Agent SDK
- Formatação: ruff (line-length 100)
- Testes: pytest + pytest-asyncio

## Referências Importantes

- Plano completo: `docs/AI_Dev_Orchestrator_Plano.md`
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- Claude Agent SDK: https://pypi.org/project/claude-agent-sdk/ (v0.1.54)
- Agent SDK docs: https://platform.claude.com/docs/en/agent-sdk/overview
