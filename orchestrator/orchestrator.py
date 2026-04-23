"""Orchestrator — connects Planner -> Critic -> Executor -> Reviewer -> Decisor."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from orchestrator import context as ctx_loader
from orchestrator import critic, decisor, executor, planner, reviewer, session
from orchestrator.config import Config
from orchestrator.models import CycleRecord, CycleStatus, DecisionResult, TaskPlan

if TYPE_CHECKING:
    from orchestrator.events import EventBus, PauseController

console = Console(highlight=False)


def _ensure_git_repo(project_dir: str) -> None:
    """Initialise a git repo in project_dir if one does not already exist.

    Runs git init and, if there are tracked files, an initial commit.
    Failures are logged as warnings — the cycle always continues.
    """
    if (Path(project_dir) / ".git").exists():
        return
    try:
        subprocess.run(["git", "init"], cwd=project_dir, capture_output=True, check=True)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir, capture_output=True, text=True, check=True,
        )
        if status.stdout.strip():
            subprocess.run(["git", "add", "."], cwd=project_dir, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "chore: initial commit before orchestrator"],
                cwd=project_dir, capture_output=True, check=True,
            )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow][!] Could not initialise git repo in '{project_dir}': {exc}[/yellow]")


async def run_cycle(
    task: str,
    config: Config,
    plan: TaskPlan | None = None,
    event_bus: EventBus | None = None,
    pause_controller: PauseController | None = None,
    phase_context: str | None = None,
) -> tuple[CycleRecord, str, DecisionResult | None]:
    """Execute a full orchestration cycle for the given task.

    Flow:
        1. Load SESSAO_ATUAL.md for shared context
        2. Planner generates a TaskPlan (with session context)  [skipped if *plan* given]
        3. Critic loop refines the plan (with session context)  [skipped if *plan* given]
        4. Executor implements the refined plan
        5. Reviewer evaluates the result (with session context)
        6. If rejected and attempts < max_retries -> re-execute with feedback
        7. If approved -> Decisor validates coherence with plan
        8. If Decisor approves -> update SESSAO_ATUAL.md, return record
        9. If Decisor rejects -> escalate to user

    Args:
        task: Natural-language description of the task.
        config: Resolved orchestrator configuration.
        plan: Optional pre-built :class:`TaskPlan`.  When provided, steps 2 and
              3 (planning and critic loop) are skipped and this plan is used
              directly for execution.  Useful for retrying after editing or for
              passing a plan from a JSON file via ``--plan``.

    Returns:
        A tuple of (CycleRecord, diff string, DecisionResult | None).
        DecisionResult is None only when escalated before reaching the Decisor.
    """
    from orchestrator.events import EventType

    _ensure_git_repo(config.project_dir)

    record = CycleRecord(task=task, status=CycleStatus.PLANNED)
    last_diff = ""
    decision: DecisionResult | None = None

    async def _emit(event_type: EventType, data: dict | None = None) -> None:
        if event_bus is not None:
            await event_bus.emit(event_type, data)

    # 1. Load session context once — from the TARGET project's SESSAO_ATUAL.md
    #    Each project keeps its own session file so the Planner gets project-specific
    #    context, not the orchestrator's own development log.
    session_ctx = session.load(config.project_dir)

    if plan is not None:
        # Skip planning and critic — use the provided plan directly.
        record.plan = plan
        console.print("[dim]  [1/5] Planning... (skipped — plan provided)[/dim]")
        console.print("[dim]  [2/5] Critic loop... (skipped — plan provided)[/dim]")
    else:
        # 1b. Load project context (README, structure, stack) for the Planner
        project_ctx = ctx_loader.load_project_context(config.project_dir)
        # Prepend the absolute path so the Planner is never confused about which project it is planning for
        project_ctx = f"**Project directory:** `{config.project_dir}`\n\n{project_ctx}"

        # 2. Plan
        console.print("[blue]  [1/5] Planning...[/blue]")
        await _emit(EventType.PLAN_STARTED, {"task": task})
        record.plan = await planner.generate_plan(
            task, config, context=project_ctx, session_context=session_ctx
        )
        await _emit(EventType.PLAN_COMPLETED, {"task": task, "plan": record.plan.to_dict()})

        # 3. Critic loop — refine plan before execution
        console.print("[cyan]  [2/5] Critic loop...[/cyan]")
        record.plan = await critic.run_critic_loop(
            task, record.plan, config,
            session_context=session_ctx,
            phase_context=phase_context,
            event_bus=event_bus,
        )

    # Pause check #1 — after planning/critic, before first execution.
    # This is the primary use-case for plan editing: the user can review the
    # plan and send an edited version before the Executor starts.
    if pause_controller is not None:
        maybe_plan = await pause_controller.check_pause()
        if maybe_plan is not None:
            record.plan = maybe_plan

    # 4-6. Execute -> Review loop
    feedback = ""
    while record.attempt <= config.max_retries:
        record.status = CycleStatus.EXECUTING
        console.print(f"[green]  [3/5] Executing (attempt {record.attempt}/{config.max_retries})...[/green]")
        await _emit(EventType.EXECUTE_STARTED, {"attempt": record.attempt, "max_attempts": config.max_retries})
        last_diff = await executor.execute_plan(record.plan, config, feedback=feedback)
        await _emit(EventType.EXECUTE_COMPLETED, {
            "attempt": record.attempt,
            "diff_lines": last_diff.count("\n"),
        })

        record.status = CycleStatus.REVIEWING
        console.print("[yellow]  [4/5] Reviewing...[/yellow]")
        await _emit(EventType.REVIEW_STARTED, {"attempt": record.attempt})
        record.review = await reviewer.review_code(
            record.plan, last_diff, config, session_context=session_ctx
        )
        await _emit(EventType.REVIEW_COMPLETED, {
            "attempt": record.attempt,
            "approved": record.review.approved,
            "score": record.review.score,
            "issues_count": len(record.review.issues),
        })

        if record.review.approved:
            break

        if record.attempt >= config.max_retries:
            record.status = CycleStatus.ESCALATED
            record.finished_at = datetime.now().isoformat()
            await _emit(EventType.CYCLE_ESCALATED, {
                "task": task,
                "reason": "max_retries_exceeded",
            })
            return record, last_diff, None

        # Build feedback string for next attempt
        feedback_lines = ["The reviewer rejected your implementation. Fix the following issues:"]
        for issue in record.review.issues:
            line = f"- [{issue.severity.value.upper()}] {issue.description}"
            if issue.suggestion:
                line += f" -- Suggestion: {issue.suggestion}"
            feedback_lines.append(line)
        feedback = "\n".join(feedback_lines)

        # Pause check #2 — between execution attempts (reviewer rejected).
        # Allows the user to inspect the diff and issues before the next retry.
        if pause_controller is not None:
            await pause_controller.check_pause()

        record.attempt += 1

    # 7. Decisor — validate coherence with plan
    console.print("[magenta]  [5/5] Decisor...[/magenta]")
    await _emit(EventType.DECISION_STARTED)
    decision = await decisor.decide(
        record.plan, last_diff, record.review, config, session_context=session_ctx
    )
    record.decision = decision
    await _emit(EventType.DECISION_COMPLETED, {
        "approved": decision.approved,
        "reasoning": decision.reasoning,
        "inconsistencies": decision.inconsistencies,
    })

    if decision.approved:
        record.status = CycleStatus.APPROVED
        await _emit(EventType.CYCLE_APPROVED, {"task": task, "attempt": record.attempt})
        # 8. Update SESSAO_ATUAL.md — only on full approval
        try:
            await session.update(task, record.plan, last_diff, record.review, decision, config, project_dir=config.project_dir)
            console.print("[dim]  Session updated — SESSAO_ATUAL.md[/dim]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow][!] Could not update SESSAO_ATUAL.md: {exc}[/yellow]")
    else:
        record.status = CycleStatus.ESCALATED
        await _emit(EventType.CYCLE_ESCALATED, {
            "task": task,
            "reason": "decisor_rejected",
        })

    record.finished_at = datetime.now().isoformat()
    return record, last_diff, decision
