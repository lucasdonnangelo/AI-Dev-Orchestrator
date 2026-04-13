"""FastAPI backend for the AI Dev Orchestrator dashboard.

Exposes the orchestrator as a local HTTP service with REST endpoints and
(in Phase 5.1.3) WebSocket streaming.

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

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator import logger as log_store
from orchestrator import orchestrator as orch
from orchestrator import templates as tmpl
from orchestrator.config import Config
from orchestrator.context import build_tree, detect_stack, load_readme
from orchestrator.events import Event, EventBus, EventType, PauseController
from orchestrator.models import CycleRecord

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


@app.post("/api/cancel/{run_id}")
async def _cancel_alias(run_id: str) -> dict[str, Any]:  # type: ignore[misc]
    # Handled above — this ensures batch_id can also be cancelled via the same endpoint.
    return await cancel_run(run_id)


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
    """Return the .orchestrator.yaml content for a project."""
    project = _get_project_or_404(project_id)
    config_path = Path(project["path"]) / ".orchestrator.yaml"
    if not config_path.exists():
        return {"content": "", "found": False}
    content = config_path.read_text(encoding="utf-8")
    return {"content": content, "found": True}


@app.put("/api/projects/{project_id}/config")
async def put_project_config(project_id: str, req: ConfigUpdate) -> dict[str, Any]:
    """Write *req.content* to the .orchestrator.yaml of a project."""
    project = _get_project_or_404(project_id)
    config_path = Path(project["path"]) / ".orchestrator.yaml"
    config_path.write_text(req.content, encoding="utf-8")
    return {"saved": True, "path": str(config_path)}


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
