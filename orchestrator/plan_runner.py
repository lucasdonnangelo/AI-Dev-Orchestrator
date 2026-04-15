"""Motor de execucao por plano — runs tasks from PLANO.md sequentially.

Flow per task:
    1. Skip tasks already in a terminal state (done / skipped)
    2. Prompt user on previously-escalated tasks (retry / skip / abort)
    3. Mark task as RUNNING and persist to PLANO.md
    4. Build accumulated phase context (completed tasks in same phase)
    5. Call run_cycle with augmented task description
    6. On approval: commit, mark DONE, persist
    7. On escalation: mark ESCALATED, persist, optionally continue
    8. Pause at subphase / phase boundaries (configurable)
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from orchestrator import git as git_helpers
from orchestrator import logger as log_store
from orchestrator.config import Config
from orchestrator.models import CycleStatus
from orchestrator.orchestrator import run_cycle
from orchestrator.plan import (
    Phase,
    PlanTask,
    PlanTaskStatus,
    ProjectPlan,
    SubPhase,
    parse_plan,
    write_plan,
)

console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass
class RunPlanOptions:
    """Options controlling how :func:`run_plan` executes the project plan."""

    # --- filters ---
    phase: str | None = None        # execute only tasks in this phase ID (e.g. "1")
    subtask: str | None = None      # execute only tasks in this subphase ID (e.g. "1.1")

    # --- execution mode ---
    auto_continue: bool = False     # never pause between subphases / phases
    dry_run: bool = False           # print what would run without executing

    # --- pause points ---
    pause_after_subtask: bool = True   # pause for validation at end of each subphase
    pause_after_phase: bool = True     # pause for validation at end of each phase

    # --- interaction ---
    yes: bool = False               # skip all confirmation prompts (commits, pauses)
    quiet: bool = False             # suppress non-essential output
    verbose: bool = False           # show extra detail (review issues, suggestions)


@dataclass
class TaskResult:
    """Outcome of executing a single :class:`~orchestrator.plan.PlanTask`."""

    task_id: str
    description: str
    # "done" | "escalated" | "skipped" | "dry_run" | "already_done"
    status: str
    commit_hash: str | None = None
    error: str | None = None


@dataclass
class RunPlanResult:
    """Overall result of a :func:`run_plan` call."""

    plan_name: str
    tasks_done: int = 0
    tasks_escalated: int = 0
    tasks_skipped: int = 0
    tasks_dry_run: int = 0
    results: list[TaskResult] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        return self.tasks_done + self.tasks_escalated + self.tasks_skipped + self.tasks_dry_run

    @property
    def success(self) -> bool:
        """True when at least one task was done and none were escalated."""
        return self.tasks_done > 0 and self.tasks_escalated == 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _StopExecution(Exception):
    """Raised internally when the user declines to continue past a boundary."""


def _commit_task(project_dir: str, message: str) -> str | None:
    """Run ``git add . && git commit``.  Returns the short hash or None."""
    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def _build_phase_context(plan: ProjectPlan, current_task: PlanTask) -> str:
    """Return a Markdown string summarising completed tasks in the current phase.

    Prepended to the task description so the Planner and Critic have full
    context of what was already implemented before planning the next step.
    Returns an empty string when no tasks have been completed yet.
    """
    current_phase: Phase | None = None

    for ph in plan.phases:
        for sp in ph.subphases:
            if any(t.id == current_task.id for t in sp.tasks):
                current_phase = ph
                break
        if current_phase is not None:
            break

    if current_phase is None:
        return ""

    done_tasks = [
        t
        for sp in current_phase.subphases
        for t in sp.tasks
        if t.is_done and t.id != current_task.id
    ]
    if not done_tasks:
        return ""

    lines: list[str] = [
        f"## Context: tasks already completed in Phase {current_phase.id} — {current_phase.name}",
        "",
    ]
    for sp in current_phase.subphases:
        done_in_sp = [t for t in sp.tasks if t.is_done and t.id != current_task.id]
        if done_in_sp:
            lines.append(f"### {sp.id} {sp.name}")
            for t in done_in_sp:
                commit_note = f" (commit: {t.commit_hash})" if t.commit_hash else ""
                lines.append(f"- [x] {t.id} {t.description}{commit_note}")
            lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _collect_entries(
    plan: ProjectPlan,
    options: RunPlanOptions,
) -> list[tuple[Phase, SubPhase, PlanTask]]:
    """Return ordered (phase, subphase, task) tuples matching the given filters."""
    result: list[tuple[Phase, SubPhase, PlanTask]] = []
    for phase in plan.phases:
        if options.phase and phase.id != options.phase:
            continue
        for sp in phase.subphases:
            if options.subtask and sp.id != options.subtask:
                continue
            for task in sp.tasks:
                result.append((phase, sp, task))
    return result


def _last_task_in_subphase(
    entries: list[tuple[Phase, SubPhase, PlanTask]], sp_id: str
) -> str | None:
    last: str | None = None
    for _, sp, task in entries:
        if sp.id == sp_id:
            last = task.id
    return last


def _last_task_in_phase(
    entries: list[tuple[Phase, SubPhase, PlanTask]], phase_id: str
) -> str | None:
    last: str | None = None
    for ph, _, task in entries:
        if ph.id == phase_id:
            last = task.id
    return last


def _next_phase(plan: ProjectPlan, current_phase_id: str) -> Phase | None:
    for i, ph in enumerate(plan.phases):
        if ph.id == current_phase_id and i + 1 < len(plan.phases):
            return plan.phases[i + 1]
    return None


def _next_subphase(plan: ProjectPlan, current_sp_id: str) -> SubPhase | None:
    all_sps = [sp for ph in plan.phases for sp in ph.subphases]
    for i, sp in enumerate(all_sps):
        if sp.id == current_sp_id and i + 1 < len(all_sps):
            return all_sps[i + 1]
    return None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _show_subphase_summary(sp: SubPhase, results: list[TaskResult]) -> None:
    """Print a compact summary for a completed subphase."""
    prefix = sp.id + "."
    done = [r for r in results if r.status == "done" and r.task_id.startswith(prefix)]
    escalated = [r for r in results if r.status == "escalated" and r.task_id.startswith(prefix)]
    skipped = [r for r in results if r.status == "skipped" and r.task_id.startswith(prefix)]
    lines = [
        f"[bold]Subfase {sp.id} — {sp.name}[/bold]",
        f"[green]{len(done)} done[/green]  "
        f"[red]{len(escalated)} escalated[/red]  "
        f"[yellow]{len(skipped)} skipped[/yellow]",
    ]
    for r in done:
        commit = f"  ({r.commit_hash})" if r.commit_hash else ""
        lines.append(f"  [green][x][/green] {r.task_id}  {r.description[:60]}{commit}")
    console.print(Panel("\n".join(lines), title="Subfase complete", border_style="cyan"))


def _show_phase_summary(phase: Phase, results: list[TaskResult]) -> None:
    """Print a compact summary for a completed phase."""
    all_ids = {t.id for t in phase.all_tasks}
    phase_results = [r for r in results if r.task_id in all_ids]
    done = [r for r in phase_results if r.status == "done"]
    escalated = [r for r in phase_results if r.status == "escalated"]
    skipped = [r for r in phase_results if r.status == "skipped"]
    lines = [
        f"[bold]Phase {phase.id} — {phase.name}[/bold]",
        f"[green]{len(done)} done[/green]  "
        f"[red]{len(escalated)} escalated[/red]  "
        f"[yellow]{len(skipped)} skipped[/yellow]",
    ]
    commits = [r.commit_hash for r in done if r.commit_hash]
    if commits:
        lines.append("")
        lines.append("[dim]Commits:[/dim]")
        for c in commits:
            lines.append(f"  [dim]{c}[/dim]")
    console.print(Panel("\n".join(lines), title="Phase complete", border_style="green"))


def _show_run_summary(result: RunPlanResult) -> None:
    """Print the overall execution summary."""
    lines = [
        f"[bold]{result.plan_name}[/bold]",
        "",
        f"[green]{result.tasks_done} done[/green]  "
        f"[red]{result.tasks_escalated} escalated[/red]  "
        f"[yellow]{result.tasks_skipped} skipped[/yellow]  "
        f"[dim]{result.tasks_dry_run} dry-run[/dim]",
    ]
    if result.success:
        status_style, status_text = "green", "[OK] Plan complete"
    elif result.tasks_escalated:
        status_style = "red"
        status_text = "[!] Stopped — escalation(s) require manual intervention"
    else:
        status_style, status_text = "yellow", "[!] No tasks were executed"

    lines.append(f"\n[{status_style}]{status_text}[/{status_style}]")
    console.print(Panel("\n".join(lines), title="Run summary", border_style=status_style))


def _maybe_pause_boundaries(
    task: PlanTask,
    ph: Phase,
    sp: SubPhase,
    last_in_subphase: dict[str, str | None],
    last_in_phase: dict[str, str | None],
    plan: ProjectPlan,
    result: RunPlanResult,
    options: RunPlanOptions,
) -> None:
    """Pause for human confirmation at subphase / phase boundaries.

    Raises :exc:`_StopExecution` when the user declines to continue.
    Does nothing when ``auto_continue`` or ``yes`` is set.
    """
    if options.auto_continue or options.yes:
        return

    is_last_in_phase = last_in_phase.get(ph.id) == task.id
    is_last_in_subphase = last_in_subphase.get(sp.id) == task.id

    # Phase boundary takes priority over subphase boundary.
    if is_last_in_phase and options.pause_after_phase:
        _show_phase_summary(ph, result.results)
        next_phase = _next_phase(plan, ph.id)
        if next_phase:
            if not click.confirm(
                f"\nContinue to Phase {next_phase.id} — {next_phase.name}?",
                default=True,
            ):
                console.print("[yellow]Execution stopped by user.[/yellow]")
                raise _StopExecution()
        return

    if is_last_in_subphase and options.pause_after_subtask:
        _show_subphase_summary(sp, result.results)
        next_sp = _next_subphase(plan, sp.id)
        if next_sp:
            if not click.confirm(
                f"\nContinue to Subfase {next_sp.id} — {next_sp.name}?",
                default=True,
            ):
                console.print("[yellow]Execution stopped by user.[/yellow]")
                raise _StopExecution()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_plan(  # noqa: C901
    plan_path: str | Path,
    config: Config,
    options: RunPlanOptions | None = None,
) -> RunPlanResult:
    """Execute tasks from PLANO.md sequentially through the full agent cycle.

    Reads the plan, identifies tasks to execute (optionally filtered by phase
    or subphase), and runs each through :func:`~orchestrator.orchestrator.run_cycle`.
    After every state change the PLANO.md is persisted so that execution can
    be resumed from the last completed task if interrupted.

    Pause behaviour
    ---------------
    By default the runner pauses for human confirmation at the end of each
    subphase and phase (unless ``auto_continue=True`` or ``yes=True``).

    Idempotency
    -----------
    Already-done and skipped tasks are silently passed over.
    Previously-escalated tasks prompt the user (retry / skip / abort).

    Accumulated context
    -------------------
    Before each task the runner builds a Markdown summary of all completed
    tasks in the same phase and prepends it to the task description so the
    Planner and Critic have full context of prior work.

    Args:
        plan_path: Path to the ``PLANO.md`` file.
        config: Resolved orchestrator configuration.
        options: Execution options.  Defaults to :class:`RunPlanOptions` with
            all defaults (pause after each subphase/phase, interactive prompts).

    Returns:
        A :class:`RunPlanResult` with per-task outcomes and aggregate counts.
    """
    if options is None:
        options = RunPlanOptions()

    plan_path = Path(plan_path)
    plan = parse_plan(plan_path)
    result = RunPlanResult(plan_name=plan.name)

    entries = _collect_entries(plan, options)

    if not entries:
        console.print("[yellow][!] No tasks match the given filters.[/yellow]")
        return result

    # Pre-compute which task ID marks the last position in each subphase/phase.
    subphase_ids = list(dict.fromkeys(sp.id for _, sp, _ in entries))
    phase_ids = list(dict.fromkeys(ph.id for ph, _, _ in entries))
    last_in_subphase = {sid: _last_task_in_subphase(entries, sid) for sid in subphase_ids}
    last_in_phase = {pid: _last_task_in_phase(entries, pid) for pid in phase_ids}

    # --- dry run ---
    if options.dry_run:
        console.print(Panel(
            f"[bold]{plan.name}[/bold]  [dim](dry run — nothing will be executed)[/dim]",
            title="Plan Runner",
            border_style="dim",
        ))
        _ICON: dict[str, str] = {
            "pending": "[ ]", "running": "[>]", "done": "[x]",
            "escalated": "[!]", "skipped": "[-]",
        }
        for _, _, task in entries:
            icon = _ICON.get(task.status.value, "[ ]")
            console.print(
                f"  {icon} {task.id}  {task.description}  [dim]({task.status.value})[/dim]"
            )
            result.tasks_dry_run += 1
            result.results.append(TaskResult(
                task_id=task.id, description=task.description, status="dry_run",
            ))
        _show_run_summary(result)
        return result

    console.print(Panel(f"[bold]{plan.name}[/bold]", title="Plan Runner", border_style="blue"))

    try:
        for ph, sp, task in entries:

            # ---- skip terminal tasks ------------------------------------------------

            if task.status == PlanTaskStatus.DONE:
                if not options.quiet:
                    console.print(
                        f"  [green][x][/green] {task.id}  {task.description}"
                        f"  [dim](already done — skipping)[/dim]"
                    )
                result.results.append(TaskResult(
                    task_id=task.id, description=task.description,
                    status="already_done", commit_hash=task.commit_hash,
                ))
                _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)
                continue

            if task.status == PlanTaskStatus.SKIPPED:
                if not options.quiet:
                    console.print(
                        f"  [yellow][-][/yellow] {task.id}  {task.description}  [dim](skipped)[/dim]"
                    )
                result.tasks_skipped += 1
                result.results.append(TaskResult(
                    task_id=task.id, description=task.description, status="skipped",
                ))
                _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)
                continue

            # ---- previously escalated ----------------------------------------------

            if task.status == PlanTaskStatus.ESCALATED:
                console.print(
                    f"\n  [red][!][/red] {task.id}  {task.description}"
                    f"  [dim](previously escalated)[/dim]"
                )
                if options.yes:
                    console.print("  [yellow]Auto-skipping escalated task (--yes mode).[/yellow]")
                    result.tasks_skipped += 1
                    result.results.append(TaskResult(
                        task_id=task.id, description=task.description, status="skipped",
                    ))
                    _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)
                    continue

                action = click.prompt(
                    "  Previously escalated. What now?",
                    type=click.Choice(["retry", "skip", "abort"]),
                    default="skip",
                    show_choices=True,
                )
                if action == "abort":
                    console.print("[yellow]Execution stopped by user.[/yellow]")
                    raise _StopExecution()
                if action == "skip":
                    result.tasks_skipped += 1
                    result.results.append(TaskResult(
                        task_id=task.id, description=task.description, status="skipped",
                    ))
                    _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)
                    continue
                # "retry" — reset to pending and fall through to execution
                task.reset()
                write_plan(plan, plan_path)

            # ---- execute task -------------------------------------------------------

            console.print(Rule(f"[bold]{task.id}[/bold]  {task.description[:80]}", style="blue"))
            if not options.quiet:
                console.print(f"  [dim]Phase {ph.id} — {ph.name}  >  {sp.id} {sp.name}[/dim]")

            # Build accumulated context from completed tasks in the same phase (6.2.2)
            phase_ctx = _build_phase_context(plan, task)
            if phase_ctx:
                full_task = (
                    f"{phase_ctx}"
                    f"## Task to implement now\n\n"
                    f"{task.id} — {task.description}"
                )
            else:
                full_task = f"{task.id} — {task.description}"

            task.mark_running()
            write_plan(plan, plan_path)

            try:
                record, diff, _ = await run_cycle(full_task, config)
            except Exception as exc:  # noqa: BLE001
                console.print(
                    f"  [red]ERROR[/red] Unexpected error while executing task {task.id}: {exc}"
                )
                task.mark_escalated()
                write_plan(plan, plan_path)
                result.tasks_escalated += 1
                result.results.append(TaskResult(
                    task_id=task.id, description=task.description,
                    status="escalated", error=str(exc),
                ))
                if not options.yes:
                    if not click.confirm("  Continue with next task?", default=False):
                        raise _StopExecution() from exc
                _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)
                continue

            # ---- escalation ---------------------------------------------------------

            if record.status == CycleStatus.ESCALATED:
                console.print(
                    f"\n  [red][!] Task {task.id} escalated — requires manual intervention.[/red]"
                )
                task.mark_escalated()
                write_plan(plan, plan_path)
                log_store.save(record, diff, config.log_dir)
                result.tasks_escalated += 1
                result.results.append(TaskResult(
                    task_id=task.id, description=task.description, status="escalated",
                ))
                if not options.yes:
                    if not click.confirm("  Continue with next task?", default=False):
                        console.print("[yellow]Execution paused — manual intervention required.[/yellow]")
                        raise _StopExecution()
                _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)
                continue

            # ---- approved — commit --------------------------------------------------

            commit_msg = (
                git_helpers.make_commit_message(task.description)
                if config.git_conventional_commits
                else f"feat: {task.id} {task.description[:60]}"
            )

            commit_hash: str | None = None
            if options.yes or click.confirm(
                f"\n  Confirm commit? [{commit_msg}]", default=True
            ):
                commit_hash = _commit_task(config.project_dir, commit_msg)
                if commit_hash:
                    console.print(f"  [green][OK] Committed:[/green] {commit_msg} ({commit_hash})")
                else:
                    console.print("  [yellow][!] Commit failed — continuing.[/yellow]")
            else:
                console.print("  [yellow]Commit skipped.[/yellow]")

            task.mark_done(commit_hash=commit_hash)
            write_plan(plan, plan_path)
            log_store.save(record, diff, config.log_dir)

            result.tasks_done += 1
            result.results.append(TaskResult(
                task_id=task.id, description=task.description,
                status="done", commit_hash=commit_hash,
            ))

            _maybe_pause_boundaries(task, ph, sp, last_in_subphase, last_in_phase, plan, result, options)

    except _StopExecution:
        pass

    _show_run_summary(result)
    return result
