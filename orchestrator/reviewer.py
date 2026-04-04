"""Reviewer agent — evaluates code quality via the Anthropic API."""

from __future__ import annotations

import json
from pathlib import Path

from anthropic import AsyncAnthropic

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
    user_message = (
        f"## Original Plan\n\n{plan.to_json(indent=2)}\n\n"
        f"## Code Diff\n\n```diff\n{diff}\n```"
    )

    client = AsyncAnthropic(api_key=config.api_key)
    response = await client.messages.create(
        model=config.model,
        max_tokens=1024,
        system=_load_system_prompt(),
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text
    # Strip markdown fences if the model wraps the JSON anyway
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    return ReviewResult.from_dict(json.loads(raw))
