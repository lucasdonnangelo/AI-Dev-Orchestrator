# AI Dev Orchestrator — Fase 6: Orquestração por Plano Hierárquico

**Autor:** Lucas Donnangelo + Claude
**Data:** 13/04/2026
**Status:** Planejamento

---

## Objetivo

Transformar o orchestrator em um sistema capaz de gerenciar e executar o desenvolvimento
de um projeto inteiro de forma autônoma e incremental, seguindo um plano hierárquico
definido previamente por você.

O sistema deve ser capaz de:
- Ler um plano estruturado em fases, subfases e tasks
- Executar cada task autonomamente pelo ciclo completo de agentes
- Marcar progresso e avançar automaticamente
- Parar para validação humana ao fim de cada fase ou subfase
- Retomar de onde parou se interrompido
- Manter contexto acumulado entre tasks da mesma fase

---

## Formato do Plano (PLANO.md)

O plano é um arquivo Markdown que você escreve antes de iniciar o projeto.
O sistema lê, parseia e executa. Exemplo de formato:

```markdown
# Nome do Projeto

## Fase 1 — Nome da Fase

### 1.1 Nome da Subfase

- [ ] 1.1.1 Descrição da task
- [ ] 1.1.2 Descrição da task
- [ ] 1.1.3 Descrição da task

### 1.2 Nome da Subfase

- [ ] 1.2.1 Descrição da task
- [ ] 1.2.2 Descrição da task

## Fase 2 — Nome da Fase

### 2.1 Nome da Subfase

- [ ] 2.1.1 Descrição da task
```

O sistema atualiza o `PLANO.md` em tempo real conforme executa:
- `- [ ]` task pendente
- `- [x]` task concluída
- `- [!]` task escalada (requer intervenção)

---

## Sub-fases

### 6.1 — Parser e Modelo de Dados

**Objetivo:** Ler e persistir o plano hierárquico.

**Tasks:**

**6.1.1 — Modelo de dados**
Criar `orchestrator/plan.py` com dataclasses:
- `ProjectPlan` — nome, fases, metadata
- `Phase` — id (ex: "1"), nome, subfases
- `SubPhase` — id (ex: "1.1"), nome, tasks
- `PlanTask` — id (ex: "1.1.1"), descrição, status, commit_hash, started_at, finished_at

Status possíveis: `pending`, `running`, `done`, `escalated`, `skipped`

**6.1.2 — Parser de PLANO.md**
Função `parse_plan(path) -> ProjectPlan`:
- Lê o arquivo Markdown
- Extrai hierarquia: Fase (##) → Subfase (###) → Task (- [ ])
- Detecta status pelo checkbox: `[ ]` = pending, `[x]` = done, `[!]` = escalated
- Retorna `ProjectPlan` completo

**6.1.3 — Writer de PLANO.md**
Função `write_plan(plan, path)`:
- Serializa o `ProjectPlan` de volta para Markdown
- Preserva formatação e texto original
- Atualiza apenas os checkboxes das tasks
- Chamado após cada task concluída

**6.1.4 — Comandos CLI básicos**
Adicionar ao `cli.py`:
- `orchestrate plan status [-d project_dir]` — exibe tabela com progresso por fase/subfase
- `orchestrate plan next [-d project_dir]` — mostra qual é a próxima task pendente
- `orchestrate plan reset TASK_ID [-d project_dir]` — volta task para pending

**Critério de aceite:** dado um `PLANO.md` com 3 fases e 10 tasks, `plan status`
exibe progresso correto e `plan next` aponta para a primeira task pendente.

---

### 6.2 — Motor de Execução por Plano

**Objetivo:** Executar tasks do plano sequencialmente com controle de progresso.

**Tasks:**

**6.2.1 — Executor de plano**
Criar função `run_plan(plan_path, config, project_dir, options)` em `orchestrator/plan_runner.py`:
- Lê o plano via `parse_plan()`
- Identifica próxima task pendente
- Executa o ciclo completo (`run_cycle`) para essa task
- Atualiza o status no `PLANO.md` via `write_plan()`
- Avança para a próxima task automaticamente
- Repete até:
  - Fim da subfase atual (pausa para validação)
  - Fim da fase atual (pausa para validação)
  - Task escalada (pausa obrigatória)
  - Fim do plano completo

**6.2.2 — Contexto acumulado entre tasks**
Ao executar cada task, incluir no prompt do Planner:
- Tasks já concluídas na mesma subfase (id + descrição + commit)
- Tasks já concluídas na mesma fase
- Decisões arquiteturais relevantes do `SESSAO_ATUAL.md`

Isso garante que o Planner e o Critic saibam o que já foi feito antes de planejar a próxima task.

**6.2.3 — Pausa para validação**
Implementar pontos de pausa configuráveis:
- `pause_after_subtask: bool` — pausa ao fim de cada subfase (default: true)
- `pause_after_phase: bool` — pausa ao fim de cada fase (default: true)
- `auto_continue: bool` — nunca pausa, executa tudo (default: false)

Na pausa, exibe resumo do que foi feito e aguarda confirmação do usuário antes de continuar.

**6.2.4 — Retomada de execução**
`run_plan` deve ser idempotente:
- Se executado novamente, retoma da primeira task com status `pending`
- Tasks com status `done` são puladas automaticamente
- Tasks com status `escalated` exibem aviso e perguntam se devem pular ou retentar

**Critério de aceite:** dado um `PLANO.md` com 6 tasks em 2 subfases, o sistema
executa todas, atualiza os checkboxes, pausa entre subfases e retoma corretamente
se interrompido no meio.

---

### 6.3 — Critic de Coerência Entre Tasks

**Objetivo:** Garantir que cada task seja planejada de forma consistente com
o que já foi implementado nas tasks anteriores da mesma fase.

**Tasks:**

**6.3.1 — Contexto de fase no Critic**
Modificar `critic.py` para aceitar `phase_context: str | None`:
- Se fornecido, inclui no system prompt do Critic
- O Critic deve avaliar: "este plano conflita com algo já implementado?"
- Adicionar critério explícito de coerência entre tasks no `critic_system.md`

**6.3.2 — Geração de phase_context**
Em `plan_runner.py`, antes de cada ciclo, gerar `phase_context` com:
- Lista de arquivos criados/modificados pelas tasks anteriores da fase
- Resumo dos planos aprovados anteriormente
- Diffs relevantes (truncados se necessário)

**Critério de aceite:** dado um plano onde a task 1.1.2 conflita com a 1.1.1,
o Critic identifica e reprova o plano antes de executar.

---

### 6.4 — Comando CLI Principal

**Objetivo:** Interface unificada para execução por plano.

**Tasks:**

**6.4.1 — Comando `orchestrate plan run`**
```bash
orchestrate plan run [-d project_dir] [--phase 1] [--subtask 1.1] [--auto] [--dry-run]
```
- Sem flags: executa a próxima task pendente e para
- `--phase 1`: executa todas as tasks da fase 1
- `--subtask 1.1`: executa todas as tasks da subfase 1.1
- `--auto`: executa tudo sem pausas (equivale a `auto_continue=true`)
- `--dry-run`: mostra o que seria executado sem executar

**6.4.2 — Output visual do progresso**
Durante a execução por plano, exibir:
```
[PLANO] FinanceAI — Fase 1: Setup Inicial
  Subfase 1.1 — Estrutura do Projeto
  [x] 1.1.1 Criar estrutura de pastas        [OK] feat: criar estrutura (abc1234)
  [x] 1.1.2 Configurar pyproject.toml        [OK] feat: pyproject (def5678)
  [>] 1.1.3 Criar modelos base               executando...
  [ ] 1.1.4 Configurar banco de dados        pendente
```

**6.4.3 — Resumo de fase**
Ao fim de cada fase, exibir:
- Quantas tasks concluídas / escaladas / puladas
- Lista de commits gerados
- Tempo total da fase
- Pergunta: "Continuar para a Fase 2? [y/n]"

**Critério de aceite:** `orchestrate plan run --phase 1 -d /projeto` executa
todas as tasks da fase 1, exibe progresso em tempo real e pausa para confirmação
antes da fase 2.

---

### 6.5 — Geração de Plano por IA (opcional, mas recomendado)

**Objetivo:** Permitir que o sistema gere o `PLANO.md` a partir de uma descrição
em linguagem natural, para projetos onde você ainda não tem o plano estruturado.

**Tasks:**

**6.5.1 — Agente Planejador de Projeto**
Criar `orchestrator/project_planner.py`:
- Recebe: descrição do projeto + premissas + stack
- Gera: `PLANO.md` completo com fases, subfases e tasks
- Usa Claude (Planner provider) com prompt especializado
- Saída é um `PLANO.md` editável por você antes de executar

**6.5.2 — Critic do Plano de Projeto**
Antes de salvar o `PLANO.md` gerado:
- Gemini (Critic) avalia se o plano está completo, coerente e bem estruturado
- Sugere ajustes se necessário
- Você aprova ou edita antes de executar

**6.5.3 — Comando CLI**
```bash
orchestrate plan generate "Quero construir uma API REST de gerenciamento financeiro
com autenticação JWT, PostgreSQL e deploy no Railway" [-d project_dir]
```
- Gera `PLANO.md` no diretório do projeto
- Exibe o plano para revisão
- Pergunta: "Aprovar este plano e começar execução? [y/n/edit]"

**Critério de aceite:** dado uma descrição de projeto em linguagem natural,
gera um `PLANO.md` coerente e estruturado que você consegue editar e executar.

---

## Arquivos novos

```
orchestrator/
├── plan.py              # Modelo de dados + parser + writer do PLANO.md
├── plan_runner.py       # Motor de execução por plano
└── project_planner.py  # Geração de plano por IA (6.5)
```

## Arquivos modificados

```
orchestrator/
├── cli.py              # Novos comandos: plan run, plan status, plan next,
│                       # plan reset, plan generate
├── critic.py           # Suporte a phase_context
└── prompts/
    ├── critic_system.md          # Critério de coerência entre tasks
    └── project_planner_system.md # Novo prompt para geração de plano
```

---

## Comandos novos (resumo)

```bash
# Ver progresso do plano
orchestrate plan status [-d project_dir]

# Ver próxima task pendente
orchestrate plan next [-d project_dir]

# Executar próxima task pendente
orchestrate plan run [-d project_dir]

# Executar subfase completa
orchestrate plan run --subtask 1.1 [-d project_dir]

# Executar fase completa
orchestrate plan run --phase 1 [-d project_dir]

# Executar tudo sem pausas
orchestrate plan run --auto [-d project_dir]

# Simular sem executar
orchestrate plan run --dry-run [-d project_dir]

# Voltar task para pendente
orchestrate plan reset 1.1.3 [-d project_dir]

# Gerar plano por IA
orchestrate plan generate "descrição do projeto" [-d project_dir]
```

---

## Formato do PLANO.md após execução parcial

```markdown
# FinanceAI

## Fase 1 — Setup Inicial

### 1.1 Estrutura do Projeto

- [x] 1.1.1 Criar estrutura de pastas e pyproject.toml
- [x] 1.1.2 Configurar variáveis de ambiente e .env.example
- [!] 1.1.3 Configurar banco de dados PostgreSQL
- [ ] 1.1.4 Criar modelos base com SQLAlchemy

### 1.2 Autenticação

- [ ] 1.2.1 Implementar JWT authentication
- [ ] 1.2.2 Criar endpoints de login e registro
```

---

## Nosso papel vs papel do sistema

| Responsabilidade | Quem faz |
|-----------------|----------|
| Escrever o PLANO.md | Você + Claude (planejamento) |
| Revisar o PLANO.md gerado por IA | Você |
| Executar tasks autonomamente | Sistema |
| Marcar progresso | Sistema |
| Avançar entre tasks | Sistema |
| Parar quando escala | Sistema |
| Resolver escalações | Você |
| Validar fim de subfase | Você |
| Validar fim de fase | Você + Claude (se necessário) |
| Decidir se continua ou ajusta plano | Você |

---

## Cronograma estimado

| Sub-fase | Descrição | Estimativa |
|----------|-----------|------------|
| 6.1 | Parser e modelo de dados | 1 sessão |
| 6.2 | Motor de execução | 1-2 sessões |
| 6.3 | Critic de coerência | 1 sessão |
| 6.4 | Comando CLI principal | 1 sessão |
| 6.5 | Geração de plano por IA | 1 sessão |

---

## Princípios

1. **PLANO.md é a fonte de verdade** — tudo que o sistema faz parte dele
2. **Idempotente** — pode ser interrompido e retomado sem perda
3. **Contexto acumulado** — cada task sabe o que foi feito antes
4. **Humano valida marcos** — fim de subfase e fase sempre pausam
5. **CLI continua funcionando** — `run` e `batch` não são afetados

---

*Este documento complementa o AI_Dev_Orchestrator_Plano.md principal.*
