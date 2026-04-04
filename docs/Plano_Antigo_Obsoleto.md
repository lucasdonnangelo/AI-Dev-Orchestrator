# AI Dev Orchestrator — Plano de Projeto

**Autor:** Lucas Donnangelo + Claude  
**Data:** 04/04/2026  
**Status:** Planejamento

---

## Visão Geral

Sistema CLI que automatiza o ciclo de desenvolvimento de software usando agentes de IA com papéis separados: um **Planner** que decompõe tasks em planos de ação, um **Executor** que implementa o código, e um **Reviewer** que avalia a qualidade. O desenvolvedor humano mantém controle final sobre commits.

### Fluxo de Produção

```
┌─────────┐     ┌──────────────────┐     ┌───────────────────┐
│  VOCÊ   │────▸│  PLANNER (API)   │────▸│ EXECUTOR (Claude  │
│  task   │     │  gera plano      │     │ Code Agent SDK)   │
└─────────┘     └──────────────────┘     │ implementa código │
                                         └────────┬──────────┘
                                                  │
                ┌──────────────────┐              │
                │ REVIEWER (API)   │◂─────────────┘
                │ avalia código    │
                └────────┬─────────┘
                         │
              ┌──────────▾──────────┐
              │    APROVADO?        │
              │                     │
              │  SIM → mostra diff  │──▸ VOCÊ confirma commit
              │  NÃO → volta pro   │──▸ EXECUTOR corrige
              │  executor (max 3x) │    (ou escala para você)
              └─────────────────────┘
```

### Stack Técnico

| Componente | Tecnologia | Motivo |
|------------|-----------|--------|
| Linguagem | Python 3.10+ | Consistente com seus projetos |
| Planner | `anthropic` SDK (API Messages) | Só precisa pensar, não executar |
| Executor | `claude-agent-sdk` (Agent SDK Python) | Executa código, cria arquivos, roda testes — tudo programaticamente |
| Reviewer | `anthropic` SDK (API Messages) | Só precisa analisar e responder |
| Interface | CLI (argparse/click) | Rápido, sem overhead de UI |
| Config | `.env` + YAML por projeto | Flexível e reutilizável |

### Descoberta Importante: Claude Agent SDK

Durante a pesquisa, encontrei o **Claude Agent SDK para Python** (`claude-agent-sdk`), um pacote oficial da Anthropic que elimina a necessidade de chamar o Claude Code via subprocess. Vantagens:

- CLI do Claude Code já vem **bundled** no pacote — não precisa instalar separadamente
- Roda no **mesmo processo** Python (sem IPC overhead)
- Suporte nativo a **hooks** (interceptar e controlar comportamento do agente)
- Controle de **permissões de ferramentas** (quais ferramentas o agente pode usar)
- **Streaming** de respostas em tempo real
- Suporte a **sessões** (continuar conversas)

Isso simplifica significativamente a Fase 1.

---

## Pré-requisitos

Antes de iniciar o desenvolvimento:

1. **Conta Anthropic com API key** (`ANTHROPIC_API_KEY`)
   - Plano Pro ou Max do Claude (para Claude Code) OU conta Console com créditos
2. **Claude Code instalado** (para desenvolvimento do próprio orquestrador)
3. **Python 3.10+** no sistema
4. **Node.js 18+** (dependência do Claude Agent SDK)

### Custos Estimados

| Componente | Custo |
|------------|-------|
| Planner (API - Sonnet) | ~$0.003-0.01 por task |
| Executor (Agent SDK) | Incluso no plano Claude ou créditos Console |
| Reviewer (API - Sonnet) | ~$0.003-0.01 por task |
| **Total por ciclo completo** | **~$0.01-0.05** (sem retries) |

*Nota: custos variam conforme tamanho do contexto e complexidade da task.*

---

## Fases do Projeto

### FASE 1 — MVP Funcional (Semana 1-2)

**Objetivo:** Ciclo completo funcionando: task → plan → execute → review → resultado

#### 1.1 Setup do Projeto

**Tasks:**
- Criar repositório `ai-dev-orchestrator`
- Estrutura inicial de pastas
- Configurar `.env` e dependências
- README básico

**Estrutura:**
```
ai-dev-orchestrator/
├── orchestrator/
│   ├── __init__.py
│   ├── cli.py              # Ponto de entrada CLI
│   ├── config.py            # Carrega .env e configs
│   ├── planner.py           # Agente Planner (API)
│   ├── executor.py          # Agente Executor (Agent SDK)
│   ├── reviewer.py          # Agente Reviewer (API)
│   ├── orchestrator.py      # Orquestra o ciclo completo
│   ├── models.py            # Dataclasses (TaskPlan, ReviewResult, etc.)
│   └── prompts/
│       ├── planner_system.md    # System prompt do Planner
│       ├── reviewer_system.md   # System prompt do Reviewer
│       └── executor_context.md  # Contexto base do Executor
├── configs/
│   └── default.yaml         # Config padrão
├── logs/
│   └── (gerados em runtime)
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── pyproject.toml
```

**Dependências:**
```
anthropic>=0.87.0
claude-agent-sdk>=0.1.0
python-dotenv>=1.0.0
pyyaml>=6.0
rich>=13.0        # Output bonito no terminal
click>=8.0        # CLI framework
```

**Critério de aceite:** `pip install -e .` funciona, CLI roda sem erros.

#### 1.2 Planner Agent

**Tasks:**
- Implementar `planner.py` com chamada à API Anthropic
- Criar system prompt que gera planos estruturados em JSON
- Parsear resposta em dataclass `TaskPlan`

**Input:** string da task em linguagem natural  
**Output:** `TaskPlan` com:
- `description`: resumo da task
- `files_to_create`: lista de arquivos novos
- `files_to_modify`: lista de arquivos a editar
- `steps`: lista ordenada de passos para o executor
- `acceptance_criteria`: como verificar que está pronto
- `estimated_complexity`: low / medium / high

**Modelo:** `claude-sonnet-4-6` (bom equilíbrio custo/qualidade para planejamento)

**Critério de aceite:** dado "Criar um endpoint GET /health que retorna status 200", gera um plano JSON válido com steps e critérios claros.

#### 1.3 Executor Agent

**Tasks:**
- Implementar `executor.py` usando `claude-agent-sdk`
- Receber `TaskPlan` e convertê-lo em prompt para o Agent SDK
- Capturar output (arquivos criados/modificados, logs)
- Implementar controle de permissões (allowedTools)

**Integração com Agent SDK:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Edit", "Write", "Bash"],
    cwd="/path/to/project",  # diretório do projeto-alvo
)

async for message in query(prompt=executor_prompt, options=options):
    # processar mensagens do agente
```

**Critério de aceite:** recebe um plano e cria/modifica arquivos no projeto-alvo corretamente.

#### 1.4 Reviewer Agent

**Tasks:**
- Implementar `reviewer.py` com chamada à API Anthropic
- System prompt focado em code review (bugs, style, segurança, completude)
- Parsear resposta em `ReviewResult`

**Input:** plano original + diff do código gerado  
**Output:** `ReviewResult` com:
- `approved`: bool
- `score`: 1-10
- `issues`: lista de problemas encontrados (severity: critical/warning/info)
- `suggestions`: melhorias opcionais
- `summary`: resumo do review

**Modelo:** `claude-sonnet-4-6` (mesmo modelo, prompt diferente)

**Critério de aceite:** dado um diff com um bug óbvio, identifica o problema e reprova. Dado um diff limpo, aprova.

#### 1.5 Orquestrador + CLI

**Tasks:**
- Implementar `orchestrator.py` que conecta os 3 agentes
- Implementar loop de correção (max 3 tentativas)
- Implementar `cli.py` com interface de terminal
- Mostrar resultado e pedir confirmação de commit

**Comandos CLI:**
```bash
# Executar uma task
orchestrate run "Criar endpoint GET /health"

# Executar com plano customizado
orchestrate run --plan plan.json

# Ver status da última execução
orchestrate status

# Ver histórico
orchestrate history
```

**Fluxo do Orquestrador:**
```
1. Recebe task
2. Chama Planner → obtém TaskPlan
3. Mostra plano ao usuário (confirmação opcional)
4. Chama Executor com o plano → obtém código
5. Gera diff das mudanças
6. Chama Reviewer com plano + diff → obtém ReviewResult
7. Se aprovado:
   - Mostra diff + review ao usuário
   - Pergunta: "Confirmar commit? [y/n/edit message]"
   - Se sim → git add + commit com mensagem gerada
8. Se reprovado (tentativa < 3):
   - Mostra issues ao usuário
   - Chama Executor novamente com issues como feedback
   - Volta ao passo 5
9. Se reprovado (tentativa = 3):
   - Mostra todas as issues
   - Escala para o usuário decidir manualmente
```

**Critério de aceite:** ciclo completo funciona end-to-end em projeto de teste.

---

### FASE 2 — Robustez e UX (Semana 3-4)

**Objetivo:** Tornar o sistema confiável para uso diário

#### 2.1 Gestão de Contexto

- Carregar README, estrutura de pastas, e arquivos relevantes como contexto para cada agente
- Implementar detecção automática de stack (Python, Node, etc.)
- Limitar tamanho do contexto para não estourar tokens

#### 2.2 Logging e Histórico

- Salvar cada execução em `logs/` com timestamp
- Log completo: task → plan → code → review → resultado
- Formato JSON para fácil consulta posterior
- Comando `orchestrate history` para listar execuções

#### 2.3 Configuração por Projeto

- Arquivo `.orchestrator.yaml` na raiz de cada projeto
- Configurações: modelo preferido, max retries, prompts customizados, ferramentas permitidas
- Override de system prompts por projeto

#### 2.4 Tratamento de Erros

- Retry automático em erros de API (rate limit, timeout)
- Fallback graceful quando Agent SDK falha
- Mensagens de erro claras e acionáveis
- Timeout configurável por etapa

#### 2.5 Melhorias de CLI

- Progress bars com `rich`
- Output colorido por etapa (plan = azul, execute = verde, review = amarelo)
- Modo verbose (`-v`) para debug
- Modo silencioso para scripts

**Critério de aceite:** 10 tasks consecutivas sem crash inesperado.

---

### FASE 3 — Features Avançadas (Semana 5-6)

**Objetivo:** Tornar o sistema verdadeiramente reutilizável

#### 3.1 Multi-task (Batch)

- Aceitar arquivo com lista de tasks
- Executar sequencialmente com contexto acumulado
- Relatório final consolidado

#### 3.2 Templates de Projeto

- Templates pré-definidos: FastAPI, React, Python CLI
- Cada template inclui prompts otimizados para aquele stack
- Comando: `orchestrate init --template fastapi`

#### 3.3 Integração Git Avançada

- Criar branch por task automaticamente
- Mensagens de commit seguindo Conventional Commits
- Suporte a PR description automática

#### 3.4 Métricas e Analytics

- Taxa de aprovação no primeiro review
- Tempo médio por ciclo
- Custo acumulado por projeto
- Estatísticas por tipo de task

#### 3.5 Preparação para Multi-Model (Futuro)

- Arquitetura de plugins para adicionar outros modelos (Gemini, ChatGPT)
- Interface abstrata `BaseAgent` que qualquer provider pode implementar
- Config para trocar modelo por papel (ex: Planner=Claude, Reviewer=Gemini)

**Critério de aceite:** sistema funciona com 3+ projetos diferentes sem modificação.

---

## Projeto Cobaia

Para testar o orquestrador, criar um projeto pequeno e simples:

**Sugestão: "Task Tracker CLI"**
- CLI Python simples para gerenciar tarefas (add, list, done, delete)
- Armazena em JSON local
- ~5 arquivos, ~200 linhas
- Complexidade baixa, perfeito para validar o fluxo

**Tasks de teste (em ordem crescente de complexidade):**

1. "Criar estrutura inicial do projeto com pyproject.toml"
2. "Criar modelo Task com campos id, title, status, created_at"
3. "Implementar storage em arquivo JSON"
4. "Criar comando CLI 'add' que adiciona uma task"
5. "Criar comando CLI 'list' que mostra todas as tasks"
6. "Adicionar testes unitários para o storage"

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Agent SDK instável/breaking changes | Média | Alto | Pintar versão, ter fallback para subprocess |
| Custo de API maior que esperado | Baixa | Médio | Usar Sonnet (não Opus), monitorar custos |
| Planner gera planos ruins | Média | Médio | Iterar no system prompt, adicionar exemplos |
| Executor não segue o plano | Média | Alto | Prompt engineering, validação pós-execução |
| Reviewer aprova código ruim | Baixa | Alto | Critérios rígidos no prompt, revisão humana final |
| Loop de correção não converge | Média | Médio | Limite de 3 tentativas, escala para humano |

---

## Decisões Registradas

| # | Decisão | Motivo |
|---|---------|--------|
| D1 | Começar só com Claude (sem Gemini/ChatGPT) | Simplificar MVP, expandir depois |
| D2 | Planner e Reviewer são chamadas API separadas | Evitar viés (reviewer não defende próprio plano) |
| D3 | Executor usa Claude Agent SDK (não subprocess) | SDK oficial, melhor integração, sem overhead de IPC |
| D4 | Commit semi-automático (humano confirma) | Manter controle humano sobre o repositório |
| D5 | Max 3 retries no loop de correção | Evitar loops infinitos e custos desnecessários |
| D6 | CLI primeiro, interface web depois | Velocidade de desenvolvimento, público-alvo: devs |
| D7 | Projeto cobaia separado do FinanceAI | Testar sem risco ao projeto principal |

---

## Cronograma Resumido

| Semana | Fase | Entregável |
|--------|------|-----------|
| 1 | Fase 1 (1.1-1.3) | Setup + Planner + Executor funcionando |
| 2 | Fase 1 (1.4-1.5) | Reviewer + Orquestrador + ciclo completo |
| 3-4 | Fase 2 | Robustez, logging, config por projeto |
| 5-6 | Fase 3 | Multi-task, templates, métricas |

**Após Fase 1:** já é possível usar o orquestrador para acelerar o desenvolvimento do FinanceAI.

---

## Próximos Passos Imediatos

1. Criar repositório `ai-dev-orchestrator`
2. Setup de ambiente (`.env`, dependências)
3. Implementar e testar Planner isoladamente
4. Implementar e testar Executor isoladamente
5. Implementar e testar Reviewer isoladamente
6. Conectar tudo no Orquestrador
7. Testar com projeto cobaia

---

*Documento vivo — será atualizado conforme o projeto evolui.*
