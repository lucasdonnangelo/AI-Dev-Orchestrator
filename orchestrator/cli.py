"""CLI entry point for the AI Dev Orchestrator."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import anthropic
import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table

from orchestrator import __version__
from orchestrator.config import Config
from orchestrator.models import CycleStatus
from orchestrator import logger as log_store
from orchestrator import orchestrator as orch
from orchestrator.models import DecisionResult

console = Console(highlight=False)


def _display_plan(record) -> None:
    plan = record.plan
    lines = []
    if plan.files_to_create:
        lines.append("[bold]Files to create:[/bold] " + ", ".join(plan.files_to_create))
    if plan.files_to_modify:
        lines.append("[bold]Files to modify:[/bold] " + ", ".join(plan.files_to_modify))
    lines.append("")
    lines.append("[bold]Steps:[/bold]")
    for i, step in enumerate(plan.steps, 1):
        lines.append(f"  {i}. {step}")
    lines.append("")
    lines.append("[bold]Acceptance criteria:[/bold]")
    for criterion in plan.acceptance_criteria:
        lines.append(f"  - {criterion}")
    lines.append(f"\n[dim]Complexity: {plan.estimated_complexity.value}[/dim]")
    console.print(Panel("\n".join(lines), title="Plan", border_style="blue"))


def _display_review(record) -> None:
    review = record.review
    color = "green" if review.approved else "red"
    status = "[OK]" if review.approved else "[X]"
    console.print(
        Panel(
            f"[{color}]{status} Score: {review.score}/10[/{color}]\n\n{review.summary}",
            title=f"Review - attempt {record.attempt}",
            border_style=color,
        )
    )


def _display_decision(decision: DecisionResult) -> None:
    color = "green" if decision.approved else "red"
    status = "[OK]" if decision.approved else "[X]"
    body = f"[{color}]{status}[/{color}] {decision.reasoning}"
    if decision.inconsistencies:
        body += "\n\n[bold]Inconsistencies:[/bold]"
        for item in decision.inconsistencies:
            body += f"\n  - {item}"
    console.print(Panel(body, title="Decisor", border_style=color))


def _display_issues(record) -> None:
    if not record.review or not record.review.issues:
        return
    console.print(Rule("Issues requiring manual intervention", style="red"))
    for issue in record.review.issues:
        severity = issue.severity.value.upper()
        console.print(f"[red][{severity}][/red] {issue.description}")
        if issue.file:
            console.print(f"         File: {issue.file}" + (f":{issue.line}" if issue.line else ""))
        if issue.suggestion:
            console.print(f"         Suggestion: {issue.suggestion}")


def _commit(project_dir: str, message: str) -> str | None:
    """Run git add + commit. Returns the new commit hash on success, None on failure."""
    try:
        subprocess.run(["git", "add", "."], cwd=project_dir, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=project_dir, check=True)
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError as e:
        console.print(f"[red]ERROR[/red] git failed: {e}")
        return None


async def _run(task: str, config: Config, yes: bool) -> None:
    console.print(Panel(f"[bold]{task}[/bold]", title="Task", border_style="blue"))

    console.print("[dim]Planning...[/dim]")
    record, diff, decision = await orch.run_cycle(task, config)

    _display_plan(record)

    if record.status == CycleStatus.ESCALATED and decision is None:
        # Escalated before reaching Decisor (max retries exhausted by Reviewer)
        console.print(
            f"\n[red][!] Max retries ({config.max_retries}) reached without approval.[/red]"
        )
        _display_issues(record)
        console.print("[yellow]Manual intervention required.[/yellow]")
        log_store.save(record, diff, config.log_dir)
        raise SystemExit(1)

    # Reviewer approved — show review
    _display_review(record)

    # Show Decisor result
    if decision is not None:
        _display_decision(decision)

    if record.status == CycleStatus.ESCALATED:
        # Decisor rejected
        console.print("\n[red][!] Decisor rejected — implementation diverges from plan.[/red]")
        console.print("[yellow]Manual intervention required.[/yellow]")
        log_store.save(record, diff, config.log_dir)
        raise SystemExit(1)

    # Show diff
    if diff.strip():
        console.print(Rule("Diff", style="blue"))
        console.print(Syntax(diff, "diff", theme="monokai"))

    # Commit confirmation
    if yes or click.confirm("\nConfirm commit?", default=True):
        commit_msg = f"feat: {task[:72]}"
        commit_hash = _commit(config.project_dir, commit_msg)
        if commit_hash:
            record.commit_hash = commit_hash
            console.print(f"[green][OK] Committed:[/green] {commit_msg} ({commit_hash})")
        else:
            log_store.save(record, diff, config.log_dir)
            raise SystemExit(1)
    else:
        console.print("[yellow]Commit skipped.[/yellow]")

    log_store.save(record, diff, config.log_dir)


def _parse_tasks_file(path: str) -> list[str]:
    """Parse a tasks file into a list of task strings.

    Supports:
    - Plain text: one task per line; lines starting with ``#`` are comments.
    - JSON: must be an array of strings (or objects with a ``"task"`` key).
    """
    content = Path(path).read_text(encoding="utf-8")
    if path.endswith(".json"):
        data = json.loads(content)
        if not isinstance(data, list):
            raise click.ClickException("JSON tasks file must contain an array.")
        tasks: list[str] = []
        for item in data:
            if isinstance(item, str):
                tasks.append(item)
            elif isinstance(item, dict):
                tasks.append(str(item.get("task", item)))
            else:
                tasks.append(str(item))
        return tasks
    # Plain text
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


@click.group()
@click.version_option(version=__version__, prog_name="orchestrate")
def cli() -> None:
    """AI Dev Orchestrator — automate the dev cycle with AI agents."""


@cli.command()
@click.argument("task")
@click.option(
    "--project-dir", "-d",
    default=".",
    help="Path to the target project directory.",
)
@click.option(
    "--plan",
    "plan_file",
    default=None,
    type=click.Path(exists=True),
    help="Use a pre-existing plan JSON file instead of generating one.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip commit confirmation prompt.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
def run(task: str, project_dir: str, plan_file: str | None, yes: bool, verbose: bool) -> None:
    """Run a full orchestration cycle for TASK."""

    config = Config.load(project_dir)
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]ERROR[/red] {err}")
        raise SystemExit(1)

    try:
        asyncio.run(_run(task, config, yes))
    except anthropic.APIError as e:
        console.print(f"[red]ERROR[/red] Anthropic API error: {e}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        raise SystemExit(130)


@cli.command()
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    help="Directory containing log files.",
)
def status(log_dir: str) -> None:
    """Show the details of the last orchestration run."""
    entry = log_store.load_last(log_dir)
    if entry is None:
        console.print("[yellow]No runs found in logs/[/yellow]")
        return

    status_val = entry.get("status", "?")
    color = "green" if status_val == "approved" else "red"
    task = entry.get("task", "")
    started = entry.get("started_at", "")[:19].replace("T", " ")
    finished = (entry.get("finished_at") or "")[:19].replace("T", " ")
    commit = entry.get("commit_hash") or "—"

    header = (
        f"[{color}]{status_val.upper()}[/{color}]  "
        f"[bold]{task}[/bold]\n"
        f"[dim]Started: {started}  Finished: {finished}  Commit: {commit}[/dim]"
    )
    console.print(Panel(header, title="Last Run", border_style=color))

    # Plan summary
    plan = entry.get("plan")
    if plan:
        lines = []
        if plan.get("files_to_create"):
            lines.append("Create: " + ", ".join(plan["files_to_create"]))
        if plan.get("files_to_modify"):
            lines.append("Modify: " + ", ".join(plan["files_to_modify"]))
        lines.append(f"Complexity: {plan.get('estimated_complexity', '?')}")
        console.print(Panel("\n".join(lines), title="Plan", border_style="blue"))

    # Review
    review = entry.get("review")
    if review:
        approved = review.get("approved", False)
        score = review.get("score", "?")
        summary = review.get("summary", "")
        r_color = "green" if approved else "red"
        r_status = "[OK]" if approved else "[X]"
        console.print(
            Panel(
                f"[{r_color}]{r_status} Score: {score}/10[/{r_color}]\n{summary}",
                title="Review",
                border_style=r_color,
            )
        )

    # Decision
    decision = entry.get("decision")
    if decision:
        approved = decision.get("approved", False)
        d_color = "green" if approved else "red"
        d_status = "[OK]" if approved else "[X]"
        body = f"[{d_color}]{d_status}[/{d_color}] {decision.get('reasoning', '')}"
        if decision.get("inconsistencies"):
            body += "\nInconsistencies: " + "; ".join(decision["inconsistencies"])
        console.print(Panel(body, title="Decisor", border_style=d_color))

    # Diff
    diff = entry.get("diff", "")
    if diff.strip():
        console.print(Rule("Diff", style="blue"))
        console.print(Syntax(diff, "diff", theme="monokai"))


@cli.command()
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    help="Directory containing log files.",
)
@click.option(
    "--limit", "-n",
    default=20,
    show_default=True,
    help="Maximum number of runs to show.",
)
def history(log_dir: str, limit: int) -> None:
    """List past orchestration runs (newest first)."""
    entries = log_store.list_runs(log_dir, limit=limit)
    if not entries:
        console.print("[yellow]No runs found in logs/[/yellow]")
        return

    table = Table(title=f"Run History (last {len(entries)})", show_lines=False)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Date", style="dim", width=19)
    table.add_column("Status", width=10)
    table.add_column("Score", width=6, justify="center")
    table.add_column("Att.", width=4, justify="center")
    table.add_column("Commit", width=8)
    table.add_column("Task")

    for i, entry in enumerate(entries, 1):
        status_val = entry.get("status", "?")
        color = "green" if status_val == "approved" else "red"
        started = (entry.get("started_at") or "")[:19].replace("T", " ")
        score = "—"
        review = entry.get("review")
        if review and review.get("score") is not None:
            score = str(review["score"])
        attempt = str(entry.get("attempt", 1))
        commit = entry.get("commit_hash") or "—"
        task = entry.get("task", "")
        if len(task) > 60:
            task = task[:57] + "..."

        table.add_row(
            str(i),
            started,
            f"[{color}]{status_val}[/{color}]",
            score,
            attempt,
            commit,
            task,
        )

    console.print(table)


@cli.command()
@click.argument("tasks_file", type=click.Path(exists=True))
@click.option(
    "--project-dir", "-d",
    default=".",
    help="Path to the target project directory.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip all confirmation prompts.")
@click.option(
    "--stop-on-failure",
    is_flag=True,
    default=False,
    help="Abort batch on first escalated task without asking.",
)
def batch(tasks_file: str, project_dir: str, yes: bool, stop_on_failure: bool) -> None:
    """Run multiple tasks sequentially from TASKS_FILE.

    TASKS_FILE can be a plain-text file (one task per line) or a JSON array.
    Lines starting with # are treated as comments in text files.

    Each task only starts after the previous one is approved.
    SESSAO_ATUAL.md accumulates context between tasks automatically.
    """
    config = Config.load(project_dir)
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]ERROR[/red] {err}")
        raise SystemExit(1)

    tasks = _parse_tasks_file(tasks_file)
    if not tasks:
        console.print("[yellow]No tasks found in file.[/yellow]")
        return

    console.print(
        Panel(
            f"[bold]{tasks_file}[/bold]\n[dim]{len(tasks)} task(s) queued[/dim]",
            title="Batch",
            border_style="blue",
        )
    )

    results: list[dict] = []

    for i, task in enumerate(tasks, 1):
        console.print(Rule(f"Task {i}/{len(tasks)}", style="blue"))
        task_status = "approved"
        try:
            asyncio.run(_run(task, config, yes))
        except SystemExit as exc:
            if exc.code == 130:  # KeyboardInterrupt escalated as SystemExit
                console.print("\n[yellow]Batch interrupted.[/yellow]")
                results.append({"task": task, "status": "interrupted"})
                break
            # Task failed (escalated or max retries)
            task_status = "escalated"
            if stop_on_failure:
                results.append({"task": task, "status": task_status})
                console.print("[red][!] Stopping batch on first failure.[/red]")
                break
            if not yes and not click.confirm(
                f"\nTask {i} was escalated. Continue with remaining tasks?",
                default=True,
            ):
                results.append({"task": task, "status": task_status})
                break

        results.append({"task": task, "status": task_status})

    # --- Summary table ---
    if not results:
        return

    console.print(Rule("Batch Summary", style="bold blue"))

    table = Table(show_lines=False)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Status", width=12)
    table.add_column("Task")
    for idx, r in enumerate(results, 1):
        st = r["status"]
        if st == "approved":
            color, icon = "green", "[OK]"
        elif st == "interrupted":
            color, icon = "yellow", "[--]"
        else:
            color, icon = "red", "[X]"
        task_display = r["task"] if len(r["task"]) <= 70 else r["task"][:67] + "..."
        table.add_row(str(idx), f"[{color}]{icon}[/{color}]", task_display)
    console.print(table)

    approved_count = sum(1 for r in results if r["status"] == "approved")
    total = len(results)
    result_color = "green" if approved_count == total else "yellow"
    console.print(
        f"\n[{result_color}][bold]Result: {approved_count}/{total} tasks approved.[/bold][/{result_color}]"
    )


if __name__ == "__main__":
    cli()
