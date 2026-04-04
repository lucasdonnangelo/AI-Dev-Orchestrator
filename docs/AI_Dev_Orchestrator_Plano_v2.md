# AI Dev Orchestrator — Plano de Projeto (v2)

**Autor:** Lucas Donnangelo + Claude
**Data:** 04/04/2026
**Status:** Em desenvolvimento (Fase 1 completa)

---

## Objetivo Final

Criar um sistema CLI de automacao de desenvolvimento que opera em **multiplas camadas de validacao com IAs de diferentes providers**, garantindo qualidade e rastreabilidade em cada etapa.

### Papeis das IAs

| Papel | Responsavel | Provider |
|-------|-------------|----------|
| **Planner** | Claude (API) | Anthropic |
| **Critico do Plano** | Gemini ou ChatGPT | Google / OpenAI |
| **Executor (Dev)** | Claude Code (Agent SDK) | Anthropic |
| **Reviewer** | Gemini ou ChatGPT | Google / OpenAI |
| **Decisor** | Gemini ou ChatGPT | Google / OpenAI |

### Fluxo Completo (Visao Final)

```
                         PLANEJAMENTO
                         ============

  Voce (task) --> Planner (Claude) --> Plano v1
                        |
                        v
              Critico (Gemini/GPT) --> observacoes, criticas, sugestoes
                        |
                        v
              Planner ajusta --> Plano v2
                        |
                        v
              Critico reavalia --> ok?
                        |
                  [repete 2-5x ate consenso]
                        |
                        v
                   Plano Final

                         EXECUCAO
                         ========

              Plano Final --> Executor (Claude Code Agent SDK)
                        |
                        v
                   Implementa tarefa N da fase
                        |
                        v
                   Gera diff das mudancas
                        |
                        v
              Reviewer (Gemini/GPT) --> avalia codigo
                        |
              +---------+---------+
              |                   |
          REPROVADO           APROVADO
          (max 3x)               |
              |                  v
              v          Atualiza SESSAO_ATUAL.md
         Executor               |
         corrige                v
              |         Decisor (Gemini/GPT) --> valida coerencia com plano
              |                  |
              |         +--------+--------+
              |         |                 |
              |     COERENTE         INCONSISTENTE
              |         |                 |
              |         v                 v
              |   Proxima tarefa    Escala para VOCE
              |         |
              +-----> [repete ate concluir a fase]

                        RASTREABILIDADE
                        ===============

              SESSAO_ATUAL.md (atualizado apos cada tarefa aprovada)
                - O que foi desenvolvido
                - Estado atual do projeto
                - Proximas etapas (baseado no plano)
              Serve para manter TODAS as IAs alinhadas.
```

---

## Stack Tecnico

| Componente | Tecnologia | Motivo |
|------------|-----------|--------|
| Linguagem | Python 3.10+ | Consistente com seus projetos |
| Planner | `anthropic` SDK (API Messages) | Claude pensa e estrutura o plano |
| Critico | `google-genai` ou `openai` SDK | IA diferente critica o plano (evita vies) |
| Executor | `claude-agent-sdk` (Agent SDK) | Executa codigo, cria arquivos, roda testes |
| Reviewer | `google-genai` ou `openai` SDK | IA diferente avalia o codigo (evita vies) |
| Decisor | `google-genai` ou `openai` SDK | Valida coerencia geral com o plano |
| Interface | CLI (click) | Rapido, sem overhead de UI |
| Config | `.env` + YAML por projeto | Flexivel e reutilizavel |

### Principio Arquitetural: Separacao de Providers

O Claude (Anthropic) **planeja e executa**. IAs de outro provider (Google/OpenAI) **criticam, revisam e validam**. Isso elimina o vies de uma IA avaliar o proprio trabalho.

---

## Pre-requisitos

1. **Conta Anthropic com API key** (`ANTHROPIC_API_KEY`) — para Planner e Executor
2. **Conta Google AI** (`GOOGLE_API_KEY`) e/ou **Conta OpenAI** (`OPENAI_API_KEY`) — para Critico, Reviewer e Decisor
3. **Claude Code instalado** — para desenvolvimento do proprio orquestrador
4. **Python 3.10+**
5. **Node.js 18+** — dependencia do Claude Agent SDK

### Custos Estimados por Ciclo Completo

| Componente | Custo estimado |
|------------|---------------|
| Planner (Claude Sonnet) | ~$0.003-0.01 |
| Critico do Plano (2-5 rounds) | ~$0.01-0.05 |
| Executor (Agent SDK) | ~$0.02-0.10 (varia com complexidade) |
| Reviewer | ~$0.003-0.01 |
| Decisor | ~$0.003-0.01 |
| **Total por tarefa** | **~$0.04-0.18** |

---

## Fases do Projeto

### FASE 1 — MVP Funcional [COMPLETA]

**Objetivo:** Ciclo basico funcionando: task -> plan -> execute -> review -> resultado

**Status:** Todos os itens abaixo estao implementados e testados.

#### 1.1 Setup do Projeto
- Repositorio criado e vinculado ao GitHub
- Estrutura de pastas, pyproject.toml, .env, dependencias
- CLI basica com click (orchestrate run/status/history)

#### 1.2 Planner Agent
- `orchestrator/planner.py` — chamada AsyncAnthropic, retorna TaskPlan
- System prompt em `orchestrator/prompts/planner_system.md`

#### 1.3 Executor Agent
- `orchestrator/executor.py` — usa `claude-agent-sdk` (query + ClaudeAgentOptions)
- Monta prompt a partir do plano + feedback, captura diff via git

#### 1.4 Reviewer Agent
- `orchestrator/reviewer.py` — chamada AsyncAnthropic, retorna ReviewResult
- System prompt em `orchestrator/prompts/reviewer_system.md`
- Strip de markdown fences na resposta

#### 1.5 Orquestrador + CLI
- `orchestrator/orchestrator.py` — loop Planner -> Executor -> Reviewer (max 3 retries)
- `orchestrator/cli.py` — exibe plano, review, diff, pede confirmacao de commit
- Tratamento de APIError e KeyboardInterrupt

**Limitacao atual:** Planner, Reviewer e Executor usam apenas Claude (mesmo provider). A Fase 2 resolve isso.

#### Estrutura Atual

```
ai-dev-orchestrator/
├── orchestrator/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py            # TaskPlan, ReviewResult, CycleRecord
│   ├── planner.py
│   ├── executor.py
│   ├── reviewer.py
│   ├── orchestrator.py
│   └── prompts/
│       ├── planner_system.md
│       ├── reviewer_system.md
│       └── executor_context.md
├── configs/
│   └── default.yaml
├── logs/
├── docs/
│   └── AI_Dev_Orchestrator_Plano.md
├── CLAUDE.md
├── .env
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

### FASE 2 — Multi-Model e Robustez (Semana 3-4)

**Objetivo:** Integrar Gemini/ChatGPT como Reviewer e Critico, tornar o sistema confiavel para uso diario.

#### 2.1 Arquitetura Multi-Provider

**Tasks:**
- Criar interface abstrata `BaseAgent` com metodo `async call(prompt, system) -> str`
- Implementar `ClaudeProvider` (anthropic SDK)
- Implementar `GeminiProvider` (google-genai SDK)
- Implementar `OpenAIProvider` (openai SDK)
- Config para escolher provider por papel (planner, critic, reviewer, decisor)

**Novas dependencias:**
```
google-genai>=1.0.0      # Gemini API
openai>=1.50.0            # ChatGPT API
```

**Config atualizada (.env):**
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AI...
OPENAI_API_KEY=sk-...

# Provider por papel
PLANNER_PROVIDER=anthropic
CRITIC_PROVIDER=google
REVIEWER_PROVIDER=google
DECISOR_PROVIDER=google
```

**Criterio de aceite:** Reviewer funciona com Gemini ou ChatGPT no lugar de Claude.

#### 2.2 Critico do Plano (Plan Critic)

**Tasks:**
- Criar `orchestrator/critic.py`
- Criar system prompt `orchestrator/prompts/critic_system.md`
- Implementar loop iterativo Planner <-> Critico (2-5 rounds)
- Criterio de parada: Critico responde com `consensus: true` ou atingiu max rounds

**Fluxo:**
```
1. Planner gera plano v1
2. Critico recebe plano, retorna CriticResult:
   - consensus: bool
   - observations: lista de observacoes
   - suggestions: lista de sugestoes
   - score: 1-10
3. Se consensus=false e round < max_rounds:
   - Planner recebe feedback do Critico e gera plano v(n+1)
   - Volta ao passo 2
4. Se consensus=true ou round >= max_rounds:
   - Plano final vai pro Executor
```

**Output:** `CriticResult` (nova dataclass em models.py)
```python
@dataclass
class CriticResult:
    consensus: bool
    observations: list[str]
    suggestions: list[str]
    score: int  # 1-10
    round: int
```

**Criterio de aceite:** Plano passa por 2+ rounds de critica antes de chegar no Executor.

#### 2.3 Decisor (Post-Review Validator)

**Tasks:**
- Criar `orchestrator/decisor.py`
- Criar system prompt `orchestrator/prompts/decisor_system.md`
- O Decisor recebe: plano original + diff + ReviewResult + SESSAO_ATUAL.md
- Valida coerencia geral: o que foi implementado bate com o plano?
- Retorna `DecisionResult`:

```python
@dataclass
class DecisionResult:
    approved: bool
    reasoning: str
    inconsistencies: list[str]  # vazio se aprovado
```

**Criterio de aceite:** Decisor bloqueia progresso quando implementacao diverge do plano.

#### 2.4 SESSAO_ATUAL.md Automatizado

**Tasks:**
- Apos cada tarefa aprovada (Reviewer + Decisor ok), gerar/atualizar `SESSAO_ATUAL.md`
- Conteudo: o que foi feito, estado atual, proximas etapas
- Esse arquivo e carregado como contexto para TODAS as IAs em cada chamada

**Template:**
```markdown
# Sessao Atual — AI Dev Orchestrator

## Ultima Atualizacao
[timestamp]

## O Que Foi Desenvolvido
- [lista de tarefas concluidas nesta sessao]

## Estado Atual do Projeto
- Fase: [fase atual]
- Tarefa atual: [descricao]
- Arquivos modificados: [lista]

## Proximas Etapas
1. [proxima tarefa baseada no plano]
2. [seguinte]
3. [seguinte]
```

**Criterio de aceite:** SESSAO_ATUAL.md e atualizado automaticamente apos cada aprovacao.

#### 2.5 Robustez

**Tasks:**
- Retry automatico em erros de API (rate limit, timeout) — todos os providers
- Fallback graceful quando Agent SDK falha
- Timeout configuravel por etapa
- Corrigir `_get_diff` para funcionar no Windows (substituir `/dev/null`)

**Criterio de aceite:** 10 tasks consecutivas sem crash inesperado.

#### 2.6 Logging e Historico

**Tasks:**
- Salvar cada execucao em `logs/` com timestamp (JSON)
- Log completo: task -> plan -> critic rounds -> code -> review -> decision -> resultado
- Comando `orchestrate history` para listar execucoes
- Comando `orchestrate status` para ver ultima execucao

**Criterio de aceite:** historico consultavel com detalhes de cada etapa.

---

### FASE 3 — Orquestracao Avancada (Semana 5-6)

**Objetivo:** Multi-task, gestao de contexto inteligente e integracao git completa.

#### 3.1 Gestao de Contexto Inteligente

- Carregar README, estrutura de pastas e arquivos relevantes como contexto
- Deteccao automatica de stack (Python, Node, etc.)
- Limitar tamanho do contexto para nao estourar tokens
- SESSAO_ATUAL.md sempre incluido no contexto de todas as IAs

#### 3.2 Multi-task (Batch)

- Aceitar arquivo com lista de tasks (uma por linha ou JSON)
- Executar sequencialmente: tarefa N so comeca apos tarefa N-1 aprovada
- SESSAO_ATUAL.md acumula contexto entre tarefas
- Relatorio final consolidado

**Comando:**
```bash
orchestrate batch tasks.txt -d /path/to/project
```

#### 3.3 Integracao Git Avancada

- Criar branch por task automaticamente (`feat/task-descricao`)
- Mensagens de commit seguindo Conventional Commits
- Suporte a PR description automatica
- Opcao de squash commits por fase

#### 3.4 Melhorias de CLI

- Progress bars com `rich` por etapa
- Output colorido: plan=azul, critic=ciano, execute=verde, review=amarelo, decision=magenta
- Modo verbose (`-v`) para debug completo
- Modo silencioso (`-q`) para scripts/CI
- Exibir custos estimados por chamada

#### 3.5 Metricas e Analytics

- Taxa de aprovacao no primeiro review
- Numero medio de rounds do Critico ate consenso
- Tempo medio por ciclo completo
- Custo acumulado por projeto e por provider
- Comando: `orchestrate metrics`

**Criterio de aceite:** sistema funciona com 3+ projetos diferentes sem modificacao.

---

### FASE 4 — Extensibilidade (Semana 7-8)

**Objetivo:** Tornar o sistema configuravel e extensivel.

#### 4.1 Templates de Projeto

- Templates pre-definidos: FastAPI, React, Python CLI
- Cada template inclui prompts otimizados para aquele stack
- Comando: `orchestrate init --template fastapi`

#### 4.2 Prompts Customizaveis por Projeto

- Override de qualquer system prompt via `.orchestrator.yaml`
- Prompts extras por stack (ex: "sempre use type hints", "siga PEP 8")

#### 4.3 Plugin de Providers

- Interface de plugin para adicionar novos providers (Mistral, Llama, etc.)
- Registro dinamico via config
- Hot-swap de provider sem restart

#### 4.4 Modo Interativo

- Apos rejeicao do Reviewer ou Decisor, permitir que o usuario edite o plano ou o codigo antes de resubmeter
- Chat interativo com qualquer agente individualmente

**Criterio de aceite:** usuario consegue adicionar um novo provider sem modificar codigo core.

---

## Projeto Cobaia

Para testar o orquestrador, usar um projeto pequeno e simples:

**"Task Tracker CLI"**
- CLI Python simples para gerenciar tarefas (add, list, done, delete)
- Armazena em JSON local
- ~5 arquivos, ~200 linhas

**Tasks de teste (em ordem crescente de complexidade):**

1. "Criar estrutura inicial do projeto com pyproject.toml"
2. "Criar modelo Task com campos id, title, status, created_at"
3. "Implementar storage em arquivo JSON"
4. "Criar comando CLI 'add' que adiciona uma task"
5. "Criar comando CLI 'list' que mostra todas as tasks"
6. "Adicionar testes unitarios para o storage"

---

## Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| Agent SDK instavel/breaking changes | Media | Alto | Pintar versao, fallback para subprocess |
| Custo de API maior que esperado | Media | Medio | Sonnet (nao Opus), monitorar custos por provider |
| Planner gera planos ruins | Media | Medio | Critico iterativo melhora o plano antes da execucao |
| Executor nao segue o plano | Media | Alto | Prompt engineering + Decisor valida coerencia |
| Reviewer aprova codigo ruim | Baixa | Alto | Provider diferente + criterios rigidos no prompt |
| Loop de correcao nao converge | Media | Medio | Max 3 retries, escala para humano |
| APIs de providers diferentes fora do ar | Baixa | Medio | Fallback entre providers (Gemini -> OpenAI) |
| Critico e Planner nao chegam a consenso | Media | Baixo | Max 5 rounds, segue com melhor versao |

---

## Decisoes Registradas

| # | Decisao | Motivo |
|---|---------|--------|
| D1 | MVP so com Claude, multi-model na Fase 2 | Validar fluxo basico antes de adicionar complexidade |
| D2 | Planner e Reviewer sao IAs de providers diferentes | Eliminar vies — quem planeja nao avalia |
| D3 | Executor usa Claude Agent SDK | SDK oficial, melhor integracao, sem IPC overhead |
| D4 | Commit semi-automatico (humano confirma) | Manter controle humano sobre o repositorio |
| D5 | Max 3 retries no loop de correcao | Evitar loops infinitos e custos desnecessarios |
| D6 | Critico do plano com 2-5 rounds | Equilibrio entre qualidade do plano e custo |
| D7 | Decisor valida coerencia apos review | Terceira camada garante que nada passou despercebido |
| D8 | SESSAO_ATUAL.md como fonte de verdade | Todas as IAs leem o mesmo estado, evita desalinhamento |
| D9 | CLI primeiro, interface web depois | Velocidade de desenvolvimento, publico-alvo: devs |
| D10 | Projeto cobaia separado | Testar sem risco ao projeto principal |

---

## Cronograma Resumido

| Semana | Fase | Entregavel |
|--------|------|-----------|
| 1-2 | Fase 1 (COMPLETA) | MVP: Planner + Executor + Reviewer + CLI |
| 3-4 | Fase 2 | Multi-model, Critico, Decisor, SESSAO_ATUAL.md, robustez |
| 5-6 | Fase 3 | Multi-task, contexto inteligente, git avancado, metricas |
| 7-8 | Fase 4 | Templates, plugins, modo interativo |

---

## Proximos Passos Imediatos

1. Commitar estado atual (Fase 1 completa)
2. Criar contas e API keys para Gemini e/ou OpenAI
3. Implementar arquitetura multi-provider (BaseAgent + providers)
4. Implementar Critico do Plano
5. Migrar Reviewer para usar Gemini/ChatGPT
6. Implementar Decisor
7. Automatizar SESSAO_ATUAL.md
8. Testar ciclo completo multi-model com projeto cobaia

---

*Documento vivo — atualizado conforme o projeto evolui.*
