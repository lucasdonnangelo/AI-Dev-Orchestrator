# CLAUDE.md — Contexto para Claude Code

## O Que E Este Projeto

**AI Dev Orchestrator** — sistema CLI em Python que automatiza o ciclo de desenvolvimento usando multiplas IAs com papeis separados e validacao em camadas.

### Papeis das IAs (Visao Final)

| Papel | O que faz | Provider |
|-------|-----------|----------|
| **Planner** | Gera plano estruturado a partir de uma task | Claude (Anthropic) |
| **Critico** | Critica e melhora o plano (2-5 rounds) | Gemini ou ChatGPT |
| **Executor** | Implementa o codigo seguindo o plano | Claude Code (Agent SDK) |
| **Reviewer** | Avalia qualidade do codigo gerado | Gemini ou ChatGPT |
| **Decisor** | Valida coerencia com o plano geral | Gemini ou ChatGPT |

**Principio:** Claude planeja e executa. IAs de outro provider criticam, revisam e validam. Elimina vies.

### Fluxo Completo

```
Voce (task)
  --> Planner (Claude) gera plano
  --> Critico (Gemini/GPT) critica [2-5 rounds ate consenso]
  --> Plano Final
  --> Executor (Agent SDK) implementa
  --> Reviewer (Gemini/GPT) avalia codigo [max 3 retries]
  --> Decisor (Gemini/GPT) valida coerencia com plano
  --> Atualiza SESSAO_ATUAL.md
  --> Proxima tarefa (ou escala para voce)
```

## Stack

- **Python 3.10+**
- **anthropic** SDK — Planner e fallback
- **claude-agent-sdk** v0.1.54 — Executor
- **google-genai** — Gemini (Critico, Reviewer, Decisor) [Fase 2]
- **openai** — ChatGPT como alternativa [Fase 2]
- **click** — CLI framework
- **rich** — output formatado no terminal
- **python-dotenv** + **pyyaml** — configuracao

## Estrutura do Projeto

```
ai-dev-orchestrator/
├── orchestrator/
│   ├── __init__.py          # Package init + __version__
│   ├── cli.py               # CLI com click (entrypoint: orchestrate)
│   ├── config.py            # Carrega .env + YAML, resolve Config
│   ├── models.py            # TaskPlan, ReviewResult, CycleRecord
│   ├── planner.py           # [OK] Planner — AsyncAnthropic
│   ├── executor.py          # [OK] Executor — claude-agent-sdk
│   ├── reviewer.py          # [OK] Reviewer — AsyncAnthropic (sera migrado para multi-provider)
│   ├── orchestrator.py      # [OK] Loop Planner->Executor->Reviewer
│   ├── critic.py            # [FASE 2] Critico do Plano
│   ├── decisor.py           # [FASE 2] Decisor pos-review
│   ├── providers/           # [FASE 2] Arquitetura multi-provider
│   │   ├── __init__.py
│   │   ├── base.py          # BaseAgent (interface abstrata)
│   │   ├── anthropic.py     # ClaudeProvider
│   │   ├── google.py        # GeminiProvider
│   │   └── openai.py        # OpenAIProvider
│   └── prompts/
│       ├── planner_system.md    # [OK] System prompt do Planner
│       ├── reviewer_system.md   # [OK] System prompt do Reviewer
│       ├── executor_context.md  # [OK] Contexto base do Executor
│       ├── critic_system.md     # [FASE 2] System prompt do Critico
│       └── decisor_system.md    # [FASE 2] System prompt do Decisor
├── configs/
│   └── default.yaml
├── logs/
├── docs/
│   └── AI_Dev_Orchestrator_Plano_v2.md  # Plano completo do projeto
├── SESSAO_ATUAL.md          # [FASE 2] Estado atual (atualizado automaticamente)
├── .env
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Status Atual

### [OK] Fase 1 — MVP Funcional (COMPLETA)

Tudo implementado e testado:
- Planner gera TaskPlan via API Anthropic
- Executor implementa codigo via Agent SDK com bypassPermissions
- Reviewer avalia codigo via API Anthropic
- Orquestrador conecta os 3 com loop de correcao (max 3 retries)
- CLI exibe plano, review, diff e pede confirmacao de commit
- Tratamento de APIError e KeyboardInterrupt

### [>>] Fase 2 — Multi-Model e Robustez (PROXIMA)

#### 2.1 Arquitetura Multi-Provider
- Criar `orchestrator/providers/base.py` com `BaseAgent` abstrato
- Implementar `ClaudeProvider`, `GeminiProvider`, `OpenAIProvider`
- Config para escolher provider por papel

#### 2.2 Critico do Plano
- `orchestrator/critic.py` — loop iterativo Planner <-> Critico (2-5 rounds)
- Critico usa Gemini/ChatGPT, retorna `CriticResult`
- Parada: consensus=true ou max rounds

#### 2.3 Decisor
- `orchestrator/decisor.py` — valida coerencia pos-review
- Recebe: plano + diff + ReviewResult + SESSAO_ATUAL.md
- Retorna `DecisionResult` (approved + inconsistencies)

#### 2.4 SESSAO_ATUAL.md Automatizado
- Gerar/atualizar apos cada tarefa aprovada
- Conteudo: o que foi feito, estado atual, proximas etapas

#### 2.5 Robustez
- Retry em erros de API (todos os providers)
- Corrigir _get_diff para Windows (substituir /dev/null)
- Timeout configuravel

#### 2.6 Logging e Historico
- Salvar execucoes em logs/ (JSON)
- Comandos orchestrate history e orchestrate status

### [ ] Fase 3 — Orquestracao Avancada
- Multi-task (batch), contexto inteligente, git avancado, metricas

### [ ] Fase 4 — Extensibilidade
- Templates de projeto, plugins de providers, modo interativo

## Modelos de Dados (models.py)

### Existentes (implementados)

```python
class TaskPlan:        # Output do Planner
    description, files_to_create, files_to_modify, steps,
    acceptance_criteria, estimated_complexity

class ReviewResult:    # Output do Reviewer
    approved, score, issues: list[ReviewIssue], suggestions, summary

class CycleRecord:     # Log de uma execucao
    task, status, plan, review, attempt, started_at, finished_at, commit_hash
```

### Novos (Fase 2)

```python
class CriticResult:    # Output do Critico
    consensus: bool
    observations: list[str]
    suggestions: list[str]
    score: int  # 1-10
    round: int

class DecisionResult:  # Output do Decisor
    approved: bool
    reasoning: str
    inconsistencies: list[str]
```

## Config (config.py)

Carrega em camadas: `configs/default.yaml` -> `.orchestrator.yaml` do projeto -> env vars.

Campos atuais: api_key, model, max_retries, executor_allowed_tools, project_dir.

Campos novos (Fase 2): google_api_key, openai_api_key, planner_provider, critic_provider, reviewer_provider, decisor_provider, critic_max_rounds.

## Convencoes de Codigo

- Python 3.10+ com `from __future__ import annotations`
- Type hints em tudo
- Async/await para chamadas de API e Agent SDK
- Formatacao: ruff (line-length 100)
- Testes: pytest + pytest-asyncio
- Sem emojis Unicode no output (compatibilidade Windows cp1252)
- Marcadores ASCII: [OK], [X], [!] em vez de emojis

## Referencias

- Plano completo: `docs/AI_Dev_Orchestrator_Plano_v2.md`
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- Claude Agent SDK: https://pypi.org/project/claude-agent-sdk/ (v0.1.54)
- Agent SDK docs: https://platform.claude.com/docs/en/agent-sdk/overview
