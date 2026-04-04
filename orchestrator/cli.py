"""CLI entry point for the AI Dev Orchestrator."""

from __future__ import annotations

import asyncio
import subprocess

import anthropic
import click
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax

from orchestrator import __version__
from orchestrator.config import Config
from orchestrator.models import CycleStatus
from orchestrator import orchestrator as orch

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


def _commit(project_dir: str, message: str) -> bool:
    try:
        subprocess.run(["git", "add", "."], cwd=project_dir, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=project_dir, check=True)
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]ERROR[/red] git failed: {e}")
        return False


async def _run(task: str, config: Config, yes: bool) -> None:
    console.print(Panel(f"[bold]{task}[/bold]", title="Task", border_style="blue"))

    console.print("[dim]Planning...[/dim]")
    record = await orch.run_cycle(task, config)

    _display_plan(record)

    if record.status == CycleStatus.ESCALATED:
        console.print(
            f"\n[red][!] Max retries ({config.max_retries}) reached without approval.[/red]"
        )
        _display_issues(record)
        console.print("[yellow]Manual intervention required.[/yellow]")
        raise SystemExit(1)

    # APPROVED
    _display_review(record)

    # Show diff
    diff = record.review  # diff is captured inside run_cycle; re-generate for display
    # Re-run diff from project dir for display purposes
    diff_result = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=config.project_dir,
        capture_output=True,
        text=True,
    )
    if diff_result.stdout.strip():
        console.print(Rule("Diff", style="blue"))
        console.print(Syntax(diff_result.stdout, "diff", theme="monokai"))

    # Commit confirmation
    if yes or click.confirm("\nConfirm commit?", default=True):
        commit_msg = f"feat: {task[:72]}"
        if _commit(config.project_dir, commit_msg):
            console.print(f"[green][OK] Committed:[/green] {commit_msg}")
        else:
            raise SystemExit(1)
    else:
        console.print("[yellow]Commit skipped.[/yellow]")


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
def status() -> None:
    """Show the status of the last orchestration run."""
    # TODO: Phase 2.2
    console.print("[yellow]! Not yet implemented (Phase 2.2)[/yellow]")


@cli.command()
def history() -> None:
    """List past orchestration runs."""
    # TODO: Phase 2.2
    console.print("[yellow]! Not yet implemented (Phase 2.2)[/yellow]")


if __name__ == "__main__":
    cli()
