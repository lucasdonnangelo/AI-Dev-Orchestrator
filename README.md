# AI Dev Orchestrator

Sistema CLI que automatiza o ciclo de desenvolvimento de software usando agentes de IA com papéis separados:

- **Planner** — decompõe uma task em um plano de ação estruturado
- **Executor** — implementa o código seguindo o plano (via Claude Agent SDK)
- **Reviewer** — avalia a qualidade do código gerado

O desenvolvedor humano mantém controle final sobre commits.

```
  Você (task) → Planner → Executor → Reviewer → Aprovado? → Você confirma commit
                                        ↑          ↓ NÃO
                                        └──────────┘ (max 3x)
```

## Pré-requisitos

- **Python 3.10+**
- **Node.js 18+** (dependência do Claude Agent SDK)
- **Conta Anthropic com API key** — [console.anthropic.com](https://console.anthropic.com)
- **Git** instalado e configurado

## Instalação

```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/ai-dev-orchestrator.git
cd ai-dev-orchestrator

# Crie e ative um virtualenv
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Instale em modo editável
pip install -e ".[dev]"

# Configure as variáveis de ambiente
cp .env.example .env
# Edite .env e adicione sua ANTHROPIC_API_KEY
```

## Uso

```bash
# Executar uma task
orchestrate run "Criar endpoint GET /health que retorna status 200"

# Usar em projeto específico
orchestrate run -d /path/to/my-project "Adicionar testes unitários para auth"

# Pular confirmação do plano
orchestrate run -y "Criar modelo User com campos name e email"

# Ver versão
orchestrate --version
```

## Configuração

### Variáveis de ambiente (`.env`)

| Variável | Obrigatória | Default | Descrição |
|----------|-------------|---------|-----------|
| `ANTHROPIC_API_KEY` | ✅ | — | Chave da API Anthropic |
| `ORCHESTRATOR_MODEL` | ❌ | `claude-sonnet-4-6` | Modelo para Planner/Reviewer |
| `ORCHESTRATOR_MAX_RETRIES` | ❌ | `3` | Tentativas máximas de correção |
| `ORCHESTRATOR_LOG_LEVEL` | ❌ | `INFO` | Nível de log |

### Config por projeto (`.orchestrator.yaml`)

Coloque na raiz do projeto-alvo para customizar o comportamento:

```yaml
model: "claude-sonnet-4-6"
max_retries: 3
confirm_plan: true
confirm_commit: true
executor_allowed_tools:
  - Read
  - Edit
  - Write
  - Bash
```

## Status do Projeto

- [x] Fase 1.1 — Setup do projeto
- [ ] Fase 1.2 — Planner Agent
- [ ] Fase 1.3 — Executor Agent
- [ ] Fase 1.4 — Reviewer Agent
- [ ] Fase 1.5 — Orquestrador + CLI
- [ ] Fase 2 — Robustez e UX
- [ ] Fase 3 — Features avançadas

## Licença

MIT
