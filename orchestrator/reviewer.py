"""Reviewer agent — evaluates code quality."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.config import Config
from orchestrator.models import ReviewResult, TaskPlan
from orchestrator.providers import make_provider

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "reviewer_system.md"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a code review assistant."


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that some models wrap around JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    return raw


async def review_code(
    plan: TaskPlan,
    diff: str,
    config: Config,
) -> ReviewResult:
    """Review the code changes using the configured reviewer provider.

    Args:
        plan: The original TaskPlan (for context).
        diff: Unified diff of the changes to review.
        config: Resolved orchestrator configuration.

    Returns:
        A parsed ReviewResult with approval status, score, and issues.
    """
    user_message = (
        f"## Original Plan\n\n{plan.to_json(indent=2)}\n\n"
        f"## Code Diff\n\n```diff\n{diff}\n```"
    )

    provider = make_provider(config.reviewer_provider, config)
    raw = await provider.call(prompt=user_message, system=_load_system_prompt())
    return ReviewResult.from_dict(json.loads(_strip_fences(raw)))
