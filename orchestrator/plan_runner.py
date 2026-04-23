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

import asyncio
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from orchestrator import git as git_helpers
from orchestrator import logger as log_store
from orchestrator.config import Config
from orchestrator.events import EventBus, EventType
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


def _get_commit_files(project_dir: str, commit_hash: str) -> list[str]:
    """Return the list of files touched by *commit_hash* (empty on any error)."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        return [f for f in result.stdout.splitlines() if f]
    except Exception:  # noqa: BLE001
        return []


def _build_phase_context(
    plan: ProjectPlan,
    current_task: PlanTask,
    project_dir: str | None = None,
) -> str:
    """Return a Markdown string summarising completed tasks in the current phase.

    Prepended to the task description so the Planner has full context of what
    was already implemented.  Also passed separately to the Critic so it can
    evaluate cross-task coherence (6.3).

    When *project_dir* is provided and a task has a commit hash, the list of
    files touched by that commit is included so the Critic can detect overlap
    or conflicts with the new plan.

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
                if project_dir and t.commit_hash:
                    files = _get_commit_files(project_dir, t.commit_hash)
                    if files:
                        for f in files:
                            lines.append(f"  - {f}")
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
    done = [r for r in results if r.status in ("done", "already_done") and r.task_id.startswith(prefix)]
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
    done = [r for r in phase_results if r.status in ("done", "already_done")]
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


def _make_pause_context(
    result: RunPlanResult,
    id_prefix: str,
) -> dict:
    """Build the ``context`` dict included in PLAN_PAUSED events."""
    relevant = [r for r in result.results if r.task_id.startswith(id_prefix)]
    return {
        "done": sum(1 for r in relevant if r.status in ("done", "already_done")),
        "escalated": sum(1 for r in relevant if r.status == "escalated"),
        "skipped": sum(1 for r in relevant if r.status == "skipped"),
        "commits": [r.commit_hash for r in relevant if r.commit_hash],
    }


async def _maybe_pause_boundaries(
    task: PlanTask,
    ph: Phase,
    sp: SubPhase,
    last_in_subphase: dict[str, str | None],
    last_in_phase: dict[str, str | None],
    plan: ProjectPlan,
    result: RunPlanResult,
    options: RunPlanOptions,
    *,
    event_bus: EventBus | None = None,
    pause_event: asyncio.Event | None = None,
    phase_start: dict[str, float] | None = None,
    subphase_start: dict[str, float] | None = None,
) -> None:
    """Pause for human confirmation at subphase / phase boundaries.

    In CLI mode (pause_event is None) uses click.confirm.
    In API mode (pause_event provided) emits PLAN_PAUSED and awaits resume.
    Raises :exc:`_StopExecution` when the user declines to continue.

    Skips all pausing when ``auto_continue`` is set.
    ``yes`` only suppresses CLI prompts — it does not bypass API-mode pauses.
    """
    if options.auto_continue:
        return
    # In CLI yes-mode, skip boundary pauses (same as before).
    # In API mode (pause_event provided), always evaluate boundaries so the
    # pause_event mechanism works regardless of the yes flag.
    if options.yes and pause_event is None:
        return

    is_last_in_phase = last_in_phase.get(ph.id) == task.id
    is_last_in_subphase = last_in_subphase.get(sp.id) == task.id

    now = time.monotonic()

    # Phase boundary takes priority over subphase boundary.
    if is_last_in_phase and options.pause_after_phase:
        ph_duration = now - (phase_start or {}).get(ph.id, now)
        all_ids = {t.id for t in ph.all_tasks}
        ph_results = [r for r in result.results if r.task_id in all_ids]
        if event_bus:
            await event_bus.emit(EventType.PHASE_COMPLETE, {
                "phase_id": ph.id,
                "done": sum(1 for r in ph_results if r.status in ("done", "already_done")),
                "escalated": sum(1 for r in ph_results if r.status == "escalated"),
                "skipped": sum(1 for r in ph_results if r.status == "skipped"),
                "duration_s": round(ph_duration, 1),
            })
        _show_phase_summary(ph, result.results)
        next_phase = _next_phase(plan, ph.id)
        if next_phase:
            if pause_event is not None:
                ctx = _make_pause_context(result, f"{ph.id}.")
                ctx["duration_s"] = round(ph_duration, 1)
                pause_event.clear()
                if event_bus:
                    await event_bus.emit(EventType.PLAN_PAUSED, {"reason": "phase", "context": ctx})
                try:
                    await asyncio.wait_for(pause_event.wait(), timeout=1800.0)
                except asyncio.TimeoutError:
                    raise _StopExecution()
                if event_bus:
                    await event_bus.emit(EventType.PLAN_RESUMED, {})
            else:
                if not click.confirm(
                    f"\nContinue to Phase {next_phase.id} — {next_phase.name}?",
                    default=True,
                ):
                    console.print("[yellow]Execution stopped by user.[/yellow]")
                    raise _StopExecution()
        return

    if is_last_in_subphase and options.pause_after_subtask:
        sp_duration = now - (subphase_start or {}).get(sp.id, now)
        sp_prefix = f"{sp.id}."
        sp_results = [r for r in result.results if r.task_id.startswith(sp_prefix)]
        if event_bus:
            await event_bus.emit(EventType.SUBPHASE_COMPLETE, {
                "subphase_id": sp.id,
                "done": sum(1 for r in sp_results if r.status in ("done", "already_done")),
                "escalated": sum(1 for r in sp_results if r.status == "escalated"),
                "skipped": sum(1 for r in sp_results if r.status == "skipped"),
                "duration_s": round(sp_duration, 1),
            })
        _show_subphase_summary(sp, result.results)
        next_sp = _next_subphase(plan, sp.id)
        if next_sp:
            if pause_event is not None:
                ctx = _make_pause_context(result, sp_prefix)
                ctx["duration_s"] = round(sp_duration, 1)
                pause_event.clear()
                if event_bus:
                    await event_bus.emit(EventType.PLAN_PAUSED, {"reason": "subphase", "context": ctx})
                try:
                    await asyncio.wait_for(pause_event.wait(), timeout=1800.0)
                except asyncio.TimeoutError:
                    raise _StopExecution()
                if event_bus:
                    await event_bus.emit(EventType.PLAN_RESUMED, {})
            else:
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
    *,
    event_bus: EventBus | None = None,
    pause_event: asyncio.Event | None = None,
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

    # Timing accumulators.
    _plan_start = time.monotonic()
    _phase_start: dict[str, float] = {}
    _subphase_start: dict[str, float] = {}

    # Emit PLAN_LOADED so the API/WS layer knows the plan structure upfront.
    if event_bus:
        phases_info = [
            {"id": ph.id, "name": ph.name, "task_count": len(ph.all_tasks)}
            for ph in plan.phases
        ]
        total_tasks = sum(len(ph.all_tasks) for ph in plan.phases)
        done_tasks = sum(1 for ph in plan.phases for t in ph.all_tasks if t.is_done)
        await event_bus.emit(EventType.PLAN_LOADED, {
            "name": plan.name,
            "phases": phases_info,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
        })

    # --- dry run ---
    if options.dry_run:
        console.print(Panel(
            f"[bold]{plan.name}[/bold]  [dim](dry run — nothing will be executed)[/dim]",
            title="Plan Runner",
            border_style="dim",
        ))
        _ICON: dict[str, str] = {
            "pending":   r"\[ ]",
            "running":   r"\[>]",
            "done":      r"\[x]",
            "escalated": r"\[!]",
            "skipped":   r"\[-]",
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

    _boundary_kwargs: dict = {
        "event_bus": event_bus,
        "pause_event": pause_event,
        "phase_start": _phase_start,
        "subphase_start": _subphase_start,
    }

    try:
        for ph, sp, task in entries:

            # Track start times for the first task in each phase/subphase.
            now = time.monotonic()
            _phase_start.setdefault(ph.id, now)
            _subphase_start.setdefault(sp.id, now)

            # ---- API per-task pause check -------------------------------------------
            # In API mode, check pause_event BEFORE starting each task so that
            # POST /api/plan/pause/{id} takes effect "after the current task" rather
            # than only at natural subphase/phase boundaries.
            # Skipped in CLI mode (pause_event is None) and auto_continue mode.
            if pause_event is not None and not options.auto_continue:
                if not pause_event.is_set():
                    ctx: dict = _make_pause_context(result, "")
                    if event_bus:
                        await event_bus.emit(EventType.PLAN_PAUSED, {
                            "reason": "requested",
                            "context": ctx,
                        })
                    try:
                        await asyncio.wait_for(pause_event.wait(), timeout=1800.0)
                    except asyncio.TimeoutError:
                        raise _StopExecution()
                    if event_bus:
                        await event_bus.emit(EventType.PLAN_RESUMED, {})

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
                if event_bus:
                    await event_bus.emit(EventType.TASK_SKIPPED, {"task_id": task.id})
                await _maybe_pause_boundaries(
                    task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                    **_boundary_kwargs,
                )
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
                if event_bus:
                    await event_bus.emit(EventType.TASK_SKIPPED, {"task_id": task.id})
                await _maybe_pause_boundaries(
                    task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                    **_boundary_kwargs,
                )
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
                    if event_bus:
                        await event_bus.emit(EventType.TASK_SKIPPED, {"task_id": task.id})
                    await _maybe_pause_boundaries(
                        task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                        **_boundary_kwargs,
                    )
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
                    if event_bus:
                        await event_bus.emit(EventType.TASK_SKIPPED, {"task_id": task.id})
                    await _maybe_pause_boundaries(
                        task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                        **_boundary_kwargs,
                    )
                    continue
                # "retry" — reset to pending and fall through to execution
                task.reset()
                write_plan(plan, plan_path)

            # ---- execute task -------------------------------------------------------

            console.print(Rule(f"[bold]{task.id}[/bold]  {task.description[:80]}", style="blue"))
            if not options.quiet:
                console.print(f"  [dim]Phase {ph.id} — {ph.name}  >  {sp.id} {sp.name}[/dim]")

            _task_run_id = str(uuid.uuid4())
            if event_bus:
                await event_bus.emit(EventType.TASK_STARTED, {
                    "task_id": task.id,
                    "description": task.description,
                    "phase_id": ph.id,
                    "subphase_id": sp.id,
                    "attempt": 1,
                    "run_id": _task_run_id,
                })
            _task_start = time.monotonic()

            # Build accumulated context from completed tasks in the same phase (6.2/6.3)
            phase_ctx = _build_phase_context(plan, task, project_dir=config.project_dir)
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
                record, diff, _ = await run_cycle(
                    full_task, config, phase_context=phase_ctx or None
                )
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
                if event_bus:
                    await event_bus.emit(EventType.TASK_ESCALATED, {
                        "task_id": task.id, "reason": str(exc),
                    })
                if not options.yes:
                    if not click.confirm("  Continue with next task?", default=False):
                        raise _StopExecution() from exc
                await _maybe_pause_boundaries(
                    task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                    **_boundary_kwargs,
                )
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
                if event_bus:
                    await event_bus.emit(EventType.TASK_ESCALATED, {
                        "task_id": task.id, "reason": "max retries exceeded",
                    })
                if not options.yes:
                    if not click.confirm("  Continue with next task?", default=False):
                        console.print("[yellow]Execution paused — manual intervention required.[/yellow]")
                        raise _StopExecution()
                await _maybe_pause_boundaries(
                    task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                    **_boundary_kwargs,
                )
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

            _task_duration = round(time.monotonic() - _task_start, 1)
            result.tasks_done += 1
            result.results.append(TaskResult(
                task_id=task.id, description=task.description,
                status="done", commit_hash=commit_hash,
            ))
            if event_bus:
                score = record.review.score if record.review else None
                await event_bus.emit(EventType.TASK_DONE, {
                    "task_id": task.id,
                    "commit_hash": commit_hash,
                    "score": score,
                    "duration_s": _task_duration,
                })

            await _maybe_pause_boundaries(
                task, ph, sp, last_in_subphase, last_in_phase, plan, result, options,
                **_boundary_kwargs,
            )

    except _StopExecution:
        pass

    if event_bus:
        await event_bus.emit(EventType.PLAN_COMPLETE, {
            "total": result.total_processed,
            "done": result.tasks_done,
            "escalated": result.tasks_escalated,
            "skipped": result.tasks_skipped,
            "duration_s": round(time.monotonic() - _plan_start, 1),
        })

    _show_run_summary(result)
    return result
