"""Project Planner agent — generates a hierarchical PLANO.md from a project description."""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import Config
from orchestrator.plan import ProjectPlan, parse_plan_text
from orchestrator.providers import make_provider

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
