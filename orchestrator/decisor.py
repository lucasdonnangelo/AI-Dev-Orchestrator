"""Decisor agent — validates coherence between plan, implementation, and session context."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from orchestrator.config import Config
from orchestrator.models import DecisionResult, ReviewResult, TaskPlan
from orchestrator.providers import make_provider

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "decisor_system.md"
_SESSION_PATH = Path(__file__).resolve().parent.parent / "SESSAO_ATUAL.md"
_FALLBACK = "You are a decisor. Validate coherence between plan and implementation. Return JSON DecisionResult."

console = Console(highlight=False)


def _load_session_context() -> str:
    if _SESSION_PATH.exists():
        return _SESSION_PATH.read_text(encoding="utf-8")
    return "(no session context available)"


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    return raw


async def decide(
    plan: TaskPlan,
    diff: str,
    review: ReviewResult,
    config: Config,
    session_context: str | None = None,
) -> DecisionResult:
    """Validate coherence between the plan and what was implemented.

    Args:
        plan: The original TaskPlan approved by the Planner/Critic loop.
        diff: Unified diff of the code changes made by the Executor.
        review: The ReviewResult produced by the Reviewer.
        config: Resolved orchestrator configuration.
        session_context: Contents of SESSAO_ATUAL.md. If None, loaded from disk.

    Returns:
        A DecisionResult with approval status, reasoning, and any inconsistencies.
    """
    if session_context is None:
        session_context = _load_session_context()

    user_message = (
        f"## Original Plan\n\n{plan.to_json(indent=2)}\n\n"
        f"## Code Diff\n\n```diff\n{diff}\n```\n\n"
        f"## Review Result\n\n{json.dumps(review.to_dict(), indent=2, ensure_ascii=False)}\n\n"
        f"## Session Context (SESSAO_ATUAL.md)\n\n{session_context}"
    )

    provider = make_provider(config.decisor_provider, config)
    raw = await provider.call(
        prompt=user_message,
        system=config.load_prompt("decisor", _PROMPT_PATH, _FALLBACK),
    )
    result = DecisionResult.from_dict(json.loads(_strip_fences(raw)))

    status = "[OK] approved" if result.approved else "[X] rejected"
    console.print(f"[dim]  Decisor — {status}[/dim]")
    if result.inconsistencies:
        for item in result.inconsistencies:
            console.print(f"[dim]    - {item}[/dim]")

    return result
