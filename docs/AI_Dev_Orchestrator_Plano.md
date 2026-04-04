# AI Dev Orchestrator — Plano de Projeto (v2)

**Autor:** Lucas Donnangelo + Claude
**Data:** 04/04/2026
**Status:** Em desenvolvimento (Fase 2.1 completa)

---

## Objetivo Final

Criar um sistema CLI de automacao de desenvolvimento que opera em **multiplas camadas de validacao com IAs de diferentes providers**, garantindo qualidade e rastreabilidade em cada etapa.

### Papeis das IAs

| Papel | Responsavel | Provider | Modelo |
|-------|-------------|----------|--------|
| **Planner** | Claude | Anthropic | claude-sonnet-4-6 |
| **Critico do Plano** | Gemini | Google | gemini-2.5-flash |
| **Executor (Dev)** | Claude Code | Anthropic (Agent SDK) | — |
| **Reviewer** | Gemini | Google | gemini-2.5-flash |
| **Decisor** | Gemini | Google | gemini-2.5-flash |

**Principio arquitetural:** Claude (Anthropic) **planeja e executa**. Gemini (Google) **critica, revisa e valida**. Isso elimina o vies de uma IA avaliar o proprio trabalho. OpenAI esta implementado como fallback opcional mas nao e usado por padrao.

### Fluxo Completo (Visao Final)

```
                         PLANEJAMENTO
                         ============

  Voce (task) --> Planner (Claude) --> Plano v1
                        |
                        v
              Critico (Gemini) --> observacoes, criticas, sugestoes
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
              Reviewer (Gemini) --> avalia codigo
                        |
              +---------+---------+
              |                   |
          REPROVADO           APROVADO
          (max 3x)               |
              |                  v
              v          Atualiza SESSAO_ATUAL.md
         Executor               |
         corrige                v
              |         Decisor (Gemini) --> valida coerencia com plano
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
| Planner | `anthropic` SDK via BaseAgent | Claude pensa e estrutura o plano |
| Critico | `google-genai` SDK via BaseAgent | Gemini critica o plano (provider diferente = sem vies) |
| Executor | `claude-agent-sdk` (Agent SDK) | Executa codigo, cria arquivos, roda testes |
| Reviewer | `google-genai` SDK via BaseAgent | Gemini avalia o codigo (provider diferente = sem vies) |
| Decisor | `google-genai` SDK via BaseAgent | Gemini valida coerencia geral com o plano |
| Fallback | `openai` SDK via BaseAgent | OpenAI como alternativa (implementado, nao usado por padrao) |
| Interface | CLI (click) | Rapido, sem overhead de UI |
| Config | `.env` + YAML por projeto | Flexivel e reutilizavel |

---

## Pre-requisitos

1. **Conta Anthropic com API key** (`ANTHROPIC_API_KEY`) — para Planner e Executor
2. **Conta Google AI Studio com API key** (`GOOGLE_API_KEY`) — para Critico, Reviewer e Decisor
3. **Claude Code instalado** — para desenvolvimento do proprio orquestrador
4. **Python 3.10+**
5. **Node.js 18+** — dependencia do Claude Agent SDK

### Custos Estimados por Ciclo Completo

| Componente | Modelo | Custo estimado |
|------------|--------|---------------|
| Planner | Claude Sonnet | ~$0.003-0.01 |
| Critico do Plano (2-5 rounds) | Gemini 2.5 Flash | ~$0.005-0.02 |
| Executor | Agent SDK | ~$0.02-0.10 (varia com complexidade) |
| Reviewer | Gemini 2.5 Flash | ~$0.002-0.005 |
| Decisor | Gemini 2.5 Flash | ~$0.002-0.005 |
| **Total por tarefa** | | **~$0.03-0.14** |

*Gemini 2.5 Flash custa $0.15/1M input e $0.60/1M output — significativamente mais barato que alternativas.*

---

## Fases do Projeto

### FASE 1 — MVP Funcional [COMPLETA]

**Objetivo:** Ciclo basico funcionando: task -> plan -> execute -> review -> resultado

**Status:** Todos os itens implementados e testados end-to-end.

#### 1.1 Setup do Projeto
- Repositorio criado e vinculado ao GitHub
- Estrutura de pastas, pyproject.toml, .env, dependencias
- CLI basica com click (orchestrate run/status/history)

#### 1.2 Planner Agent
- `orchestrator/planner.py` — chamada via provider abstrato, retorna TaskPlan
- System prompt em `orchestrator/prompts/planner_system.md`

#### 1.3 Executor Agent
- `orchestrator/executor.py` — usa `claude-agent-sdk` (query + ClaudeAgentOptions)
- Monta prompt a partir do plano + feedback, captura diff via git

#### 1.4 Reviewer Agent
- `orchestrator/reviewer.py` — chamada via provider abstrato, retorna ReviewResult
- System prompt em `orchestrator/prompts/reviewer_system.md`

#### 1.5 Orquestrador + CLI
- `orchestrator/orchestrator.py` — loop Planner -> Executor -> Reviewer (max 3 retries)
- `orchestrator/cli.py` — exibe plano, review, diff, pede confirmacao de commit

---

### FASE 2 — Multi-Model e Robustez (Semana 3-4)

**Objetivo:** Integrar Gemini como Critico/Reviewer/Decisor, tornar o sistema confiavel.

#### 2.1 Arquitetura Multi-Provider [COMPLETA]

- `BaseAgent(ABC)` com metodo `async call(prompt, system) -> str`
- `ClaudeProvider` — anthropic SDK (AsyncAnthropic)
- `GeminiProvider` — google-genai SDK (modelo padrao: `gemini-2.5-flash`)
- `OpenAIProvider` — openai SDK (fallback opcional, nao usado por padrao)
- Factory `make_provider(name, config)` em `providers/__init__.py`
- Config com campos por provider e por papel (planner_provider, critic_provider, etc.)
- Planner e Reviewer migrados para usar providers
- Backward compatible — defaults mantidos

#### 2.2 Critico do Plano (Plan Critic)

**Tasks:**
- Criar `orchestrator/critic.py`
- Criar system prompt `orchestrator/prompts/critic_system.md`
- Implementar loop iterativo Planner <-> Critico (min 2, max 5 rounds)
- Criterio de parada: Critico responde com `consensus: true` (score >= 8) ou atingiu max rounds

**Fluxo:**
```
1. Planner gera plano v1
2. Critico (Gemini) recebe plano, retorna CriticResult:
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

**Output:**
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

**Criterio de aceite:** SESSAO_ATUAL.md e atualizado automaticamente apos cada aprovacao.

#### 2.5 Robustez

**Tasks:**
- Retry automatico em erros de API (rate limit, timeout) — todos os providers
- Fallback graceful quando Agent SDK falha
- Timeout configuravel por etapa
- Corrigir `_get_diff` para funcionar no Windows (substituir `/dev/null`)
- Corrigir exibicao de diff no CLI (capturar diff dentro do run_cycle, nao re-gerar)

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
- Comando: `orchestrate batch tasks.txt -d /path/to/project`

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
- Prompts extras por stack

#### 4.3 Plugin de Providers
- Interface de plugin para adicionar novos providers (Mistral, Llama, etc.)
- Registro dinamico via config
- Hot-swap de provider sem restart

#### 4.4 Modo Interativo
- Apos rejeicao, permitir que o usuario edite o plano ou codigo antes de resubmeter
- Chat interativo com qualquer agente individualmente

**Criterio de aceite:** usuario consegue adicionar um novo provider sem modificar codigo core.

---

## Projeto Cobaia

**"Task Tracker CLI"** — CLI Python simples para gerenciar tarefas.

**Tasks de teste:**
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
| Custo de API maior que esperado | Media | Medio | Gemini 2.5 Flash (barato), monitorar custos |
| Planner gera planos ruins | Media | Medio | Critico iterativo melhora antes da execucao |
| Executor nao segue o plano | Media | Alto | Prompt engineering + Decisor valida coerencia |
| Reviewer aprova codigo ruim | Baixa | Alto | Provider diferente (Gemini) + criterios rigidos |
| Loop de correcao nao converge | Media | Medio | Max 3 retries, escala para humano |
| API do Gemini fora do ar | Baixa | Medio | OpenAI implementado como fallback |
| Critico e Planner nao chegam a consenso | Media | Baixo | Max 5 rounds, segue com melhor versao |

---

## Decisoes Registradas

| # | Decisao | Motivo |
|---|---------|--------|
| D1 | MVP so com Claude, multi-model na Fase 2 | Validar fluxo basico antes de adicionar complexidade |
| D2 | Planner (Claude) e Reviewer (Gemini) sao providers diferentes | Eliminar vies — quem planeja nao avalia |
| D3 | Executor usa Claude Agent SDK | SDK oficial, melhor integracao, sem IPC overhead |
| D4 | Commit semi-automatico (humano confirma) | Manter controle humano sobre o repositorio |
| D5 | Max 3 retries no loop de correcao | Evitar loops infinitos e custos desnecessarios |
| D6 | Critico do plano com 2-5 rounds | Equilibrio entre qualidade do plano e custo |
| D7 | Decisor valida coerencia apos review | Terceira camada garante alinhamento com plano |
| D8 | SESSAO_ATUAL.md como fonte de verdade | Todas as IAs leem o mesmo estado |
| D9 | Gemini 2.5 Flash como modelo padrao para Critico/Reviewer/Decisor | Melhor custo-beneficio, estavel (nao preview) |
| D10 | OpenAI como fallback opcional | Implementado na arquitetura mas nao usado por padrao |
| D11 | CLI primeiro, interface web depois | Velocidade de desenvolvimento, publico-alvo: devs |

---

## Cronograma Resumido

| Semana | Fase | Entregavel |
|--------|------|-----------|
| 1-2 | Fase 1 (COMPLETA) | MVP: Planner + Executor + Reviewer + CLI |
| 3-4 | Fase 2 (EM ANDAMENTO) | Multi-model, Critico, Decisor, SESSAO_ATUAL.md, robustez |
| 5-6 | Fase 3 | Multi-task, contexto inteligente, git avancado, metricas |
| 7-8 | Fase 4 | Templates, plugins, modo interativo |

---

## Proximos Passos Imediatos

1. ~~Fase 2.1 — Arquitetura multi-provider~~ [COMPLETA]
2. **Fase 2.2 — Critico do Plano** [PROXIMA]
3. Fase 2.3 — Decisor
4. Fase 2.4 — SESSAO_ATUAL.md automatizado
5. Fase 2.5 — Robustez
6. Fase 2.6 — Logging e Historico
7. Testar ciclo completo multi-model com projeto cobaia

---

*Documento vivo — atualizado conforme o projeto evolui.*
