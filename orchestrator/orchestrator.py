"""Orchestrator — connects Planner → Executor → Reviewer in a correction loop."""

from __future__ import annotations

from datetime import datetime

from orchestrator import critic, executor, planner, reviewer
from orchestrator.config import Config
from orchestrator.models import CycleRecord, CycleStatus


async def run_cycle(task: str, config: Config) -> CycleRecord:
    """Execute a full orchestration cycle for the given task.

    Flow:
        1. Planner generates a TaskPlan
        1b. Critic loop refines the plan (min 2, max 5 rounds)
        2. Executor implements the refined plan
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
    record = CycleRecord(task=task, status=CycleStatus.PLANNED)

    # 1. Plan
    record.plan = await planner.generate_plan(task, config)

    # 1b. Critic loop — refine plan before execution
    record.plan = await critic.run_critic_loop(task, record.plan, config)

    # 2-6. Execute → Review loop
    feedback = ""
    while record.attempt <= config.max_retries:
        record.status = CycleStatus.EXECUTING
        diff = await executor.execute_plan(record.plan, config, feedback=feedback)

        record.status = CycleStatus.REVIEWING
        record.review = await reviewer.review_code(record.plan, diff, config)

        if record.review.approved:
            record.status = CycleStatus.APPROVED
            break

        if record.attempt >= config.max_retries:
            record.status = CycleStatus.ESCALATED
            break

        # Build feedback string for next attempt
        feedback_lines = ["The reviewer rejected your implementation. Fix the following issues:"]
        for issue in record.review.issues:
            line = f"- [{issue.severity.value.upper()}] {issue.description}"
            if issue.suggestion:
                line += f" — Suggestion: {issue.suggestion}"
            feedback_lines.append(line)
        feedback = "\n".join(feedback_lines)

        record.attempt += 1

    record.finished_at = datetime.now().isoformat()
    return record
