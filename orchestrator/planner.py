"""Planner agent — decomposes a task into a structured TaskPlan."""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import Config
from orchestrator.models import TaskPlan
from orchestrator.providers import make_provider

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "planner_system.md"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are a software planning assistant."


async def generate_plan(task: str, config: Config, context: str = "") -> TaskPlan:
    """Generate a TaskPlan for the given task using the configured planner provider.

    Args:
        task: Natural-language description of what needs to be done.
        config: Resolved orchestrator configuration.
        context: Optional extra context (e.g. repo structure, README).

    Returns:
        A parsed TaskPlan ready for the Executor.
    """
    user_message = f"Task: {task}"
    if context:
        user_message += f"\n\nProject context:\n{context}"

    provider = make_provider(config.planner_provider, config)
    raw = await provider.call(prompt=user_message, system=_load_system_prompt())
    return TaskPlan.from_json(raw)
