"""Project templates for `orchestrate init`.

Each template generates a `.orchestrator.yaml` and a `tasks.txt` (plus any
skeleton files) in the target directory so the user can start an orchestrated
dev cycle immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Template:
    name: str
    description: str
    # Maps relative path -> file content.  Directories are created as needed.
    files: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

_FASTAPI = Template(
    name="fastapi",
    description="FastAPI REST API (Python + Pydantic + Uvicorn)",
    files={
        ".orchestrator.yaml": """\
# .orchestrator.yaml — fastapi template
# Overrides for this project. Remove or adjust as needed.
critic_min_rounds: 2
critic_max_rounds: 5
max_retries: 3
git_conventional_commits: true
# template: fastapi

# --- Custom prompts (Phase 4.2) ---
# Override any agent's system prompt with inline text or a path relative to
# this directory.  Uncomment and edit to customise behaviour for your stack.
#
# prompts:
#   planner: "prompts/my_planner.md"   # path relative to project root
#   reviewer: |                         # inline multi-line text
#     You are a strict FastAPI code reviewer.
#     Focus on: Pydantic validation, async correctness, OpenAPI spec quality.
#     Return JSON ReviewResult.

# --- Plugin providers (Phase 4.3) ---
# Register third-party provider classes by short name.
# Each value is a "module.ClassName" import path; the class must subclass
# BaseAgent and accept a single Config argument in its constructor.
#
# providers:
#   mistral: "my_project.providers.MistralProvider"
#   local: "llama_provider.LlamaProvider"
#
# Then use the short name anywhere a provider is configured:
#   planner_provider: mistral
#   critic_provider: local
""",
        "tasks.txt": """\
# FastAPI Project — starter tasks
# Run: orchestrate batch tasks.txt -d . -y
Criar estrutura inicial com pyproject.toml e dependencias fastapi uvicorn pydantic
Criar app/main.py com instancia FastAPI e rota GET /health retornando status ok
Criar modelo Pydantic Item com campos id title description e price
Criar rota POST /items que valida e persiste um item em lista na memoria
Criar rota GET /items que retorna todos os itens salvos
Criar rota GET /items/{item_id} que retorna item pelo id ou 404
Adicionar testes com pytest e httpx para todas as rotas CRUD
""",
    },
)

_PYTHON_CLI = Template(
    name="python-cli",
    description="CLI Python com Click e persistencia JSON",
    files={
        ".orchestrator.yaml": """\
# .orchestrator.yaml — python-cli template
critic_min_rounds: 2
critic_max_rounds: 4
max_retries: 3
git_conventional_commits: true
# template: python-cli

# --- Custom prompts (Phase 4.2) ---
# prompts:
#   planner: "prompts/my_planner.md"
#   reviewer: "You are a strict CLI code reviewer. Focus on click API usage and error handling."
""",
        "tasks.txt": """\
# Python CLI — starter tasks
# Run: orchestrate batch tasks.txt -d . -y
Criar estrutura inicial com pyproject.toml e dependencia click
Criar pacote principal com __init__.py e modulo cli.py com grupo de comandos e --version
Criar modelo Item com dataclass campos id title e created_at
Implementar storage JSON com funcoes save e load
Implementar comando add que cria e persiste um Item
Implementar comando list que exibe todos os itens em tabela rich
Implementar comando delete que remove um Item pelo id
Adicionar testes unitarios para storage e para cada comando
""",
    },
)

_REACT = Template(
    name="react",
    description="React + TypeScript + Vite (frontend SPA)",
    files={
        ".orchestrator.yaml": """\
# .orchestrator.yaml — react template
critic_min_rounds: 2
critic_max_rounds: 5
max_retries: 3
git_conventional_commits: true
# template: react

# --- Custom prompts (Phase 4.2) ---
# prompts:
#   planner: "prompts/my_planner.md"
#   reviewer: "You are a strict React/TypeScript reviewer. Focus on hooks rules, type safety, and accessibility."
""",
        "tasks.txt": """\
# React TypeScript — starter tasks
# Run: orchestrate batch tasks.txt -d . -y
Criar estrutura inicial com package.json typescript react react-dom e vite
Criar tipo Item com campos id title e completed em src/types.ts
Criar componente ItemList que renderiza lista de Items com props items e onToggle
Criar componente ItemForm com input controlado e botao para adicionar novo Item
Conectar ItemList e ItemForm no App com useState gerenciando a lista de items
Estilizar componentes com CSS modules mantendo layout responsivo simples
Adicionar testes com vitest e testing-library para ItemList e ItemForm
""",
    },
)

# Registry
_REGISTRY: dict[str, Template] = {
    t.name: t for t in [_FASTAPI, _PYTHON_CLI, _REACT]
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates() -> list[Template]:
    """Return all available templates sorted by name."""
    return sorted(_REGISTRY.values(), key=lambda t: t.name)


def get_template(name: str) -> Template | None:
    """Return the template with the given name, or None if not found."""
    return _REGISTRY.get(name)


def init_project(template: Template, directory: Path, force: bool = False) -> list[str]:
    """Write template files into *directory*.

    Args:
        template: Template to apply.
        directory: Target directory (created if it does not exist).
        force: Overwrite existing files when True.  When False, raises
               FileExistsError listing any conflicting paths.

    Returns:
        List of relative file paths that were written.

    Raises:
        FileExistsError: If *force* is False and any target file already exists.
    """
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)

    # Conflict check (fail-fast before writing anything)
    if not force:
        conflicts = [
            rel for rel in template.files if (directory / rel).exists()
        ]
        if conflicts:
            joined = ", ".join(conflicts)
            raise FileExistsError(
                f"Files already exist in {directory}: {joined}. "
                "Use --force to overwrite."
            )

    written: list[str] = []
    for rel_path, content in template.files.items():
        target = directory / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(rel_path)

    return written
