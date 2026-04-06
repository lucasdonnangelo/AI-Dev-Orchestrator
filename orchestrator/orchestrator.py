"""Orchestrator — connects Planner -> Critic -> Executor -> Reviewer -> Decisor."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console

from orchestrator import context as ctx_loader
from orchestrator import critic, decisor, executor, planner, reviewer, session
from orchestrator.config import Config
from orchestrator.models import CycleRecord, CycleStatus, DecisionResult

console = Console(highlight=False)


async def run_cycle(task: str, config: Config) -> tuple[CycleRecord, str, DecisionResult | None]:
    """Execute a full orchestration cycle for the given task.

    Flow:
        1. Load SESSAO_ATUAL.md for shared context
        2. Planner generates a TaskPlan (with session context)
        3. Critic loop refines the plan (with session context)
        4. Executor implements the refined plan
        5. Reviewer evaluates the result (with session context)
        6. If rejected and attempts < max_retries -> re-execute with feedback
        7. If approved -> Decisor validates coherence with plan
        8. If Decisor approves -> update SESSAO_ATUAL.md, return record
        9. If Decisor rejects -> escalate to user

    Args:
        task: Natural-language description of the task.
        config: Resolved orchestrator configuration.

    Returns:
        A tuple of (CycleRecord, diff string, DecisionResult | None).
        DecisionResult is None only when escalated before reaching the Decisor.
    """
    record = CycleRecord(task=task, status=CycleStatus.PLANNED)
    last_diff = ""
    decision: DecisionResult | None = None

    # 1. Load session context once — from the TARGET project's SESSAO_ATUAL.md
    #    Each project keeps its own session file so the Planner gets project-specific
    #    context, not the orchestrator's own development log.
    session_ctx = session.load(config.project_dir)

    # 1b. Load project context (README, structure, stack) for the Planner
    project_ctx = ctx_loader.load_project_context(config.project_dir)
    # Prepend the absolute path so the Planner is never confused about which project it is planning for
    project_ctx = f"**Project directory:** `{config.project_dir}`\n\n{project_ctx}"

    # 2. Plan
    console.print("[blue]  [1/5] Planning...[/blue]")
    record.plan = await planner.generate_plan(
        task, config, context=project_ctx, session_context=session_ctx
    )

    # 3. Critic loop — refine plan before execution
    console.print("[cyan]  [2/5] Critic loop...[/cyan]")
    record.plan = await critic.run_critic_loop(task, record.plan, config, session_context=session_ctx)

    # 4-6. Execute -> Review loop
    feedback = ""
    while record.attempt <= config.max_retries:
        record.status = CycleStatus.EXECUTING
        console.print(f"[green]  [3/5] Executing (attempt {record.attempt}/{config.max_retries})...[/green]")
        last_diff = await executor.execute_plan(record.plan, config, feedback=feedback)

        record.status = CycleStatus.REVIEWING
        console.print("[yellow]  [4/5] Reviewing...[/yellow]")
        record.review = await reviewer.review_code(
            record.plan, last_diff, config, session_context=session_ctx
        )

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

    # 7. Decisor — validate coherence with plan
    console.print("[magenta]  [5/5] Decisor...[/magenta]")
    decision = await decisor.decide(
        record.plan, last_diff, record.review, config, session_context=session_ctx
    )
    record.decision = decision

    if decision.approved:
        record.status = CycleStatus.APPROVED
        # 8. Update SESSAO_ATUAL.md — only on full approval
        try:
            await session.update(task, record.plan, last_diff, record.review, decision, config, project_dir=config.project_dir)
            console.print("[dim]  Session updated — SESSAO_ATUAL.md[/dim]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow][!] Could not update SESSAO_ATUAL.md: {exc}[/yellow]")
    else:
        record.status = CycleStatus.ESCALATED

    record.finished_at = datetime.now().isoformat()
    return record, last_diff, decision
