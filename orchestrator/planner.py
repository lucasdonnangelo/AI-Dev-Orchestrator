"""Planner agent — decomposes a task into a structured TaskPlan via the Anthropic API."""

from __future__ import annotations

from pathlib import Path

from anthropic import AsyncAnthropic

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
    user_message = f"Task: {task}"
    if context:
        user_message += f"\n\nProject context:\n{context}"

    client = AsyncAnthropic(api_key=config.api_key)
    response = await client.messages.create(
        model=config.model,
        max_tokens=1024,
        system=_load_system_prompt(),
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text
    return TaskPlan.from_json(raw)
