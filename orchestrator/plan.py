"""Data models and parser for the hierarchical project plan (PLANO.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlanTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# PlanTask
# ---------------------------------------------------------------------------


@dataclass
class PlanTask:
    """A single executable task inside a subfase of the hierarchical plan."""

    id: str                          # e.g. "1.1.1"
    description: str
    status: PlanTaskStatus = PlanTaskStatus.PENDING
    commit_hash: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    # ---- computed helpers ----

    @property
    def is_pending(self) -> bool:
        return self.status == PlanTaskStatus.PENDING

    @property
    def is_done(self) -> bool:
        return self.status == PlanTaskStatus.DONE

    @property
    def is_terminal(self) -> bool:
        """True if the task will not be retried automatically."""
        return self.status in (
            PlanTaskStatus.DONE,
            PlanTaskStatus.ESCALATED,
            PlanTaskStatus.SKIPPED,
        )

    # ---- lifecycle ----

    def mark_running(self) -> None:
        self.status = PlanTaskStatus.RUNNING
        self.started_at = datetime.now().isoformat()

    def mark_done(self, commit_hash: str | None = None) -> None:
        self.status = PlanTaskStatus.DONE
        self.finished_at = datetime.now().isoformat()
        if commit_hash:
            self.commit_hash = commit_hash

    def mark_escalated(self) -> None:
        self.status = PlanTaskStatus.ESCALATED
        self.finished_at = datetime.now().isoformat()

    def mark_skipped(self) -> None:
        self.status = PlanTaskStatus.SKIPPED
        self.finished_at = datetime.now().isoformat()

    def reset(self) -> None:
        """Return task to pending, clearing all runtime state."""
        self.status = PlanTaskStatus.PENDING
        self.commit_hash = None
        self.started_at = None
        self.finished_at = None

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "commit_hash": self.commit_hash,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanTask:
        return cls(
            id=data["id"],
            description=data["description"],
            status=PlanTaskStatus(data.get("status", "pending")),
            commit_hash=data.get("commit_hash"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )


# ---------------------------------------------------------------------------
# SubPhase
# ---------------------------------------------------------------------------


@dataclass
class SubPhase:
    """A named group of tasks within a Phase (### heading in PLANO.md)."""

    id: str             # e.g. "1.1"
    name: str
    tasks: list[PlanTask] = field(default_factory=list)

    # ---- computed helpers ----

    @property
    def pending_tasks(self) -> list[PlanTask]:
        return [t for t in self.tasks if t.status == PlanTaskStatus.PENDING]

    @property
    def done_tasks(self) -> list[PlanTask]:
        return [t for t in self.tasks if t.status == PlanTaskStatus.DONE]

    @property
    def is_complete(self) -> bool:
        """All tasks are in a terminal state."""
        return all(t.is_terminal for t in self.tasks)

    @property
    def has_escalated(self) -> bool:
        return any(t.status == PlanTaskStatus.ESCALATED for t in self.tasks)

    def next_pending(self) -> PlanTask | None:
        """Return the first pending task, or None if all are terminal."""
        return next((t for t in self.tasks if t.status == PlanTaskStatus.PENDING), None)

    def get_task(self, task_id: str) -> PlanTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubPhase:
        return cls(
            id=data["id"],
            name=data["name"],
            tasks=[PlanTask.from_dict(t) for t in data.get("tasks", [])],
        )


# ---------------------------------------------------------------------------
# Phase
# ---------------------------------------------------------------------------


@dataclass
class Phase:
    """A top-level phase of the project plan (## heading in PLANO.md)."""

    id: str             # e.g. "1"
    name: str
    subphases: list[SubPhase] = field(default_factory=list)

    # ---- computed helpers ----

    @property
    def all_tasks(self) -> list[PlanTask]:
        return [t for sp in self.subphases for t in sp.tasks]

    @property
    def pending_tasks(self) -> list[PlanTask]:
        return [t for t in self.all_tasks if t.status == PlanTaskStatus.PENDING]

    @property
    def done_tasks(self) -> list[PlanTask]:
        return [t for t in self.all_tasks if t.status == PlanTaskStatus.DONE]

    @property
    def is_complete(self) -> bool:
        return all(sp.is_complete for sp in self.subphases)

    @property
    def has_escalated(self) -> bool:
        return any(sp.has_escalated for sp in self.subphases)

    def next_pending(self) -> PlanTask | None:
        """Return the first pending task across all subfases, in order."""
        for sp in self.subphases:
            task = sp.next_pending()
            if task:
                return task
        return None

    def get_subphase(self, subphase_id: str) -> SubPhase | None:
        return next((sp for sp in self.subphases if sp.id == subphase_id), None)

    def get_task(self, task_id: str) -> PlanTask | None:
        for sp in self.subphases:
            task = sp.get_task(task_id)
            if task:
                return task
        return None

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "subphases": [sp.to_dict() for sp in self.subphases],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Phase:
        return cls(
            id=data["id"],
            name=data["name"],
            subphases=[SubPhase.from_dict(sp) for sp in data.get("subphases", [])],
        )


# ---------------------------------------------------------------------------
# ProjectPlan
# ---------------------------------------------------------------------------


@dataclass
class ProjectPlan:
    """Root model representing the full hierarchical project plan."""

    name: str
    phases: list[Phase] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ---- computed helpers ----

    @property
    def all_tasks(self) -> list[PlanTask]:
        return [t for ph in self.phases for t in ph.all_tasks]

    @property
    def pending_tasks(self) -> list[PlanTask]:
        return [t for t in self.all_tasks if t.status == PlanTaskStatus.PENDING]

    @property
    def done_tasks(self) -> list[PlanTask]:
        return [t for t in self.all_tasks if t.status == PlanTaskStatus.DONE]

    @property
    def is_complete(self) -> bool:
        return all(ph.is_complete for ph in self.phases)

    def next_pending(self) -> PlanTask | None:
        """Return the very next pending task across all phases, in order."""
        for ph in self.phases:
            task = ph.next_pending()
            if task:
                return task
        return None

    def get_phase(self, phase_id: str) -> Phase | None:
        return next((ph for ph in self.phases if ph.id == phase_id), None)

    def get_subphase(self, subphase_id: str) -> SubPhase | None:
        for ph in self.phases:
            sp = ph.get_subphase(subphase_id)
            if sp:
                return sp
        return None

    def get_task(self, task_id: str) -> PlanTask | None:
        for ph in self.phases:
            task = ph.get_task(task_id)
            if task:
                return task
        return None

    def progress_summary(self) -> dict[str, int]:
        """Return counts by status for all tasks."""
        counts: dict[str, int] = {s.value: 0 for s in PlanTaskStatus}
        for task in self.all_tasks:
            counts[task.status.value] += 1
        return counts

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "phases": [ph.to_dict() for ph in self.phases],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectPlan:
        return cls(
            name=data["name"],
            phases=[Phase.from_dict(ph) for ph in data.get("phases", [])],
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# PLANO.md parser
# ---------------------------------------------------------------------------

# Matches: ## Fase 1 — Name  or  ## Fase 1: Name  or  ## 1 Name
_RE_PHASE = re.compile(r"^##\s+(?:Fase\s+)?(\d+)[\s\-\u2014:]+(.+)$")
# Matches: ### 1.1 Name
_RE_SUBPHASE = re.compile(r"^###\s+(\d+\.\d+)\s+(.+)$")
# Matches: - [ ] 1.1.1 Description  /  - [x] ...  /  - [!] ...  /  - [>] ...
_RE_TASK = re.compile(r"^-\s+\[([x!>\- ])\]\s+(\d+(?:\.\d+)+)\s+(.+)$", re.IGNORECASE)
# Matches: # Title  (first h1 only)
_RE_TITLE = re.compile(r"^#\s+(.+)$")

_CHECKBOX_TO_STATUS: dict[str, PlanTaskStatus] = {
    " ": PlanTaskStatus.PENDING,
    "x": PlanTaskStatus.DONE,
    "X": PlanTaskStatus.DONE,
    "!": PlanTaskStatus.ESCALATED,
    ">": PlanTaskStatus.RUNNING,
    "-": PlanTaskStatus.SKIPPED,
}


def parse_plan(path: str | Path) -> ProjectPlan:
    """Parse a PLANO.md file and return a ProjectPlan.

    Expected Markdown structure::

        # Project Name

        ## Fase 1 — Phase Name

        ### 1.1 SubPhase Name

        - [ ] 1.1.1 Task description
        - [x] 1.1.2 Completed task
        - [!] 1.1.3 Escalated task

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError: if the file has no recognisable title (# heading).
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return _parse_text(text, source=str(path))


def parse_plan_text(text: str) -> ProjectPlan:
    """Parse PLANO.md content from a string (useful for testing)."""
    return _parse_text(text, source="<string>")


def _parse_text(text: str, source: str) -> ProjectPlan:
    name: str | None = None
    phases: list[Phase] = []
    current_phase: Phase | None = None
    current_subphase: SubPhase | None = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        # --- project title ---
        if name is None:
            m = _RE_TITLE.match(line)
            if m:
                name = m.group(1).strip()
                continue

        # --- phase (## heading) ---
        m = _RE_PHASE.match(line)
        if m:
            # flush current subphase into current phase before switching
            if current_subphase is not None and current_phase is not None:
                current_phase.subphases.append(current_subphase)
                current_subphase = None
            if current_phase is not None:
                phases.append(current_phase)
            phase_id = m.group(1).strip()
            phase_name = m.group(2).strip()
            current_phase = Phase(id=phase_id, name=phase_name)
            continue

        # --- subphase (### heading) ---
        m = _RE_SUBPHASE.match(line)
        if m:
            if current_subphase is not None and current_phase is not None:
                current_phase.subphases.append(current_subphase)
            subphase_id = m.group(1).strip()
            subphase_name = m.group(2).strip()
            current_subphase = SubPhase(id=subphase_id, name=subphase_name)
            continue

        # --- task (- [x] ...) ---
        m = _RE_TASK.match(line)
        if m:
            checkbox = m.group(1)
            task_id = m.group(2).strip()
            description = m.group(3).strip()
            status = _CHECKBOX_TO_STATUS.get(checkbox, PlanTaskStatus.PENDING)
            task = PlanTask(id=task_id, description=description, status=status)
            if current_subphase is not None:
                current_subphase.tasks.append(task)
            # tasks outside a subphase are silently ignored (malformed plan)
            continue

    # flush remaining objects
    if current_subphase is not None and current_phase is not None:
        current_phase.subphases.append(current_subphase)
    if current_phase is not None:
        phases.append(current_phase)

    if name is None:
        raise ValueError(f"PLANO.md has no title (# heading): {source}")

    return ProjectPlan(name=name, phases=phases)


# ---------------------------------------------------------------------------
# PLANO.md writer
# ---------------------------------------------------------------------------

_STATUS_TO_CHECKBOX: dict[PlanTaskStatus, str] = {
    PlanTaskStatus.PENDING: " ",
    PlanTaskStatus.RUNNING: ">",
    PlanTaskStatus.DONE: "x",
    PlanTaskStatus.ESCALATED: "!",
    PlanTaskStatus.SKIPPED: "-",
}

# Matches a task line preserving leading whitespace and trailing content:
# group 1 = prefix before '[', group 2 = checkbox char, group 3 = task-id + rest
_RE_TASK_LINE = re.compile(r"^(-\s+\[)([x!>\- ])(\]\s+\d+(?:\.\d+)+\s+.+)$", re.IGNORECASE)


def write_plan(plan: ProjectPlan, path: str | Path) -> None:
    """Update PLANO.md in-place, rewriting only the checkbox of each task line.

    The original file is read and every task line (``- [ ] N.N.N ...``) is
    matched against *plan*.  The checkbox character is replaced to reflect the
    task's current :class:`PlanTaskStatus`; all other content (headings, prose,
    blank lines, indentation) is preserved verbatim.

    If a task line references an ID that is not present in *plan* (e.g. the
    plan was trimmed externally) the line is written unchanged.

    Args:
        plan: The :class:`ProjectPlan` whose task statuses are authoritative.
        path: Path to the PLANO.md file to update (created if absent).
    """
    path = Path(path)

    if path.exists():
        original = path.read_text(encoding="utf-8")
    else:
        # No existing file — generate from scratch.
        original = _render_plan(plan)

    updated_lines: list[str] = []
    for raw_line in original.splitlines(keepends=True):
        stripped = raw_line.rstrip("\n").rstrip("\r")
        m = _RE_TASK_LINE.match(stripped)
        if m:
            # Extract the task ID from the rest-of-line group (group 3).
            # group 3 looks like:  "] 1.1.2 Some description"
            rest = m.group(3)  # e.g. "] 1.1.1 Description"
            id_match = re.match(r"\]\s+(\d+(?:\.\d+)+)", rest)
            if id_match:
                task_id = id_match.group(1)
                task = plan.get_task(task_id)
                if task is not None:
                    new_checkbox = _STATUS_TO_CHECKBOX[task.status]
                    eol = raw_line[len(stripped):]  # preserve original line ending
                    updated_lines.append(m.group(1) + new_checkbox + rest + eol)
                    continue
        updated_lines.append(raw_line)

    # Preserve a trailing newline if original had one, add one if generated.
    content = "".join(updated_lines)
    if not content.endswith("\n"):
        content += "\n"

    path.write_text(content, encoding="utf-8")


def _render_plan(plan: ProjectPlan) -> str:
    """Render a :class:`ProjectPlan` to PLANO.md Markdown from scratch.

    Used when *write_plan* is called for a file that does not yet exist.
    Produces a canonical Markdown structure that ``parse_plan`` can round-trip.
    """
    lines: list[str] = [f"# {plan.name}", ""]
    for phase in plan.phases:
        lines.append(f"## Fase {phase.id} \u2014 {phase.name}")
        lines.append("")
        for sp in phase.subphases:
            lines.append(f"### {sp.id} {sp.name}")
            lines.append("")
            for task in sp.tasks:
                checkbox = _STATUS_TO_CHECKBOX[task.status]
                lines.append(f"- [{checkbox}] {task.id} {task.description}")
            lines.append("")
    return "\n".join(lines)
