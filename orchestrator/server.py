"""FastAPI backend for the AI Dev Orchestrator dashboard.

Exposes the orchestrator as a local HTTP service with REST endpoints and
WebSocket streaming.

Endpoints
---------
POST   /api/run                  Start a full orchestration cycle
GET    /api/run/{run_id}         Poll status / result of a run
POST   /api/cancel/{run_id}      Cancel a running cycle
POST   /api/batch                Start a sequential batch of tasks
GET    /api/batch/{batch_id}     Poll status of a batch
GET    /api/projects             List registered projects
POST   /api/projects             Register a new project
DELETE /api/projects/{id}        Remove a project
GET    /api/history              Return cycle log history
GET    /api/metrics              Return aggregated metrics
GET    /api/templates            List available project templates
POST   /api/init                 Create a project from a template
GET    /api/health               Health check

Plan runner endpoints (Fase 7):
POST   /api/plan/run             Start hierarchical plan execution
GET    /api/plan/run/{id}        State of a plan run
POST   /api/plan/pause/{id}      Signal pause at next task boundary
POST   /api/plan/resume/{id}     Resume a paused plan run
POST   /api/plan/abort/{id}      Abort a plan run
GET    /api/plan/load            Parse PLANO.md from a project and return it
POST   /api/plan/generate        Generate PLANO.md via AI + Critic loop
POST   /api/plan/save            Save PLANO.md content to a project

WebSocket:
WS /ws/run/{run_id}          Real-time cycle events + history replay + keepalive 30s
WS /ws/plan/{plan_run_id}    Real-time plan runner events + history replay + resume action
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator import logger as log_store
from orchestrator import orchestrator as orch
from orchestrator import plan_runner as plan_runner_mod
from orchestrator import templates as tmpl
from orchestrator.config import Config
from orchestrator.context import build_tree, detect_stack, load_readme
from orchestrator.events import Event, EventBus, EventType, PauseController
from orchestrator.models import CycleRecord
from orchestrator.plan import ProjectPlan, parse_plan
from orchestrator.plan_runner import RunPlanOptions, TaskResult
from orchestrator.project_planner import generate_project_plan, run_project_plan_critic_loop

# ---------------------------------------------------------------------------
# Prompt paths (used by resolved-config endpoint)
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_ROLE_PROMPT_PATHS: dict[str, Path] = {
    "planner":  _PROMPTS_DIR / "planner_system.md",
    "critic":   _PROMPTS_DIR / "critic_system.md",
    "reviewer": _PROMPTS_DIR / "reviewer_system.md",
    "decisor":  _PROMPTS_DIR / "decisor_system.md",
}

# ---------------------------------------------------------------------------
# Projects registry
# ---------------------------------------------------------------------------

_PROJECTS_FILE = Path.home() / ".orchestrator" / "projects.json"


def _load_projects() -> list[dict[str, Any]]:
    if not _PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(_PROJECTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_projects(projects: list[dict[str, Any]]) -> None:
    _PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROJECTS_FILE.write_text(json.dumps(projects, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# In-memory run registry
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    """Tracks a single background orchestration run."""

    run_id: str
    task: str
    project_dir: str
    status: str = "running"       # running | approved | escalated | cancelled | error
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None
    record: CycleRecord | None = None
    diff: str = ""
    error: str | None = None
    bg_task: asyncio.Task | None = None  # type: ignore[type-arg]
    event_bus: EventBus = field(default_factory=EventBus)
    pause_controller: PauseController = field(default_factory=PauseController)
    # Internal — not part of __init__ / repr
    event_history: list[dict[str, Any]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )
    _client_queues: list[asyncio.Queue[dict[str, Any] | None]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # Align the EventBus run_id so emitted events carry the same ID as the run.
        self.event_bus.run_id = self.run_id
        self.event_bus.subscribe(self._capture_event)

    def _capture_event(self, event: Event) -> None:
        """Persist event to history and fan-out to connected WebSocket clients."""
        evt_dict = event.to_dict()
        self.event_history.append(evt_dict)
        for q in list(self._client_queues):
            q.put_nowait(evt_dict)
        # Terminal events: push sentinel None so WS handlers know the stream ended.
        if event.type in (EventType.CYCLE_APPROVED, EventType.CYCLE_ESCALATED):
            for q in list(self._client_queues):
                q.put_nowait(None)


# Module-level store — one server instance, in-memory is sufficient for local use.
_active_runs: dict[str, RunState] = {}


# ---------------------------------------------------------------------------
# Plan runner state (Fase 7)
# ---------------------------------------------------------------------------

@dataclass
class PlanRunState:
    """Tracks a hierarchical plan run (run_plan) initiated via the API."""

    id: str
    project_id: str
    project_path: str
    plan_path: str
    status: str = "running"   # running | paused | complete | aborted | error
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None
    plan_name: str = ""
    current_task_id: str | None = None
    pause_reason: str | None = None
    pause_context: dict[str, Any] | None = None
    error: str | None = None
    tasks_done: int = 0
    tasks_escalated: int = 0
    tasks_skipped: int = 0
    results: list[TaskResult] = field(default_factory=list)
    bg_task: asyncio.Task | None = None  # type: ignore[type-arg]
    event_bus: EventBus = field(default_factory=EventBus)
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    event_history: list[dict[str, Any]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )
    _client_queues: list[asyncio.Queue[dict[str, Any] | None]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self.event_bus.run_id = self.id
        self.pause_event.set()  # starts as "not paused"
        self.event_bus.subscribe(self._on_plan_event)

    def _on_plan_event(self, event: Event) -> None:
        evt_dict = event.to_dict()
        self.event_history.append(evt_dict)
        for q in list(self._client_queues):
            q.put_nowait(evt_dict)

        if event.type == EventType.PLAN_LOADED:
            self.plan_name = event.data.get("name", "")
        elif event.type == EventType.TASK_STARTED:
            self.current_task_id = event.data.get("task_id")
        elif event.type in (EventType.TASK_DONE, EventType.TASK_ESCALATED, EventType.TASK_SKIPPED):
            self.current_task_id = None
            if event.type == EventType.TASK_DONE:
                self.tasks_done += 1
            elif event.type == EventType.TASK_ESCALATED:
                self.tasks_escalated += 1
            else:
                self.tasks_skipped += 1
        elif event.type == EventType.PLAN_PAUSED:
            self.status = "paused"
            self.pause_reason = event.data.get("reason")
            self.pause_context = event.data.get("context")
        elif event.type == EventType.PLAN_RESUMED:
            self.status = "running"
            self.pause_reason = None
            self.pause_context = None
        elif event.type in (EventType.PLAN_COMPLETE, EventType.PLAN_ABORTED):
            for q in list(self._client_queues):
                q.put_nowait(None)  # terminal sentinel for WS clients


_active_plan_runs: dict[str, PlanRunState] = {}


async def _wait_for_run(run_id: str, *, max_wait: float = 5.0) -> RunState | None:
    """Poll _active_runs until *run_id* appears or *max_wait* seconds elapse.

    Handles the race where a WebSocket client connects immediately after
    ``POST /api/run`` returns but before the RunState is fully registered.
    """
    interval = 0.1
    waited = 0.0
    while waited < max_wait:
        if run_id in _active_runs:
            return _active_runs[run_id]
        await asyncio.sleep(interval)
        waited += interval
    return _active_runs.get(run_id)


async def _wait_for_plan_run(plan_run_id: str, *, max_wait: float = 5.0) -> PlanRunState | None:
    """Poll _active_plan_runs until *plan_run_id* appears or *max_wait* seconds elapse.

    Handles the race where a WebSocket client connects immediately after
    ``POST /api/plan/run`` returns but before the PlanRunState is registered.
    """
    interval = 0.1
    waited = 0.0
    while waited < max_wait:
        if plan_run_id in _active_plan_runs:
            return _active_plan_runs[plan_run_id]
        await asyncio.sleep(interval)
        waited += interval
    return _active_plan_runs.get(plan_run_id)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    task: str
    project_dir: str = "."


class RunResponse(BaseModel):
    run_id: str
    status: str
    message: str = ""


class BatchRequest(BaseModel):
    tasks: list[str]
    project_dir: str = "."


class BatchResponse(BaseModel):
    batch_id: str
    task_count: int
    status: str = "running"


class ProjectCreate(BaseModel):
    name: str
    path: str


class InitRequest(BaseModel):
    template: str
    project_dir: str
    force: bool = False


class InitResponse(BaseModel):
    template: str
    project_dir: str
    files_created: list[str]


class EditPlanRequest(BaseModel):
    plan: dict[str, Any]  # Serialized TaskPlan (keys: description, steps, …)


class ConfigUpdate(BaseModel):
    content: str


class ConfigParseRequest(BaseModel):
    content: str


class PlanRunRequest(BaseModel):
    project_id: str
    plan_path: str = "PLANO.md"       # relative to project dir
    phase: str | None = None
    subtask: str | None = None
    auto_continue: bool = False
    pause_after_subtask: bool = True
    pause_after_phase: bool = True


class PlanGenerateRequest(BaseModel):
    project_id: str
    description: str
    premises: str = ""
    stack: str = ""
    run_critic: bool = True


class PlanSaveRequest(BaseModel):
    project_id: str
    content: str
    plan_path: str = "PLANO.md"


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------

async def _run_cycle_bg(state: RunState) -> None:
    """Execute one orchestration cycle, updating *state* when done."""
    try:
        config = Config.load(state.project_dir)
        record, diff, _decision = await orch.run_cycle(
            state.task, config,
            event_bus=state.event_bus,
            pause_controller=state.pause_controller,
        )
        state.record = record
        state.diff = diff
        state.status = record.status.value
        state.finished_at = datetime.now().isoformat()
    except asyncio.CancelledError:
        state.status = "cancelled"
        state.finished_at = datetime.now().isoformat()
        raise
    except Exception as exc:  # noqa: BLE001
        state.status = "error"
        state.error = str(exc)
        state.finished_at = datetime.now().isoformat()
        # Emit a terminal event so WebSocket clients exit the "running" state.
        # Without this, the frontend hangs indefinitely after retry exhaustion
        # or any other unhandled error, because the sentinel (None) is only
        # pushed on cycle_approved / cycle_escalated events.
        await state.event_bus.emit(
            EventType.CYCLE_ESCALATED,
            {"task": state.task, "reason": str(exc)},
        )


async def _run_batch_bg(
    batch_id: str,
    task_states: list[RunState],
) -> None:
    """Execute a list of runs sequentially, stopping if the batch is cancelled."""
    batch_state = _active_runs[batch_id]

    for state in task_states:
        if batch_state.status == "cancelled":
            state.status = "cancelled"
            continue
        try:
            await _run_cycle_bg(state)
        except asyncio.CancelledError:
            state.status = "cancelled"
            for remaining in task_states:
                if remaining.status == "running":
                    remaining.status = "cancelled"
            raise

    if batch_state.status == "running":
        batch_state.status = "completed"
        batch_state.finished_at = datetime.now().isoformat()


# ---------------------------------------------------------------------------
# Plan runner background task (Fase 7)
# ---------------------------------------------------------------------------

async def _run_plan_bg(state: PlanRunState, options: RunPlanOptions) -> None:
    """Execute run_plan in the background, updating PlanRunState as events arrive."""
    try:
        config = Config.load(state.project_path)
        run_result = await plan_runner_mod.run_plan(
            state.plan_path,
            config,
            options,
            event_bus=state.event_bus,
            pause_event=state.pause_event,
        )
        state.results = run_result.results
        state.status = "complete"
        state.finished_at = datetime.now().isoformat()
    except asyncio.CancelledError:
        state.status = "aborted"
        state.finished_at = datetime.now().isoformat()
        await state.event_bus.emit(EventType.PLAN_ABORTED, {"reason": "user cancelled"})
        raise
    except Exception as exc:  # noqa: BLE001
        state.status = "error"
        state.error = str(exc)
        state.finished_at = datetime.now().isoformat()
        await state.event_bus.emit(EventType.PLAN_ABORTED, {"reason": str(exc)})


# ---------------------------------------------------------------------------
# Metrics helper
# ---------------------------------------------------------------------------

def _compute_metrics(log_dir: str = "logs") -> dict[str, Any]:
    """Compute aggregated metrics from the log directory."""
    entries = log_store.list_runs(log_dir, limit=0)
    total = len(entries)
    if not total:
        return {"total": 0}

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
                s = datetime.fromisoformat(started)
                f = datetime.fromisoformat(finished)
                durations.append((f - s).total_seconds())
            except ValueError:
                pass
    avg_duration = sum(durations) / len(durations) if durations else None

    first_attempt_approved = sum(
        1 for e in entries
        if e.get("status") == "approved" and e.get("attempt", 1) == 1
    )

    return {
        "total": total,
        "approved": approved,
        "escalated": escalated,
        "approval_rate": round(approved / total, 3),
        "first_attempt_approval_rate": round(first_attempt_approved / total, 3),
        "avg_review_score": round(avg_score, 2) if avg_score is not None else None,
        "avg_attempts": round(avg_attempts, 2),
        "avg_duration_seconds": round(avg_duration, 1) if avg_duration is not None else None,
        "recent": entries[:5],
    }


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Dev Orchestrator",
    description="Local API for the AI Dev Orchestrator dashboard",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------

@app.post("/api/run", response_model=RunResponse, status_code=202)
async def start_run(req: RunRequest) -> RunResponse:
    """Start a full orchestration cycle in the background.

    Returns immediately with a ``run_id``.  Poll ``GET /api/run/{run_id}``
    or subscribe to ``WS /ws/run/{run_id}`` for real-time updates.
    """
    run_id = str(uuid.uuid4())
    state = RunState(run_id=run_id, task=req.task, project_dir=req.project_dir)
    _active_runs[run_id] = state
    state.bg_task = asyncio.create_task(_run_cycle_bg(state))
    return RunResponse(run_id=run_id, status="running", message="Cycle started")


@app.get("/api/run/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    """Return the current state of a run (status, result, diff)."""
    state = _active_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    result: dict[str, Any] = {
        "run_id": state.run_id,
        "task": state.task,
        "project_dir": state.project_dir,
        "status": state.status,
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "error": state.error,
    }
    if state.record is not None:
        result["record"] = state.record.to_dict()
        result["diff"] = state.diff

    return result


@app.post("/api/cancel/{run_id}")
async def cancel_run(run_id: str) -> dict[str, Any]:
    """Request cancellation of a running cycle.

    If the run is not active, returns its current status without error.
    """
    state = _active_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if state.status != "running":
        return {"run_id": run_id, "status": state.status, "message": "Run is not active"}

    if state.bg_task and not state.bg_task.done():
        state.bg_task.cancel()

    state.status = "cancelled"
    state.finished_at = datetime.now().isoformat()
    return {"run_id": run_id, "status": "cancelled", "message": "Cancellation requested"}


@app.post("/api/pause/{run_id}")
async def pause_run(run_id: str) -> dict[str, Any]:
    """Pause the cycle before its next pipeline stage.

    The orchestrator will block at the next :meth:`check_pause` call until
    ``POST /api/resume/{run_id}`` (or ``/api/edit-plan/{run_id}``) is called.
    If the run remains paused for more than 30 minutes it is auto-cancelled.
    """
    state = _active_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if state.status != "running":
        return {"run_id": run_id, "status": state.status, "message": "Run is not active"}

    state.pause_controller.pause()
    state.status = "paused"
    await state.event_bus.emit(EventType.CYCLE_PAUSED, {"run_id": run_id})
    return {"run_id": run_id, "status": "paused", "message": "Pause requested"}


@app.post("/api/resume/{run_id}")
async def resume_run(run_id: str) -> dict[str, Any]:
    """Resume a paused cycle without changing the plan."""
    state = _active_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if state.status != "paused":
        return {"run_id": run_id, "status": state.status, "message": "Run is not paused"}

    state.status = "running"
    state.pause_controller.resume()
    await state.event_bus.emit(EventType.CYCLE_RESUMED, {"run_id": run_id})
    return {"run_id": run_id, "status": "running", "message": "Run resumed"}


@app.post("/api/edit-plan/{run_id}")
async def edit_plan(run_id: str, req: EditPlanRequest) -> dict[str, Any]:
    """Replace the plan and resume a paused cycle.

    The cycle must be paused (via ``POST /api/pause/{run_id}``) before
    calling this endpoint.  The edited plan replaces the one generated by
    the Planner + Critic pipeline and is used for the next execution attempt.
    """
    state = _active_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    if state.status != "paused":
        raise HTTPException(status_code=409, detail="Run must be paused to edit the plan")

    from orchestrator.models import TaskPlan
    try:
        edited_plan = TaskPlan.from_dict(req.plan)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid plan payload: {exc}")

    state.status = "running"
    state.pause_controller.resume(edited_plan=edited_plan)
    await state.event_bus.emit(EventType.CYCLE_RESUMED, {"run_id": run_id, "plan_edited": True})
    return {"run_id": run_id, "status": "running", "message": "Plan updated and run resumed"}


# ---------------------------------------------------------------------------
# Batch endpoints
# ---------------------------------------------------------------------------

@app.post("/api/batch", response_model=BatchResponse, status_code=202)
async def start_batch(req: BatchRequest) -> BatchResponse:
    """Start a sequential batch of tasks in the background."""
    if not req.tasks:
        raise HTTPException(status_code=422, detail="tasks list must not be empty")

    batch_id = str(uuid.uuid4())
    batch_state = RunState(
        run_id=batch_id,
        task=f"[batch] {len(req.tasks)} task(s)",
        project_dir=req.project_dir,
    )
    _active_runs[batch_id] = batch_state

    task_states = [
        RunState(run_id=f"{batch_id}:{i}", task=t, project_dir=req.project_dir)
        for i, t in enumerate(req.tasks)
    ]
    for s in task_states:
        _active_runs[s.run_id] = s

    batch_state.bg_task = asyncio.create_task(_run_batch_bg(batch_id, task_states))
    return BatchResponse(batch_id=batch_id, task_count=len(req.tasks))


@app.get("/api/batch/{batch_id}")
async def get_batch(batch_id: str) -> dict[str, Any]:
    """Return the status of a batch run and its individual task states."""
    batch_state = _active_runs.get(batch_id)
    if batch_state is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")

    tasks = [
        {
            "run_id": v.run_id,
            "task": v.task,
            "status": v.status,
            "started_at": v.started_at,
            "finished_at": v.finished_at,
        }
        for k, v in _active_runs.items()
        if k.startswith(f"{batch_id}:")
    ]

    return {
        "batch_id": batch_id,
        "status": batch_state.status,
        "started_at": batch_state.started_at,
        "finished_at": batch_state.finished_at,
        "task_count": len(tasks),
        "tasks": tasks,
    }


# ---------------------------------------------------------------------------
# Plan runner endpoints (Fase 7)
# ---------------------------------------------------------------------------

def _get_plan_run_or_404(plan_run_id: str) -> PlanRunState:
    state = _active_plan_runs.get(plan_run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Plan run '{plan_run_id}' not found")
    return state


@app.post("/api/plan/run", status_code=202)
async def start_plan_run(req: PlanRunRequest) -> dict[str, Any]:
    """Start a hierarchical plan execution in the background.

    Reads ``PLANO.md`` from the project directory and runs each pending task
    through the full agent cycle.  Returns a ``plan_run_id`` immediately;
    poll ``GET /api/plan/run/{id}`` or connect to ``WS /ws/plan/{id}`` for
    progress.
    """
    project = _get_project_or_404(req.project_id)
    project_path = project["path"]
    abs_plan = str(Path(project_path) / req.plan_path)

    if not Path(abs_plan).exists():
        raise HTTPException(
            status_code=404,
            detail=f"PLANO.md not found at '{abs_plan}'. Run 'plan generate' first.",
        )

    plan_run_id = str(uuid.uuid4())
    state = PlanRunState(
        id=plan_run_id,
        project_id=req.project_id,
        project_path=project_path,
        plan_path=abs_plan,
    )
    _active_plan_runs[plan_run_id] = state

    options = RunPlanOptions(
        phase=req.phase,
        subtask=req.subtask,
        auto_continue=req.auto_continue,
        pause_after_subtask=req.pause_after_subtask,
        pause_after_phase=req.pause_after_phase,
        yes=True,   # skip click.confirm prompts (commits handled automatically)
    )
    state.bg_task = asyncio.create_task(_run_plan_bg(state, options))

    return {"plan_run_id": plan_run_id, "status": "running", "message": "Plan execution started"}


@app.get("/api/plan/run/{plan_run_id}")
async def get_plan_run(plan_run_id: str) -> dict[str, Any]:
    """Return the current state of a plan run."""
    state = _get_plan_run_or_404(plan_run_id)
    return {
        "plan_run_id": state.id,
        "project_id": state.project_id,
        "plan_name": state.plan_name,
        "status": state.status,
        "current_task_id": state.current_task_id,
        "pause_reason": state.pause_reason,
        "pause_context": state.pause_context,
        "tasks_done": state.tasks_done,
        "tasks_escalated": state.tasks_escalated,
        "tasks_skipped": state.tasks_skipped,
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "error": state.error,
    }


@app.post("/api/plan/pause/{plan_run_id}")
async def pause_plan_run(plan_run_id: str) -> dict[str, Any]:
    """Signal the plan runner to pause at the next task boundary.

    The runner will pause after completing its current task.  Call
    ``POST /api/plan/resume/{id}`` to continue.
    """
    state = _get_plan_run_or_404(plan_run_id)
    if state.status not in ("running",):
        return {"plan_run_id": plan_run_id, "status": state.status, "message": "Plan run is not active"}

    # Clear the pause_event so the runner blocks at the next boundary.
    state.pause_event.clear()
    # The status will transition to "paused" when PLAN_PAUSED is emitted.
    return {"plan_run_id": plan_run_id, "status": state.status, "message": "Pause requested at next boundary"}


@app.post("/api/plan/resume/{plan_run_id}")
async def resume_plan_run(plan_run_id: str) -> dict[str, Any]:
    """Resume a paused plan run."""
    state = _get_plan_run_or_404(plan_run_id)
    if state.status != "paused":
        return {"plan_run_id": plan_run_id, "status": state.status, "message": "Plan run is not paused"}

    state.pause_event.set()
    # status will update to "running" when PLAN_RESUMED is emitted
    return {"plan_run_id": plan_run_id, "status": "running", "message": "Plan run resumed"}


@app.post("/api/plan/abort/{plan_run_id}")
async def abort_plan_run(plan_run_id: str) -> dict[str, Any]:
    """Abort an active (running or paused) plan run."""
    state = _get_plan_run_or_404(plan_run_id)
    if state.status not in ("running", "paused"):
        return {"plan_run_id": plan_run_id, "status": state.status, "message": "Plan run is not active"}

    # Unblock any pending pause so the background task can reach a cancellation point.
    state.pause_event.set()
    if state.bg_task and not state.bg_task.done():
        state.bg_task.cancel()

    state.status = "aborted"
    state.finished_at = datetime.now().isoformat()
    return {"plan_run_id": plan_run_id, "status": "aborted", "message": "Plan run aborted"}


@app.get("/api/plan/load")
async def load_plan(project_id: str, plan_path: str = "PLANO.md") -> dict[str, Any]:
    """Parse PLANO.md from a project and return its structure.

    Returns the plan hierarchy (phases → subphases → tasks) with status of
    each task so the frontend can render the plan tree without starting a run.
    """
    project = _get_project_or_404(project_id)
    abs_plan = Path(project["path"]) / plan_path

    if not abs_plan.exists():
        raise HTTPException(status_code=404, detail=f"'{plan_path}' not found in project")

    try:
        plan = parse_plan(abs_plan)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse plan: {exc}")

    def _serialise_plan(p: ProjectPlan) -> dict[str, Any]:
        return {
            "name": p.name,
            "phases": [
                {
                    "id": ph.id,
                    "name": ph.name,
                    "subphases": [
                        {
                            "id": sp.id,
                            "name": sp.name,
                            "tasks": [
                                {
                                    "id": t.id,
                                    "description": t.description,
                                    "status": t.status.value,
                                    "commit_hash": t.commit_hash,
                                }
                                for t in sp.tasks
                            ],
                        }
                        for sp in ph.subphases
                    ],
                    "task_count": len(ph.all_tasks),
                    "done_count": sum(1 for t in ph.all_tasks if t.is_done),
                }
                for ph in p.phases
            ],
            "total_tasks": sum(len(ph.all_tasks) for ph in p.phases),
            "done_tasks": sum(1 for ph in p.phases for t in ph.all_tasks if t.is_done),
        }

    return _serialise_plan(plan)


@app.post("/api/plan/generate", status_code=202)
async def generate_plan(req: PlanGenerateRequest) -> dict[str, Any]:
    """Generate a PLANO.md via AI and optionally refine it with the Critic loop.

    Returns the generated Markdown and the parsed plan structure so the
    frontend can display a preview before saving.
    """
    project = _get_project_or_404(req.project_id)

    try:
        config = Config.load(project["path"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to load config: {exc}")

    try:
        raw_md, plan = await generate_project_plan(
            req.description, config, premises=req.premises, stack=req.stack
        )
        if req.run_critic:
            raw_md, plan = await run_project_plan_critic_loop(
                req.description, raw_md, plan, config,
                premises=req.premises, stack=req.stack,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Plan generation failed: {exc}")

    return {
        "raw_md": raw_md,
        "plan": {
            "name": plan.name,
            "phase_count": len(plan.phases),
            "task_count": sum(len(ph.all_tasks) for ph in plan.phases),
        },
    }


@app.post("/api/plan/save")
async def save_plan(req: PlanSaveRequest) -> dict[str, Any]:
    """Write PLANO.md content to the project directory."""
    project = _get_project_or_404(req.project_id)
    target = Path(project["path"]) / req.plan_path

    try:
        target.write_text(req.content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save plan: {exc}")

    return {"saved": True, "path": str(target)}



# ---------------------------------------------------------------------------
# Projects endpoints
# ---------------------------------------------------------------------------

@app.get("/api/projects")
async def list_projects() -> list[dict[str, Any]]:
    """Return all registered projects."""
    return _load_projects()


@app.post("/api/projects", status_code=201)
async def create_project(req: ProjectCreate) -> dict[str, Any]:
    """Register a new project by name and local path."""
    path = str(Path(req.path).resolve())
    projects = _load_projects()
    project_id = str(uuid.uuid4())
    entry: dict[str, Any] = {"id": project_id, "name": req.name, "path": path}
    projects.append(entry)
    _save_projects(projects)
    return entry


def _get_project_or_404(project_id: str) -> dict[str, Any]:
    """Return the project dict for *project_id* or raise HTTP 404."""
    projects = _load_projects()
    project = next((p for p in projects if p.get("id") == project_id), None)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project


@app.get("/api/projects/{project_id}/info")
async def get_project_info(project_id: str) -> dict[str, Any]:
    """Return stack detection and path existence for a project."""
    project = _get_project_or_404(project_id)
    path = Path(project["path"])
    if not path.exists():
        return {"id": project_id, "stack": [], "path_exists": False}
    return {"id": project_id, "stack": detect_stack(path), "path_exists": True}


@app.get("/api/projects/{project_id}/readme")
async def get_project_readme(project_id: str) -> dict[str, Any]:
    """Return the README content for a project (raw text, empty string if not found)."""
    project = _get_project_or_404(project_id)
    path = Path(project["path"])
    if not path.exists():
        return {"content": "", "found": False}
    content = load_readme(path)
    return {"content": content, "found": bool(content)}


@app.get("/api/projects/{project_id}/tree")
async def get_project_tree(project_id: str) -> dict[str, Any]:
    """Return the directory tree string for a project (plain text, no markdown wrapper)."""
    project = _get_project_or_404(project_id)
    path = Path(project["path"])
    if not path.exists():
        return {"content": ""}
    return {"content": build_tree(path)}


@app.get("/api/projects/{project_id}/config")
async def get_project_config(project_id: str) -> dict[str, Any]:
    """Return the .orchestrator.yaml content and parsed fields for a project."""
    project = _get_project_or_404(project_id)
    config_path = Path(project["path"]) / ".orchestrator.yaml"
    if not config_path.exists():
        return {"content": "", "found": False, "fields": {}}
    content = config_path.read_text(encoding="utf-8")
    try:
        fields = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        fields = {}
    return {"content": content, "found": True, "fields": fields}


@app.put("/api/projects/{project_id}/config")
async def put_project_config(project_id: str, req: ConfigUpdate) -> dict[str, Any]:
    """Write *req.content* to the .orchestrator.yaml of a project."""
    project = _get_project_or_404(project_id)
    config_path = Path(project["path"]) / ".orchestrator.yaml"
    config_path.write_text(req.content, encoding="utf-8")
    return {"saved": True, "path": str(config_path)}


@app.post("/api/projects/{project_id}/config-parse")
async def parse_project_config(project_id: str, req: ConfigParseRequest) -> dict[str, Any]:
    """Parse raw YAML text and return structured fields (no file I/O).

    Used by the frontend to convert a raw YAML string into structured form
    fields when switching from Raw to Visual editing mode.
    """
    _get_project_or_404(project_id)  # ensure project exists
    try:
        fields = yaml.safe_load(req.content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")
    if not isinstance(fields, dict):
        raise HTTPException(status_code=422, detail="YAML root must be a mapping")
    return {"fields": fields}


@app.get("/api/projects/{project_id}/resolved-config")
async def get_resolved_config(project_id: str) -> dict[str, Any]:
    """Return the fully-resolved config for a project (all 3 layers merged).

    Combines global defaults, project-level ``.orchestrator.yaml``, and
    environment-variable overrides into a single view.  API keys are excluded.
    The ``resolved_prompts`` field contains the actual system-prompt text each
    agent will receive (after applying any ``prompts:`` overrides from the
    project YAML).
    """
    project = _get_project_or_404(project_id)
    try:
        config = Config.load(project["path"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to load config: {exc}")

    resolved_prompts: dict[str, str] = {
        role: config.load_prompt(role, path)
        for role, path in _ROLE_PROMPT_PATHS.items()
    }

    return {
        "planner_provider":        config.planner_provider,
        "critic_provider":         config.critic_provider,
        "reviewer_provider":       config.reviewer_provider,
        "decisor_provider":        config.decisor_provider,
        "google_model":            config.google_model,
        "openai_model":            config.openai_model,
        "critic_min_rounds":       config.critic_min_rounds,
        "critic_max_rounds":       config.critic_max_rounds,
        "max_retries":             config.max_retries,
        "git_auto_branch":         config.git_auto_branch,
        "git_conventional_commits": config.git_conventional_commits,
        "prompt_overrides":        config.prompt_overrides,
        "resolved_prompts":        resolved_prompts,
    }


@app.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    """Remove a project from the registry."""
    projects = _load_projects()
    updated = [p for p in projects if p.get("id") != project_id]
    if len(updated) == len(projects):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    _save_projects(updated)


# ---------------------------------------------------------------------------
# History & Metrics endpoints
# ---------------------------------------------------------------------------

@app.get("/api/history")
async def get_history(limit: int = 20, log_dir: str = "logs") -> list[dict[str, Any]]:
    """Return cycle log entries (newest first)."""
    return log_store.list_runs(log_dir, limit=limit)


@app.get("/api/metrics")
async def get_metrics(log_dir: str = "logs") -> dict[str, Any]:
    """Return aggregated orchestration metrics."""
    return _compute_metrics(log_dir)


# ---------------------------------------------------------------------------
# Templates endpoints
# ---------------------------------------------------------------------------

@app.get("/api/templates")
async def list_templates_route() -> list[dict[str, Any]]:
    """List all available project templates."""
    return [{"name": t.name, "description": t.description} for t in tmpl.list_templates()]


@app.post("/api/init")
async def init_project_route(req: InitRequest) -> InitResponse:
    """Create a new project from a template."""
    selected = tmpl.get_template(req.template)
    if selected is None:
        available = [t.name for t in tmpl.list_templates()]
        raise HTTPException(
            status_code=404,
            detail=f"Unknown template '{req.template}'. Available: {available}",
        )

    target = Path(req.project_dir).resolve()
    try:
        written = tmpl.init_project(selected, target, force=req.force)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return InitResponse(
        template=req.template,
        project_dir=str(target),
        files_created=[str(p) for p in written],
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Simple liveness probe."""
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Frontend static-file mounting (called by CLI before uvicorn.run)
# ---------------------------------------------------------------------------

def mount_frontend(dist_path: Path | str) -> None:
    """Mount a built React frontend as static files served from ``/``.

    Must be called *before* starting uvicorn so that the route is registered
    at startup.  API routes defined above take precedence over static files,
    so ``/api/*`` and ``/ws/*`` continue to work normally.

    The ``html=True`` option instructs FastAPI to return ``index.html`` for
    any path that does not match a static file — required for React
    client-side routing (e.g. ``/projects``, ``/history``).

    Args:
        dist_path: Path to the ``dist/`` directory produced by ``npm run build``.
    """
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/",
        StaticFiles(directory=str(dist_path), html=True),
        name="frontend",
    )


# ---------------------------------------------------------------------------
# WebSocket — real-time event streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/run/{run_id}")
async def ws_run(websocket: WebSocket, run_id: str) -> None:
    """Stream EventBus events for *run_id* to the connected client.

    Protocol
    --------
    * Client connects.  Server accepts and immediately replays any events that
      were emitted before the connection was established (history replay).
    * Subsequent events are forwarded as JSON objects in real time.
    * When the run reaches a terminal state (``cycle_approved`` or
      ``cycle_escalated``), the server sends a final ``{"type": "done"}``
      message and closes the connection.
    * A ``{"type": "ping"}`` keepalive is sent every 30 s while waiting.
    * If *run_id* is unknown after 5 s the server sends
      ``{"type": "error", "detail": "Run not found"}`` and closes.

    Multiple clients may connect to the same *run_id* simultaneously.
    """
    state = await _wait_for_run(run_id)

    await websocket.accept()

    if state is None:
        await websocket.send_json({"type": "error", "detail": f"Run '{run_id}' not found"})
        await websocket.close(code=4004)
        return

    # Register per-client queue THEN snapshot history.
    # Because asyncio is single-threaded, no event can arrive between these two
    # lines — so the snapshot captures exactly events[0..N) and the queue will
    # receive events[N..).  No duplicates, no gaps.
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    history_snapshot = list(state.event_history)
    state._client_queues.append(queue)

    # Statuses where the run is still active (streaming continues).
    _streaming = {"running", "paused"}

    try:
        # Replay history to late-joining clients.
        for evt in history_snapshot:
            await websocket.send_json(evt)

        # If the run already finished, drain the queue (may contain a terminal
        # event that arrived between snapshot and queue registration) and exit.
        if state.status not in _streaming:
            while not queue.empty():
                evt = queue.get_nowait()
                if evt is not None:
                    await websocket.send_json(evt)
            await websocket.send_json({"type": "done", "run_id": run_id})
            return

        # Stream live events until a sentinel (None) signals the run is over.
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "run_id": run_id})
                continue

            if evt is None:
                # Terminal event was already forwarded; just signal completion.
                await websocket.send_json({"type": "done", "run_id": run_id})
                break

            await websocket.send_json(evt)

    except Exception:  # noqa: BLE001 — client disconnect, network error, etc.
        pass
    finally:
        with contextlib.suppress(ValueError):
            state._client_queues.remove(queue)
        with contextlib.suppress(Exception):
            await websocket.close()


@app.websocket("/ws/plan/{plan_run_id}")
async def ws_plan(websocket: WebSocket, plan_run_id: str) -> None:
    """Stream EventBus events for a hierarchical plan run to the connected client.

    Protocol
    --------
    * Client connects.  Server accepts and immediately replays any events
      emitted before the connection was established (history replay).
    * Subsequent events are forwarded as JSON objects in real time.
    * Cycle-level events (``cycle_*``) for the task currently executing are
      also forwarded — the frontend may use them to drive the agent streaming
      card via the task's ``run_id``.
    * When the plan reaches a terminal state (``plan_complete`` or
      ``plan_aborted``), the server sends ``{"type": "done"}`` and closes.
    * A ``{"type": "ping"}`` keepalive is sent every 30 s while waiting.
    * The client may send ``{"action": "resume"}`` to unblock a paused plan
      run (equivalent to ``POST /api/plan/resume/{id}``).
    * If *plan_run_id* is unknown after 5 s the server sends
      ``{"type": "error", "detail": "..."}`` and closes with code 4004.

    Multiple clients may connect to the same *plan_run_id* simultaneously.
    """
    state = await _wait_for_plan_run(plan_run_id)

    await websocket.accept()

    if state is None:
        await websocket.send_json(
            {"type": "error", "detail": f"Plan run '{plan_run_id}' not found"}
        )
        await websocket.close(code=4004)
        return

    # Register per-client queue THEN snapshot history — same race-free pattern
    # as ws_run: no event can arrive between these two lines in asyncio's
    # single-threaded execution model.
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    history_snapshot = list(state.event_history)
    state._client_queues.append(queue)

    # Statuses where streaming should continue (run is still active).
    _streaming = {"running", "paused"}

    async def _handle_client_messages() -> None:
        """Process incoming messages from the WebSocket client.

        Supports ``{"action": "resume"}`` to unblock a paused plan run.
        Any other messages are silently ignored.  Exits on disconnect or
        parse error.
        """
        while True:
            try:
                msg = await websocket.receive_json()
                if isinstance(msg, dict) and msg.get("action") == "resume":
                    state.pause_event.set()
            except Exception:  # noqa: BLE001 — disconnect or parse error
                break

    try:
        # Replay history to late-joining clients.
        for evt in history_snapshot:
            await websocket.send_json(evt)

        # If the plan already finished, drain the queue (may contain a terminal
        # event that arrived between snapshot and queue registration) and exit.
        if state.status not in _streaming:
            while not queue.empty():
                evt = queue.get_nowait()
                if evt is not None:
                    await websocket.send_json(evt)
            await websocket.send_json({"type": "done", "plan_run_id": plan_run_id})
            return

        # Stream live events; also accept client messages concurrently.
        client_task = asyncio.create_task(_handle_client_messages())
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping", "plan_run_id": plan_run_id})
                    continue

                if evt is None:
                    # Terminal sentinel — plan is complete or aborted.
                    await websocket.send_json({"type": "done", "plan_run_id": plan_run_id})
                    break

                await websocket.send_json(evt)
        finally:
            client_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await client_task

    except Exception:  # noqa: BLE001 — client disconnect, network error, etc.
        pass
    finally:
        with contextlib.suppress(ValueError):
            state._client_queues.remove(queue)
        with contextlib.suppress(Exception):
            await websocket.close()
