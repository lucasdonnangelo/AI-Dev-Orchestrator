"""CLI entry point for the AI Dev Orchestrator."""

from __future__ import annotations

import click
from rich.console import Console
from rich.panel import Panel

from orchestrator import __version__
from orchestrator.config import Config

console = Console()


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
@click.option("--yes", "-y", is_flag=True, help="Skip plan confirmation prompt.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
def run(task: str, project_dir: str, plan_file: str | None, yes: bool, verbose: bool) -> None:
    """Run a full orchestration cycle for TASK."""

    config = Config.load(project_dir)
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]✗[/red] {err}")
        raise SystemExit(1)

    console.print(
        Panel(
            f"[bold]{task}[/bold]",
            title="🎯 Task",
            border_style="blue",
        )
    )

    # TODO: Wire up orchestrator.run_cycle() in Phase 1.5
    console.print("[yellow]⚠ Orchestrator not yet implemented (Phase 1.5)[/yellow]")


@cli.command()
def status() -> None:
    """Show the status of the last orchestration run."""
    # TODO: Phase 2.2
    console.print("[yellow]⚠ Not yet implemented (Phase 2.2)[/yellow]")


@cli.command()
def history() -> None:
    """List past orchestration runs."""
    # TODO: Phase 2.2
    console.print("[yellow]⚠ Not yet implemented (Phase 2.2)[/yellow]")


if __name__ == "__main__":
    cli()
