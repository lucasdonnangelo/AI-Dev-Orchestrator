"""Orchestrator — connects Planner → Critic → Executor → Reviewer → Decisor."""

from __future__ import annotations

from datetime import datetime

from orchestrator import critic, decisor, executor, planner, reviewer
from orchestrator.config import Config
from orchestrator.models import CycleRecord, CycleStatus, DecisionResult


async def run_cycle(task: str, config: Config) -> tuple[CycleRecord, str, DecisionResult | None]:
    """Execute a full orchestration cycle for the given task.

    Flow:
        1. Planner generates a TaskPlan
        2. Critic loop refines the plan (min 2, max 5 rounds)
        3. Executor implements the refined plan
        4. Reviewer evaluates the result
        5. If rejected and attempts < max_retries → re-execute with feedback
        6. If approved → Decisor validates coherence with plan
        7. If Decisor rejects → escalate to user
        8. If Decisor approves → return record for user to confirm commit

    Args:
        task: Natural-language description of the task.
        config: Resolved orchestrator configuration.

    Returns:
        A tuple of (CycleRecord, diff string, DecisionResult | None).
        DecisionResult is None only when the cycle is escalated before reaching the Decisor.
    """
    record = CycleRecord(task=task, status=CycleStatus.PLANNED)
    last_diff = ""
    decision: DecisionResult | None = None

    # 1. Plan
    record.plan = await planner.generate_plan(task, config)

    # 2. Critic loop — refine plan before execution
    record.plan = await critic.run_critic_loop(task, record.plan, config)

    # 3-5. Execute → Review loop
    feedback = ""
    while record.attempt <= config.max_retries:
        record.status = CycleStatus.EXECUTING
        last_diff = await executor.execute_plan(record.plan, config, feedback=feedback)

        record.status = CycleStatus.REVIEWING
        record.review = await reviewer.review_code(record.plan, last_diff, config)

        if record.review.approved:
            break

        if record.attempt >= config.max_retries:
            record.status = CycleStatus.ESCALATED
            record.finished_at = datetime.now().isoformat()
            return record, last_diff, None

        # Build feedback string for next attempt
        feedback_lines = ["The reviewer rejected your implementation. Fix the following issues:"]
        for issue in record.review.issues:
            line = f"- [{issue.severity.value.upper()}] {issue.description}"
            if issue.suggestion:
                line += f" -- Suggestion: {issue.suggestion}"
            feedback_lines.append(line)
        feedback = "\n".join(feedback_lines)

        record.attempt += 1

    # 6. Decisor — validate coherence with plan
    decision = await decisor.decide(record.plan, last_diff, record.review, config)
    record.decision = decision

    if decision.approved:
        record.status = CycleStatus.APPROVED
    else:
        record.status = CycleStatus.ESCALATED

    record.finished_at = datetime.now().isoformat()
    return record, last_diff, decision
