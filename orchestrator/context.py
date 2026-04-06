"""Project context loader — collects README, structure, and stack info for AI agents."""

from __future__ import annotations

from pathlib import Path

# Cap total context size to avoid token overflow (~8 k tokens)
_MAX_CONTEXT_CHARS = 24_000
_README_MAX_CHARS = 6_000
_STRUCTURE_MAX_FILES = 80

_STACK_INDICATORS: dict[str, list[str]] = {
    "python": ["pyproject.toml", "setup.py", "requirements.txt"],
    "node": ["package.json"],
    "go": ["go.mod"],
    "rust": ["Cargo.toml"],
    "java": ["pom.xml", "build.gradle"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
}

_IGNORE_DIRS: set[str] = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "logs",
    ".tox",
    ".eggs",
}


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

def _detect_stack(project_dir: Path) -> list[str]:
    """Return list of detected tech stacks based on indicator files."""
    detected: list[str] = []
    for stack, indicators in _STACK_INDICATORS.items():
        for indicator in indicators:
            if (project_dir / indicator).exists():
                detected.append(stack)
                break
    return detected


# ---------------------------------------------------------------------------
# README loader
# ---------------------------------------------------------------------------

def _load_readme(project_dir: Path) -> str:
    """Return README content (truncated to _README_MAX_CHARS), or empty string."""
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        path = project_dir / name
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace")
            if len(content) > _README_MAX_CHARS:
                content = content[:_README_MAX_CHARS] + "\n... [truncated]"
            return f"## README\n\n{content}\n"
    return ""


# ---------------------------------------------------------------------------
# Directory tree
# ---------------------------------------------------------------------------

def _build_tree(project_dir: Path) -> str:
    """Build a compact directory tree string, skipping noise directories."""
    # Use "." as root so the model does NOT prefix paths with the project folder name.
    lines: list[str] = [". (project root)"]
    count = 0

    def _walk(path: Path, prefix: str = "", depth: int = 0) -> None:
        nonlocal count
        if depth > 4 or count >= _STRUCTURE_MAX_FILES:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in _IGNORE_DIRS:
                continue
            if entry.name.startswith(".") and entry.name not in {
                ".env.example",
                ".orchestrator.yaml",
            }:
                continue
            if entry.suffix in {".pyc", ".pyo"}:
                continue
            count += 1
            if count > _STRUCTURE_MAX_FILES:
                lines.append(f"{prefix}... [truncated]")
                return
            lines.append(f"{prefix}+- {entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                _walk(entry, prefix + "|  ", depth + 1)

    _walk(project_dir)
    return (
        "## Project Structure\n\n"
        "> All paths are relative to the project root. "
        "Do NOT include the project folder name as a prefix.\n\n"
        "```\n" + "\n".join(lines) + "\n```\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_project_context(project_dir: str | Path) -> str:
    """Load README + directory tree + stack detection for a project.

    Returns a markdown string ready to be injected into the Planner prompt.
    Total length is capped at _MAX_CONTEXT_CHARS.

    Args:
        project_dir: Root directory of the target project.

    Returns:
        Markdown string with project context (stack, README, structure).
    """
    root = Path(project_dir).resolve()
    parts: list[str] = []

    stacks = _detect_stack(root)
    if stacks:
        parts.append(f"## Detected Stack\n\n{', '.join(stacks)}\n")

    readme = _load_readme(root)
    if readme:
        parts.append(readme)

    parts.append(_build_tree(root))

    combined = "\n".join(parts)
    if len(combined) > _MAX_CONTEXT_CHARS:
        combined = combined[:_MAX_CONTEXT_CHARS] + "\n\n... [context truncated]"

    return combined
