"""Planner agent — decomposes a task into a structured TaskPlan."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from orchestrator.config import Config
from orchestrator.models import TaskPlan
from orchestrator.providers import make_provider

if TYPE_CHECKING:
    from orchestrator.models import CriticResult

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "planner_system.md"
_FALLBACK = "You are a software planning assistant."


async def generate_plan(
    task: str,
    config: Config,
    context: str = "",
    session_context: str = "",
) -> TaskPlan:
    """Generate a TaskPlan for the given task using the configured planner provider.

    Args:
        task: Natural-language description of what needs to be done.
        config: Resolved orchestrator configuration.
        context: Optional extra context (e.g. repo structure, README).
        session_context: Contents of SESSAO_ATUAL.md for project-state awareness.

    Returns:
        A parsed TaskPlan ready for the Executor.
    """
    user_message = f"Task: {task}"
    if context:
        user_message += (
            f"\n\n## Target Project Context"
            f"\n> THIS is the project you are writing code for. "
            f"Use only paths relative to this project's root."
            f"\n\n{context}"
        )
    if session_context:
        user_message += (
            f"\n\n## Orchestrator Dev Log"
            f"\n> Background context about the AI tool's own development state."
            f" Do NOT use file paths from this section — they belong to a different project."
            f"\n\n{session_context}"
        )

    provider = make_provider(config.planner_provider, config)
    raw = await provider.call(
        prompt=user_message,
        system=config.load_prompt("planner", _PROMPT_PATH, _FALLBACK),
        max_tokens=4000,
    )
    return TaskPlan.from_json(raw)


async def refine_plan(
    task: str,
    current_plan: TaskPlan,
    critic_result: CriticResult,
    config: Config,
) -> TaskPlan:
    """Ask the Planner to improve the current plan based on Critic feedback.

    Args:
        task: Original task description.
        current_plan: The plan that was just critiqued.
        critic_result: Feedback from the Critic agent.
        config: Resolved orchestrator configuration.

    Returns:
        A revised TaskPlan that addresses the Critic's observations.
    """
    observations = "\n".join(f"- {o}" for o in critic_result.observations)
    suggestions = "\n".join(f"- {s}" for s in critic_result.suggestions)

    user_message = (
        f"Task: {task}\n\n"
        f"## Current Plan (score {critic_result.score}/10 — needs improvement)\n\n"
        f"{current_plan.to_json(indent=2)}\n\n"
        f"## Critic Observations\n\n{observations}\n\n"
        f"## Critic Suggestions\n\n{suggestions}\n\n"
        "Please produce an improved plan that addresses the critic's feedback. "
        "Return only the JSON plan."
    )

    provider = make_provider(config.planner_provider, config)
    raw = await provider.call(
        prompt=user_message,
        system=config.load_prompt("planner", _PROMPT_PATH, _FALLBACK),
        max_tokens=4000,
    )
    return TaskPlan.from_json(raw)
