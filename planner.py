"""Planner agent — decomposes a task into a structured TaskPlan via the Anthropic API."""

from __future__ import annotations

from pathlib import Path

from anthropic import Anthropic

from orchestrator.config import Config
from orchestrator.models import TaskPlan

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "planner_system.md"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a software planning assistant."


async def generate_plan(task: str, config: Config, context: str = "") -> TaskPlan:
    """Call the Anthropic API to generate a TaskPlan for the given task.

    Args:
        task: Natural-language description of what needs to be done.
        config: Resolved orchestrator configuration.
        context: Optional extra context (e.g. repo structure, README).

    Returns:
        A parsed TaskPlan ready for the Executor.
    """
    # TODO: Implement in Phase 1.2
    # 1. Build messages with system prompt + task + context
    # 2. Call Anthropic Messages API (config.model)
    # 3. Parse JSON response into TaskPlan
    raise NotImplementedError("Planner will be implemented in Phase 1.2")
