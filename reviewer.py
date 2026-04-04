"""Reviewer agent — evaluates code quality via the Anthropic API."""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import Config
from orchestrator.models import ReviewResult, TaskPlan

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "reviewer_system.md"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a code review assistant."


async def review_code(
    plan: TaskPlan,
    diff: str,
    config: Config,
) -> ReviewResult:
    """Call the Anthropic API to review the code changes.

    Args:
        plan: The original TaskPlan (for context).
        diff: Unified diff of the changes to review.
        config: Resolved orchestrator configuration.

    Returns:
        A parsed ReviewResult with approval status, score, and issues.
    """
    # TODO: Implement in Phase 1.4
    # 1. Build messages with system prompt + plan + diff
    # 2. Call Anthropic Messages API (config.model)
    # 3. Parse JSON response into ReviewResult
    raise NotImplementedError("Reviewer will be implemented in Phase 1.4")
