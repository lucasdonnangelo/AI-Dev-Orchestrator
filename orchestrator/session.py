"""Session manager — loads and auto-updates SESSAO_ATUAL.md after each approved cycle."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.config import Config
from orchestrator.models import DecisionResult, ReviewResult, TaskPlan
from orchestrator.providers import make_provider

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "session_update_system.md"
_SESSION_FILENAME = "SESSAO_ATUAL.md"


def _session_path(project_dir: str | Path | None = None) -> Path:
    """Return the SESSAO_ATUAL.md path for the given project directory.

    If *project_dir* is provided, the file is co-located with the project.
    Falls back to the orchestrator's own root when *project_dir* is None.
    """
    if project_dir is not None:
        return Path(project_dir).resolve() / _SESSION_FILENAME
    # Legacy fallback — orchestrator's own root
    return Path(__file__).resolve().parent.parent / _SESSION_FILENAME


def load(project_dir: str | Path | None = None) -> str:
    """Return the contents of the project's SESSAO_ATUAL.md, or empty string.

    Each target project keeps its own session file so that the Planner
    receives context specific to that project — not the orchestrator's own
    development log.
    """
    path = _session_path(project_dir)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a session updater. Update SESSAO_ATUAL.md and return the full updated file."


async def update(
    task: str,
    plan: TaskPlan,
    diff: str,
    review: ReviewResult,
    decision: DecisionResult,
    config: Config,
    project_dir: str | Path | None = None,
) -> None:
    """Generate an updated SESSAO_ATUAL.md and write it to disk.

    Called after a cycle where both the Reviewer and the Decisor approved.

    Args:
        task: The natural-language task that was just completed.
        plan: The final TaskPlan that was executed.
        diff: Unified diff of the changes made by the Executor.
        review: The Reviewer's evaluation result.
        decision: The Decisor's validation result.
        config: Resolved orchestrator configuration.
    """
    current = load(project_dir)

    user_message = (
        f"## Current SESSAO_ATUAL.md\n\n{current}\n\n"
        f"## Task Just Completed\n\n{task}\n\n"
        f"## Plan Executed\n\n{plan.to_json(indent=2)}\n\n"
        f"## Diff Summary\n\n```diff\n{diff[:3000]}\n```\n\n"
        f"## Review Result\n\n{json.dumps(review.to_dict(), indent=2, ensure_ascii=False)}\n\n"
        f"## Decision Result\n\n{json.dumps(decision.to_dict(), indent=2, ensure_ascii=False)}"
    )

    provider = make_provider(config.decisor_provider, config)
    updated_content = await provider.call(prompt=user_message, system=_load_system_prompt())

    # Strip accidental markdown fences wrapping the whole file
    updated_content = updated_content.strip()
    if updated_content.startswith("```"):
        updated_content = updated_content.split("```", 2)[1]
        if updated_content.startswith(("markdown", "md")):
            updated_content = updated_content.split("\n", 1)[1]
        updated_content = updated_content.rsplit("```", 1)[0].strip()

    _session_path(project_dir).write_text(updated_content, encoding="utf-8")
