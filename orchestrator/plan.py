"""Data models for the hierarchical project plan (PLANO.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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
