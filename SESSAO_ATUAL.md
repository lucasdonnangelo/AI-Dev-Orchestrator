# Sessão Atual — AI Dev Orchestrator

**Última atualização:** 04/04/2026  
**Branch:** main

---

## O que é o projeto

CLI Python que automatiza o ciclo de desenvolvimento com 3 agentes de IA:

```
Você (task) → Planner → Executor → Reviewer → Aprovado? → Você confirma commit
                                      ↑           ↓ NÃO
                                      └───────────┘ (max 3x, depois escala pro humano)
```

| Agente | SDK | Papel |
|--------|-----|-------|
| Planner | `anthropic` Messages API | Decompõe a task em `TaskPlan` (JSON) |
| Executor | `claude-agent-sdk` | Implementa o código no projeto-alvo |
| Reviewer | `anthropic` Messages API | Avalia o diff e devolve `ReviewResult` |

---

## Status das fases

| Fase | Descrição | Status |
|------|-----------|--------|
| 1.1 | Setup do projeto | COMPLETA (commitada) |
| 1.2 | Planner agent | COMPLETA (nao commitada) |
| 1.3 | Executor agent | COMPLETA (nao commitada) |
| 1.4 | Reviewer agent | COMPLETA (nao commitada) |
| 1.5a | Orquestrador (`orchestrator.py`) | COMPLETA (nao commitada) |
| 1.5b | CLI (`cli.py`) | COMPLETA (nao commitada) |

---

## O que foi feito nesta sessão

### Correcoes de estrutura — commit `a9ecdaa`

O commit inicial (`508f14d`) criou todos os arquivos na raiz do projeto em vez
de dentro do pacote `orchestrator/`. Corrigido:

- Movidos para `orchestrator/`: todos os módulos Python
- Movidos para `orchestrator/prompts/`: os 3 system prompts
- Movido para `configs/`: `default.yaml`
- `gitignore` renomeado para `.gitignore`
- Emojis removidos do `cli.py` (incompatíveis com cp1252 no Windows terminal)

### Fase 1.2 — Planner (`orchestrator/planner.py`)

- Usa `AsyncAnthropic` (cliente async do SDK)
- Monta user message com task + contexto opcional do projeto
- Chama `client.messages.create()` com o system prompt de `prompts/planner_system.md`
- Parseia resposta JSON em `TaskPlan` via `TaskPlan.from_json()`
- Testado: gerou `TaskPlan` valido para "Criar endpoint GET /health"

### Fase 1.3 — Executor (`orchestrator/executor.py`)

- `_build_prompt()`: monta o prompt a partir do `TaskPlan` + contexto do executor + feedback opcional
- `_get_diff()`: captura diff de arquivos modificados (`git diff HEAD`) e arquivos novos não rastreados (`git ls-files --others` + `git diff --no-index`)
- `execute_plan()`: chama `claude_agent_sdk.query()` com `allowed_tools`, `cwd` e `permission_mode="bypassPermissions"`
- Testado: criou `hello.py` no projeto cobaia e retornou diff unificado correto

### Fase 1.4 — Reviewer (`orchestrator/reviewer.py`)

- Monta user message com o plano (JSON) + diff como bloco de código
- Chama `AsyncAnthropic.messages.create()` com system prompt de `prompts/reviewer_system.md`
- Trata markdown fences caso o modelo embrulhe o JSON
- Parseia resposta em `ReviewResult` via `ReviewResult.from_dict()`
- Testado caminho de aprovação (score 10) e rejeição (score 2, 2 issues críticos)

---

### Fase 1.5a — Orquestrador (`orchestrator/orchestrator.py`)

- Cria `CycleRecord` com status `PLANNED`
- Chama `planner.generate_plan()` e armazena o plano
- Loop `while attempt <= max_retries`:
  - Status `EXECUTING` → chama `executor.execute_plan()` (com feedback nas tentativas seguintes)
  - Status `REVIEWING` → chama `reviewer.review_code()`
  - Aprovado → status `APPROVED`, sai do loop
  - Reprovado e ainda tem tentativas → monta feedback string com as issues e incrementa attempt
  - Esgotou tentativas → status `ESCALATED`
- Preenche `finished_at` antes de retornar
- Testado: caminho aprovado (attempt=1, APPROVED) e esgotado (attempt=2, ESCALATED)

### Fase 1.5b — CLI (`orchestrator/cli.py`)

- `_display_plan()`: exibe files e steps em Panel azul
- `_display_review()`: exibe score e summary em Panel verde (aprovado) ou vermelho (reprovado)
- `_display_issues()`: lista issues com severidade quando ESCALATED
- `_commit()`: roda `git add . && git commit -m` via subprocess no `project_dir`
- `_run()`: corrotina principal — chama `orch.run_cycle()`, exibe plano, review e diff, pede confirmacao
- `run`: envolve `_run` com `asyncio.run()`, trata `anthropic.APIError` e `KeyboardInterrupt`
- Testado end-to-end no projeto cobaia: tarefa planejada, implementada, aprovada (score 9) e commitada automaticamente

## Situacao atual — MVP COMPLETO

**Todas as fases do MVP (1.1 a 1.5) estao implementadas e testadas.**  
Nenhuma das mudancas foi commitada ainda — aguardando revisao e liberacao.

## Proximo passo — Fases 2 e 3 (pos-MVP)

### Fases 2 e 3 (pos-MVP)

- **Fase 2:** logging em JSON, config por projeto (`.orchestrator.yaml`), retry em erros de API, UX com progress bars
- **Fase 3:** batch de tasks, templates de projeto, integracao Git avancada, metricas de custo

---

## Projeto cobaia

Para testar o orquestrador: "Task Tracker CLI" (~5 arquivos, ~200 linhas).
Tasks de teste em `docs/AI_Dev_Orchestrator_Plano.md`.

---

## Como rodar o que ja funciona

```bash
# CLI
orchestrate --version
orchestrate run "sua task aqui"

# Planner isolado
python -c "
import asyncio
from orchestrator.config import Config
from orchestrator.planner import generate_plan

async def main():
    config = Config.load('.')
    plan = await generate_plan('sua task aqui', config)
    print(plan.to_json(indent=2))

asyncio.run(main())
"
```
