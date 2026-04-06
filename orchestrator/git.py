"""Git helpers — branch creation, conventional commits, and PR description."""

from __future__ import annotations

import re
import subprocess

# ---------------------------------------------------------------------------
# Conventional commit type detection
# ---------------------------------------------------------------------------

_COMMIT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "fix": [
        "fix", "corrigir", "bug", "erro", "error", "patch", "hotfix",
        "correcao", "correção", "broken", "quebrado",
    ],
    "docs": [
        "doc", "readme", "document", "documentar", "comentar", "comment",
        "wiki", "changelog",
    ],
    "test": [
        "test", "teste", "spec", "coverage", "cobertura", "pytest", "unittest",
    ],
    "refactor": [
        "refactor", "refatorar", "cleanup", "limpeza", "reorganizar",
        "reorganize", "rename", "renomear", "mover", "move",
    ],
    "chore": [
        "chore", "config", "setup", "dep", "dependencia", "dependência",
        "upgrade", "atualizar", "bump", "ci", "lint",
    ],
    "perf": [
        "performance", "otimizar", "optimize", "speed", "velocidade", "cache",
    ],
    "style": [
        "style", "format", "formatter", "estilo",
    ],
}


def detect_commit_type(task: str) -> str:
    """Infer a conventional commit type from a task description."""
    lower = task.lower()
    for commit_type, keywords in _COMMIT_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return commit_type
    return "feat"


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def task_slug(task: str, max_len: int = 50) -> str:
    """Convert a task description to a kebab-case slug."""
    slug = task.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_len].rstrip("-")


def make_branch_name(task: str) -> str:
    """Build a git branch name like ``feat/task-slug``."""
    return f"{detect_commit_type(task)}/{task_slug(task)}"


def make_commit_message(task: str) -> str:
    """Build a conventional commit message from a task description.

    Format: ``<type>: <description>`` (total <= 72 chars).
    """
    commit_type = detect_commit_type(task)
    max_desc = 72 - len(commit_type) - 2  # "type: "
    return f"{commit_type}: {task[:max_desc]}"


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def create_branch(project_dir: str, branch_name: str) -> bool:
    """Create and checkout a new git branch. Returns True on success."""
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_current_branch(project_dir: str) -> str:
    """Return the name of the current git branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# PR description
# ---------------------------------------------------------------------------

def build_pr_description(task: str, record) -> str:  # record: CycleRecord
    """Build a markdown PR description from a completed CycleRecord.

    No AI call — built from structured data already available.
    """
    plan = record.plan
    review = record.review
    decision = record.decision

    lines: list[str] = [
        f"## {task}",
        "",
        "### What was done",
        "",
    ]

    if plan:
        if plan.files_to_create:
            lines.append("**Files created:** " + ", ".join(f"`{f}`" for f in plan.files_to_create))
        if plan.files_to_modify:
            lines.append("**Files modified:** " + ", ".join(f"`{f}`" for f in plan.files_to_modify))
        if plan.steps:
            lines.append("")
            lines.append("**Steps executed:**")
            for step in plan.steps:
                lines.append(f"- {step}")

    lines += ["", "### Review", ""]
    if review:
        status = "[OK] Approved" if review.approved else "[X] Rejected"
        lines.append(f"**Status:** {status}  |  **Score:** {review.score}/10")
        if review.summary:
            lines.append(f"\n{review.summary}")

    if decision:
        lines += ["", "### Coherence check (Decisor)", ""]
        d_status = "[OK] Coherent" if decision.approved else "[X] Inconsistent"
        lines.append(f"**Status:** {d_status}")
        if decision.reasoning:
            lines.append(f"\n{decision.reasoning}")

    if record.commit_hash:
        lines += ["", f"**Commit:** `{record.commit_hash}`"]

    lines += [
        "",
        "---",
        "_Generated by AI Dev Orchestrator_",
    ]

    return "\n".join(lines)
