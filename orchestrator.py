"""Orchestrator — connects Planner → Executor → Reviewer in a correction loop."""

from __future__ import annotations

from orchestrator.config import Config
from orchestrator.models import CycleRecord


async def run_cycle(task: str, config: Config) -> CycleRecord:
    """Execute a full orchestration cycle for the given task.

    Flow:
        1. Planner generates a TaskPlan
        2. Executor implements the plan
        3. Reviewer evaluates the result
        4. If rejected and attempts < max_retries → re-execute with feedback
        5. If approved → return record for user to confirm commit
        6. If max retries exhausted → escalate to user

    Args:
        task: Natural-language description of the task.
        config: Resolved orchestrator configuration.

    Returns:
        A CycleRecord summarizing the full cycle.
    """
    # TODO: Implement in Phase 1.5
    raise NotImplementedError("Orchestrator will be implemented in Phase 1.5")
