"""Project Planner agent — generates a hierarchical PLANO.md from a project description."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from orchestrator.config import Config
from orchestrator.critic import critique_project_plan
from orchestrator.models import CriticResult
from orchestrator.plan import ProjectPlan, parse_plan_text
from orchestrator.providers import make_provider

console = Console(highlight=False)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "project_planner_system.md"
_FALLBACK = (
    "You are a project planner. Given a project description, generate a PLANO.md "
    "file with phases, subphases, and atomic tasks in the required Markdown format."
)


def _build_user_message(
    description: str,
    premises: str = "",
    stack: str = "",
) -> str:
    """Assemble the user prompt sent to the Project Planner agent."""
    parts = [f"## Project Description\n\n{description.strip()}"]
    if premises.strip():
        parts.append(f"## Premises and Constraints\n\n{premises.strip()}")
    if stack.strip():
        parts.append(f"## Stack / Technology Choices\n\n{stack.strip()}")
    parts.append(
        "Generate a complete PLANO.md for this project. "
        "Output ONLY the Markdown content — no surrounding explanation."
    )
    return "\n\n".join(parts)


async def generate_project_plan(
    description: str,
    config: Config,
    premises: str = "",
    stack: str = "",
) -> tuple[str, ProjectPlan]:
    """Generate a PLANO.md from a natural-language project description.

    Calls the configured planner provider (Claude by default) with a specialised
    system prompt that instructs it to produce a hierarchical Markdown plan.

    Args:
        description: Natural-language description of what the project should do.
        config: Resolved orchestrator configuration.
        premises: Optional constraints or architectural decisions already made.
        stack: Optional technology stack information (languages, frameworks, etc.).

    Returns:
        A tuple of:
        - ``raw_md``: The raw PLANO.md Markdown text as returned by the model.
        - ``plan``: The parsed :class:`~orchestrator.plan.ProjectPlan` object.

    Raises:
        ValueError: If the returned Markdown cannot be parsed as a valid plan
            (e.g. missing ``#`` title heading).
    """
    user_message = _build_user_message(description, premises=premises, stack=stack)

    provider = make_provider(config.planner_provider, config)
    raw_md = await provider.call(
        prompt=user_message,
        system=config.load_prompt("project_planner", _PROMPT_PATH, _FALLBACK),
    )

    raw_md = _strip_outer_fence(raw_md)
    plan = parse_plan_text(raw_md)
    return raw_md, plan


async def refine_project_plan(
    description: str,
    raw_md: str,
    critic_result: CriticResult,
    config: Config,
    premises: str = "",
    stack: str = "",
) -> tuple[str, ProjectPlan]:
    """Ask the Project Planner to improve the PLANO.md based on Critic feedback.

    Args:
        description: Original project description.
        raw_md: Current PLANO.md Markdown that was critiqued.
        critic_result: Feedback from the :func:`critique_project_plan` call.
        config: Resolved orchestrator configuration.
        premises: Original premises/constraints forwarded for context.
        stack: Original stack information forwarded for context.

    Returns:
        A tuple of (``raw_md``, ``plan``) with the revised PLANO.md content and
        the corresponding parsed :class:`~orchestrator.plan.ProjectPlan`.
    """
    observations = "\n".join(f"- {o}" for o in critic_result.observations)
    suggestions = "\n".join(f"- {s}" for s in critic_result.suggestions)

    base_msg = _build_user_message(description, premises=premises, stack=stack)
    user_message = (
        f"{base_msg}\n\n"
        f"## Current PLANO.md (score {critic_result.score}/10 — needs improvement)\n\n"
        f"{raw_md}\n\n"
        f"## Critic Observations\n\n{observations}\n\n"
        f"## Critic Suggestions\n\n{suggestions}\n\n"
        "Please produce an improved PLANO.md that addresses the critic's feedback. "
        "Output ONLY the Markdown content — no surrounding explanation."
    )

    provider = make_provider(config.planner_provider, config)
    new_raw = await provider.call(
        prompt=user_message,
        system=config.load_prompt("project_planner", _PROMPT_PATH, _FALLBACK),
    )
    new_raw = _strip_outer_fence(new_raw)
    plan = parse_plan_text(new_raw)
    return new_raw, plan


async def run_project_plan_critic_loop(
    description: str,
    raw_md: str,
    plan: ProjectPlan,
    config: Config,
    premises: str = "",
    stack: str = "",
) -> tuple[str, ProjectPlan]:
    """Iterative Project Planner <-> Plan Critic refinement loop.

    Mirrors the task-level :func:`~orchestrator.critic.run_critic_loop` but
    operates on the full PLANO.md Markdown instead of a ``TaskPlan`` JSON.

    Runs at least ``config.critic_min_rounds`` rounds and stops as soon as the
    Critic reaches consensus (score >= 8) or ``config.critic_max_rounds`` is
    exhausted, whichever comes first.

    Args:
        description: Original project description (used by the Critic to assess
            completeness against stated goals).
        raw_md: Initial PLANO.md Markdown generated by :func:`generate_project_plan`.
        plan: Parsed :class:`~orchestrator.plan.ProjectPlan` corresponding to
            ``raw_md``.
        config: Resolved orchestrator configuration.
        premises: Optional constraints/decisions forwarded to the refiner.
        stack: Optional stack information forwarded to the refiner.

    Returns:
        A tuple of (``raw_md``, ``plan``) representing the final, critic-approved
        PLANO.md and its parsed object.
    """
    current_raw = raw_md
    current_plan = plan

    for round_num in range(1, config.critic_max_rounds + 1):
        result = await critique_project_plan(
            current_raw, config, round_num, description=description
        )

        status = "[OK] consensus" if result.consensus else "[!] needs revision"
        console.print(
            f"[dim]  Plan Critic round {round_num}/{config.critic_max_rounds} "
            f"-- score {result.score}/10 -- {status}[/dim]"
        )

        if result.consensus and round_num >= config.critic_min_rounds:
            break

        if round_num >= config.critic_max_rounds:
            break

        current_raw, current_plan = await refine_project_plan(
            description, current_raw, result, config,
            premises=premises, stack=stack,
        )

    return current_raw, current_plan


def _strip_outer_fence(text: str) -> str:
    """Remove a surrounding markdown code fence if the model wrapped its output.

    Some models wrap the entire PLANO.md in a ```markdown ... ``` block despite
    being instructed not to. This function strips that outer fence so the result
    is clean Markdown that ``parse_plan_text`` can consume.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text

    # Remove opening fence line (e.g. ```markdown or just ```)
    lines = stripped.splitlines()
    start = 1  # skip the opening fence line
    # Find the closing fence (last ```) and strip it
    end = len(lines)
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip().startswith("```"):
            end = i
            break

    inner = "\n".join(lines[start:end])
    return inner
