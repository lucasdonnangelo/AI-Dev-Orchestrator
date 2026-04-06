"""Chat module — single-turn and interactive exchanges with orchestrator agents.

Each agent is identified by its role name ("planner", "critic", "reviewer",
"decisor").  The module resolves the correct provider and system prompt from
the project :class:`~orchestrator.config.Config`, respecting any
project-level overrides defined in ``.orchestrator.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from orchestrator.providers import make_provider

if TYPE_CHECKING:
    from orchestrator.config import Config

# ---------------------------------------------------------------------------
# Role metadata
# ---------------------------------------------------------------------------

# Default system prompt file for each role (bundled with the orchestrator)
_PROMPT_PATHS: dict[str, Path] = {
    "planner":  Path(__file__).resolve().parent / "prompts" / "planner_system.md",
    "critic":   Path(__file__).resolve().parent / "prompts" / "critic_system.md",
    "reviewer": Path(__file__).resolve().parent / "prompts" / "reviewer_system.md",
    "decisor":  Path(__file__).resolve().parent / "prompts" / "decisor_system.md",
}

_FALLBACKS: dict[str, str] = {
    "planner":  "You are a software planning assistant.",
    "critic":   "You are a plan critic. Evaluate the plan and return JSON.",
    "reviewer": "You are a code review assistant.",
    "decisor":  "You are a decisor. Validate coherence between plan and implementation.",
}

#: Ordered list of all valid agent roles.
ROLES: list[str] = list(_PROMPT_PATHS)


def _provider_name_for_role(role: str, config: "Config") -> str:
    """Return the configured provider name for *role*."""
    return {
        "planner":  config.planner_provider,
        "critic":   config.critic_provider,
        "reviewer": config.reviewer_provider,
        "decisor":  config.decisor_provider,
    }[role]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def send(role: str, message: str, config: "Config") -> str:
    """Send a single message to the agent for *role* and return the response.

    Uses the provider and system prompt configured for *role*, respecting any
    project-level overrides in ``config.prompt_overrides``.

    Args:
        role: One of ``"planner"``, ``"critic"``, ``"reviewer"``, ``"decisor"``.
        message: User-turn content to send to the agent.
        config: Resolved orchestrator configuration.

    Returns:
        The agent's raw text response as a string.

    Raises:
        KeyError: If *role* is not a recognised agent role.
    """
    if role not in _PROMPT_PATHS:
        raise KeyError(
            f"Unknown role {role!r}. Valid roles: {', '.join(ROLES)}"
        )

    provider_name = _provider_name_for_role(role, config)
    provider = make_provider(provider_name, config)
    system = config.load_prompt(role, _PROMPT_PATHS[role], _FALLBACKS[role])
    return await provider.call(message, system=system)
