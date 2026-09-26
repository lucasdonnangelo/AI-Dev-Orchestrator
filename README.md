# AI Dev Orchestrator

Orquestrador multi-agente que automatiza o ciclo de desenvolvimento de software. Cada etapa (planejar, criticar o plano, implementar, revisar e decidir) é feita por um agente com papel próprio, e os agentes rodam em **provedores de IA diferentes** para que o modelo que escreve o código não seja o mesmo que o avalia.

O desenvolvedor mantém o controle final: nenhum commit acontece sem confirmação.

## Como funciona

```
Você (task)
  -> Planner (Claude)            gera o plano de ação a partir do contexto do projeto
  -> Critic (Gemini)             avalia o plano; Planner refina até haver consenso
  -> Executor (Claude Agent SDK) implementa o plano no repositório
  -> Reviewer (Gemini)           revisa o código; se reprovar, o Executor corrige
  -> Decisor (Gemini)            valida se o resultado é coerente com o plano
  -> Aprovado: você confirma o commit (mensagem convencional gerada automaticamente)
  -> Escalado: você intervém (editar plano/código, conversar com o agente, reenviar)
```

**Por que provedores diferentes?** Um modelo revisando o próprio código tende a aprovar os próprios erros. Separar geração (Anthropic) e validação (Google) reduz esse viés. OpenAI está implementado como alternativa opcional, e o provedor de cada papel é configurável.

## Funcionalidades

- **Execução de tasks isoladas ou em lote** (`orchestrate run`, `orchestrate batch`)
- **Planos hierárquicos**: um `PLANO.md` com fases, subfases e tasks é executado em sequência, com o contexto das tasks já concluídas (arquivos modificados, commits) repassado ao Critic para manter coerência entre elas
- **Geração de plano por IA** (`orchestrate plan generate`), com loop Planner/Critic e aprovação interativa
- **Dashboard web** (React + Vite + Tailwind) com streaming em tempo real via WebSocket: árvore do plano, painel de execução por agente, pausa/retomada, escalonamento, histórico e métricas
- **Memória de sessão**: o `SESSAO_ATUAL.md` do projeto-alvo é atualizado automaticamente a cada ciclo aprovado e injetado no contexto dos agentes
- **Robustez**: retry com backoff respeitando o `retryDelay` das APIs, proteção do `PLANO.md` contra alterações do Executor, tratamento de respostas vazias e JSON truncado
- **Templates de projeto** (`orchestrate init`) e chat direto com qualquer agente (`orchestrate chat`)

## Stack

- **Backend / CLI:** Python 3.11, Click, Rich, Pydantic, FastAPI, Uvicorn, WebSockets
- **Agentes:** Anthropic API, Claude Agent SDK, Google Gemini (`google-genai`), OpenAI (opcional)
- **Frontend:** React, Vite, Tailwind, Recharts
- **Testes:** pytest + pytest-asyncio (493 testes)

## Estrutura

```
orchestrator/
  cli.py              comandos do CLI
  orchestrator.py     ciclo principal de uma task
  plan_runner.py      execução de planos hierárquicos
  planner.py, critic.py, executor.py, reviewer.py, decisor.py, project_planner.py
  providers/          Anthropic, Google, OpenAI + retry
  prompts/            system prompts de cada agente
  server.py           API REST + WebSockets do dashboard
dashboard/            frontend React
configs/default.yaml  configuração padrão
tests/                suíte de testes
docs/                 planos de cada fase do projeto
```

## Instalação

Pré-requisitos: Python 3.11+, Node.js 18+ (usado pelo Claude Agent SDK e pelo dashboard), Git e chaves de API da Anthropic e do Google AI Studio.

```bash
git clone https://github.com/lucasdonnangelo/ai-dev-orchestrator.git
cd ai-dev-orchestrator

python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

pip install -e ".[dev]"

cp .env.example .env           # preencha ANTHROPIC_API_KEY e GOOGLE_API_KEY
```

Para o dashboard:

```bash
cd dashboard
npm install
npm run build
```

## Uso

```bash
# Uma task no projeto atual ou em outro diretório
orchestrate run "Criar endpoint GET /health que retorna status 200"
orchestrate run -d /caminho/do/projeto "Adicionar testes unitários para auth"

# Várias tasks de um arquivo
orchestrate batch tasks.txt

# Planos hierárquicos
orchestrate plan generate      # gera um PLANO.md com IA
orchestrate plan status        # mostra o progresso do plano
orchestrate plan run           # executa as próximas tasks do plano

# Dashboard, histórico e métricas
orchestrate dashboard
orchestrate history
orchestrate metrics
```

## Configuração

A configuração é em camadas: `configs/default.yaml`, depois um `.orchestrator.yaml` opcional na raiz do projeto-alvo, depois variáveis de ambiente (ver `.env.example`). Valores padrão:

```yaml
model: "claude-sonnet-4-6"
google_model: "gemini-2.5-flash"
planner_provider: "anthropic"
critic_provider: "google"
reviewer_provider: "google"
decisor_provider: "google"
critic_min_rounds: 2
critic_max_rounds: 5
max_retries: 3
confirm_plan: true
confirm_commit: true
```

## Status do projeto

Fases 1 a 7 concluídas: MVP do ciclo de agentes, arquitetura multi-provedor, loop de crítica do plano, Decisor, memória de sessão, dashboard web e execução hierárquica de planos com streaming em tempo real.

**Em andamento:** investigação de uma falha intermitente (`Command failed with exit code 1`) no Executor ao rodar via Claude Agent SDK em execuções longas.

O desenvolvimento do próprio orquestrador seguiu um fluxo de review gates: cada fase foi planejada em um documento (ver `docs/`) antes da implementação, e cada task só era commitada após revisão.

## Licença

MIT
