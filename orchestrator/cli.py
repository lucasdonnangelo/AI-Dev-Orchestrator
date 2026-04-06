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
from orchestrator.models import CycleStatus, TaskPlan
from orchestrator import chat as chat_module
from orchestrator import git as git_helpers
from orchestrator import logger as log_store
from orchestrator import orchestrator as orch
from orchestrator import session
from orchestrator import templates as tmpl
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


def _maybe_create_branch(task: str, config) -> str | None:
    """Create and checkout a new branch if git_auto_branch is enabled.

    Returns the branch name on success, None otherwise.
    """
    if not config.git_auto_branch:
        return None
    branch = git_helpers.make_branch_name(task)
    ok = git_helpers.create_branch(config.project_dir, branch)
    if ok:
        console.print(f"[dim]  Branch: {branch}[/dim]")
        return branch
    console.print(f"[yellow][!] Could not create branch '{branch}' — committing on current branch.[/yellow]")
    return None


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


async def _run(
    task: str,
    config: Config,
    yes: bool,
    quiet: bool = False,
    verbose: bool = False,
    plan: TaskPlan | None = None,
) -> None:
    """Execute one full orchestration cycle.

    Args:
        task: Natural-language task description.
        config: Resolved orchestrator configuration.
        yes: Skip all confirmation prompts.
        quiet: Suppress non-essential panels (plan, diff, review, decision).
               Errors and commit status are always shown.
        verbose: Show extra detail (issues list even on approval, all suggestions).
        plan: Optional pre-built plan to skip the planning/critic phases.
    """
    if not quiet:
        console.print(Panel(f"[bold]{task}[/bold]", title="Task", border_style="blue"))

    _maybe_create_branch(task, config)

    record, diff, decision = await orch.run_cycle(task, config, plan=plan)

    if not quiet:
        _display_plan(record)

    if record.status == CycleStatus.ESCALATED and decision is None:
        console.print(
            f"\n[red][!] Max retries ({config.max_retries}) reached without approval.[/red]"
        )
        _display_issues(record)
        log_store.save(record, diff, config.log_dir)

        if yes:
            console.print("[yellow]Manual intervention required.[/yellow]")
            raise SystemExit(1)

        action = click.prompt(
            "\nWhat next?",
            type=click.Choice(["abort", "retry", "edit"]),
            default="abort",
            show_choices=True,
        )
        if action == "abort":
            raise SystemExit(1)
        elif action == "retry":
            await _run(task, config, yes, quiet=quiet, verbose=verbose)
            return
        else:  # edit
            new_task = click.prompt("New task description", default=task)
            await _run(new_task, config, yes, quiet=quiet, verbose=verbose)
            return

    if not quiet:
        _display_review(record)
        if decision is not None:
            _display_decision(decision)
    elif verbose:
        # In verbose+quiet (unusual) still show the review score
        review = record.review
        if review:
            status = "[OK]" if review.approved else "[X]"
            console.print(f"  Review: {status} {review.score}/10 — {review.summary[:80]}")

    # Always show issues in verbose mode (even on approval)
    if verbose and record.review and record.review.issues:
        _display_issues(record)
    # Also show suggestions in verbose mode
    if verbose and record.review and record.review.suggestions:
        console.print("[dim]Suggestions:[/dim]")
        for s in record.review.suggestions:
            console.print(f"  [dim]- {s}[/dim]")

    if record.status == CycleStatus.ESCALATED:
        console.print("\n[red][!] Decisor rejected — implementation diverges from plan.[/red]")
        log_store.save(record, diff, config.log_dir)

        if yes:
            console.print("[yellow]Manual intervention required.[/yellow]")
            raise SystemExit(1)

        action = click.prompt(
            "\nWhat next?",
            type=click.Choice(["abort", "retry", "edit"]),
            default="abort",
            show_choices=True,
        )
        if action == "abort":
            raise SystemExit(1)
        elif action == "retry":
            await _run(task, config, yes, quiet=quiet, verbose=verbose)
            return
        else:  # edit
            new_task = click.prompt("New task description", default=task)
            await _run(new_task, config, yes, quiet=quiet, verbose=verbose)
            return

    # Show diff (suppressed in quiet mode)
    if not quiet and diff.strip():
        console.print(Rule("Diff", style="blue"))
        console.print(Syntax(diff, "diff", theme="monokai"))

    # Commit confirmation
    commit_msg = (
        git_helpers.make_commit_message(task)
        if config.git_conventional_commits
        else f"feat: {task[:72]}"
    )

    if yes or click.confirm("\nConfirm commit?", default=True):
        commit_hash = _commit(config.project_dir, commit_msg)
        if commit_hash:
            record.commit_hash = commit_hash
            console.print(f"[green][OK] Committed:[/green] {commit_msg} ({commit_hash})")
            if config.git_auto_branch:
                pr_desc = git_helpers.build_pr_description(task, record)
                if not quiet:
                    console.print(Panel(pr_desc, title="PR Description", border_style="dim"))
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
@click.option("--verbose", "-v", is_flag=True, help="Show extra detail (issues, suggestions).")
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential panels (errors/commit always shown).")
def run(task: str, project_dir: str, plan_file: str | None, yes: bool, verbose: bool, quiet: bool) -> None:
    """Run a full orchestration cycle for TASK."""

    config = Config.load(project_dir)
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]ERROR[/red] {err}")
        raise SystemExit(1)

    prebuilt_plan: TaskPlan | None = None
    if plan_file:
        try:
            prebuilt_plan = TaskPlan.from_json(
                __import__("pathlib").Path(plan_file).read_text(encoding="utf-8")
            )
        except Exception as exc:
            console.print(f"[red]ERROR[/red] Could not load plan file: {exc}")
            raise SystemExit(1)

    try:
        asyncio.run(_run(task, config, yes, quiet=quiet, verbose=verbose, plan=prebuilt_plan))
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
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential panels per task.")
@click.option("--verbose", "-v", is_flag=True, help="Show extra detail per task.")
def batch(tasks_file: str, project_dir: str, yes: bool, stop_on_failure: bool, quiet: bool, verbose: bool) -> None:
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
            asyncio.run(_run(task, config, yes, quiet=quiet, verbose=verbose))
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


@cli.command()
@click.option(
    "--log-dir",
    default="logs",
    show_default=True,
    help="Directory containing log files.",
)
def metrics(log_dir: str) -> None:
    """Show analytics aggregated from all past orchestration runs."""
    from datetime import datetime as _dt

    entries = log_store.list_runs(log_dir, limit=0)
    if not entries:
        console.print("[yellow]No runs found in logs/[/yellow]")
        return

    total = len(entries)
    approved = sum(1 for e in entries if e.get("status") == "approved")
    escalated = sum(1 for e in entries if e.get("status") == "escalated")

    scores = [
        e["review"]["score"]
        for e in entries
        if e.get("review") and e["review"].get("score") is not None
    ]
    avg_score = sum(scores) / len(scores) if scores else None

    attempts_list = [e.get("attempt", 1) for e in entries]
    avg_attempts = sum(attempts_list) / len(attempts_list)

    durations: list[float] = []
    for e in entries:
        started = e.get("started_at")
        finished = e.get("finished_at")
        if started and finished:
            try:
                s = _dt.fromisoformat(started)
                f = _dt.fromisoformat(finished)
                durations.append((f - s).total_seconds())
            except ValueError:
                pass
    avg_duration = sum(durations) / len(durations) if durations else None

    # First-attempt approval rate
    first_attempt_approved = sum(
        1 for e in entries if e.get("status") == "approved" and e.get("attempt", 1) == 1
    )

    # --- Summary table ---
    summary = Table(title="Orchestrator Metrics", show_lines=True, border_style="blue")
    summary.add_column("Metric", style="bold", min_width=28)
    summary.add_column("Value", justify="right", min_width=20)

    def pct(n: int) -> str:
        return f"{n * 100 // total}%" if total else "—"

    summary.add_row("Total runs", str(total))
    summary.add_row(
        "Approved",
        f"[green]{approved}[/green]  ({pct(approved)})",
    )
    summary.add_row(
        "Escalated",
        f"[red]{escalated}[/red]  ({pct(escalated)})",
    )
    summary.add_row(
        "1st-attempt approval",
        f"{first_attempt_approved}  ({pct(first_attempt_approved)})",
    )
    summary.add_row(
        "Avg review score",
        f"{avg_score:.1f} / 10" if avg_score is not None else "—",
    )
    summary.add_row("Avg attempts per cycle", f"{avg_attempts:.2f}")
    summary.add_row(
        "Avg cycle duration",
        f"{avg_duration:.0f}s" if avg_duration is not None else "—",
    )
    console.print(summary)

    # --- Status breakdown bar ---
    bar_width = 40
    approved_blocks = round(approved * bar_width / total) if total else 0
    escalated_blocks = bar_width - approved_blocks
    bar = (
        "[green]" + "#" * approved_blocks + "[/green]"
        + "[red]" + "-" * escalated_blocks + "[/red]"
    )
    console.print(f"\n  [dim]approved[/dim] {bar} [dim]escalated[/dim]")

    # --- Recent tasks (last 5) ---
    recent = entries[:5]
    if recent:
        console.print()
        recent_table = Table(title="Last 5 Runs", show_lines=False, border_style="dim")
        recent_table.add_column("Date", style="dim", width=19)
        recent_table.add_column("Status", width=10)
        recent_table.add_column("Score", width=6, justify="center")
        recent_table.add_column("Task")
        for e in recent:
            st = e.get("status", "?")
            color = "green" if st == "approved" else "red"
            started = (e.get("started_at") or "")[:19].replace("T", " ")
            score = "—"
            if e.get("review") and e["review"].get("score") is not None:
                score = str(e["review"]["score"])
            task_text = e.get("task", "")
            if len(task_text) > 55:
                task_text = task_text[:52] + "..."
            recent_table.add_row(started, f"[{color}]{st}[/{color}]", score, task_text)
        console.print(recent_table)


@cli.command("chat")
@click.option(
    "--agent", "-a", "role",
    default="planner",
    type=click.Choice(chat_module.ROLES),
    show_default=True,
    help="Agent to chat with.",
)
@click.option(
    "--project-dir", "-d",
    default=".",
    help="Target project directory (used to load .orchestrator.yaml and session context).",
)
def chat(role: str, project_dir: str) -> None:
    """Start an interactive chat session with an orchestrator agent.

    Sends messages directly to the chosen agent using its configured provider
    and system prompt.  Session context from SESSAO_ATUAL.md (if present) is
    prepended to the first message automatically.

    \b
    Examples:
      orchestrate chat                       # chat with planner (default)
      orchestrate chat --agent reviewer      # chat with reviewer
      orchestrate chat -a critic -d ./myapp  # critic for a specific project
    """
    config = Config.load(project_dir)
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]ERROR[/red] {err}")
        raise SystemExit(1)

    session_ctx = session.load(config.project_dir)

    provider_name = {
        "planner":  config.planner_provider,
        "critic":   config.critic_provider,
        "reviewer": config.reviewer_provider,
        "decisor":  config.decisor_provider,
    }[role]

    console.print(
        Panel(
            f"[bold]{role}[/bold] agent  [dim]({provider_name})[/dim]\n"
            "[dim]Type your message and press Enter. 'exit' or Ctrl+C to quit.[/dim]",
            title="Chat",
            border_style="blue",
        )
    )
    if session_ctx:
        console.print("[dim]  Session context loaded from SESSAO_ATUAL.md[/dim]")

    first_turn = True
    while True:
        try:
            message = click.prompt("You", prompt_suffix="\n> ")
        except (click.Abort, EOFError):
            console.print("\n[dim]Exiting chat.[/dim]")
            break

        message = message.strip()
        if message.lower() in ("exit", "quit", "q"):
            console.print("[dim]Exiting chat.[/dim]")
            break
        if not message:
            continue

        # Prepend session context to the first turn only
        full_message = message
        if first_turn and session_ctx:
            full_message = (
                f"## Project Context (SESSAO_ATUAL.md)\n\n{session_ctx}\n\n{message}"
            )
        first_turn = False

        try:
            response = asyncio.run(chat_module.send(role, full_message, config))
        except Exception as exc:
            console.print(f"[red]ERROR[/red] {exc}")
            continue

        console.print(Rule(style="dim"))
        console.print(f"[bold green]{role.capitalize()}[/bold green]")
        console.print(response)
        console.print(Rule(style="dim"))


@cli.command("init")
@click.option(
    "--template", "-t",
    default=None,
    metavar="NAME",
    help="Template name to apply (fastapi, python-cli, react).",
)
@click.option(
    "--list", "list_only",
    is_flag=True,
    help="List available templates and exit.",
)
@click.option(
    "--dir", "-d",
    "directory",
    default=".",
    show_default=True,
    help="Target directory for the project (created if it does not exist).",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    help="Overwrite existing files without asking.",
)
def init(template: str | None, list_only: bool, directory: str, force: bool) -> None:
    """Initialise a project from a template.

    Creates .orchestrator.yaml and tasks.txt (plus any skeleton files) in the
    target directory so you can start an orchestrated dev cycle immediately.

    \b
    Examples:
      orchestrate init --list
      orchestrate init --template fastapi --dir ./my-api
      orchestrate init -t python-cli -d .
    """
    if list_only:
        table = Table(title="Available Templates", show_lines=False, border_style="blue")
        table.add_column("Name", style="bold cyan", width=14)
        table.add_column("Description")
        for t in tmpl.list_templates():
            table.add_row(t.name, t.description)
        console.print(table)
        return

    if not template:
        console.print(
            "[red]ERROR[/red] --template is required. "
            "Run [bold]orchestrate init --list[/bold] to see available templates."
        )
        raise SystemExit(1)

    selected = tmpl.get_template(template)
    if selected is None:
        available = ", ".join(t.name for t in tmpl.list_templates())
        console.print(
            f"[red]ERROR[/red] Unknown template '{template}'. "
            f"Available: {available}"
        )
        raise SystemExit(1)

    target = Path(directory).resolve()

    try:
        written = tmpl.init_project(selected, target, force=force)
    except FileExistsError as exc:
        console.print(f"[red]ERROR[/red] {exc}")
        raise SystemExit(1)

    console.print(
        Panel(
            f"[bold]{selected.name}[/bold] — {selected.description}\n"
            f"[dim]Directory: {target}[/dim]",
            title="Template applied",
            border_style="green",
        )
    )
    for rel in written:
        console.print(f"  [green]+[/green] {rel}")

    console.print(
        f"\n[dim]Next step:[/dim] [bold]orchestrate batch tasks.txt -d {directory} -y[/bold]"
    )


if __name__ == "__main__":
    cli()
