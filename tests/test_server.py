"""Unit tests for orchestrator/server.py — REST API endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from orchestrator.events import EventType
from orchestrator.models import CycleRecord, CycleStatus, TaskPlan, Complexity
from orchestrator.server import (
    PlanRunState,
    RunState,
    _active_plan_runs,
    _active_runs,
    _compute_metrics,
    _load_projects,
    _save_projects,
    app,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_active_runs():
    """Reset in-memory run stores between tests."""
    _active_runs.clear()
    _active_plan_runs.clear()
    yield
    _active_runs.clear()
    _active_plan_runs.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_plan() -> TaskPlan:
    return TaskPlan(
        description="test plan",
        files_to_create=["a.py"],
        files_to_modify=[],
        steps=["Step 1"],
        acceptance_criteria=["it works"],
        estimated_complexity=Complexity.LOW,
    )


def _make_record(status: CycleStatus = CycleStatus.APPROVED) -> CycleRecord:
    from datetime import datetime
    r = CycleRecord(task="test task", status=status, plan=_make_plan())
    r.finished_at = datetime.now().isoformat()
    return r


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_ok(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_version(self, client: TestClient):
        resp = client.get("/api/health")
        assert "version" in resp.json()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_list_returns_all_templates(self, client: TestClient):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "fastapi" in names
        assert "python-cli" in names
        assert "react" in names

    def test_list_has_description(self, client: TestClient):
        resp = client.get("/api/templates")
        for t in resp.json():
            assert "name" in t
            assert "description" in t


class TestInitProject:
    def test_unknown_template_returns_404(self, client: TestClient, tmp_path: Path):
        resp = client.post("/api/init", json={"template": "nonexistent", "project_dir": str(tmp_path)})
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]

    def test_valid_template_creates_files(self, client: TestClient, tmp_path: Path):
        resp = client.post("/api/init", json={"template": "python-cli", "project_dir": str(tmp_path)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["template"] == "python-cli"
        assert len(data["files_created"]) > 0

    def test_conflict_without_force_returns_409(self, client: TestClient, tmp_path: Path):
        # Create files first
        client.post("/api/init", json={"template": "python-cli", "project_dir": str(tmp_path)})
        # Try again without force
        resp = client.post("/api/init", json={"template": "python-cli", "project_dir": str(tmp_path)})
        assert resp.status_code == 409

    def test_force_overwrites(self, client: TestClient, tmp_path: Path):
        client.post("/api/init", json={"template": "python-cli", "project_dir": str(tmp_path)})
        resp = client.post(
            "/api/init",
            json={"template": "python-cli", "project_dir": str(tmp_path), "force": True},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------

class TestProjects:
    @pytest.fixture(autouse=True)
    def patch_projects_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Redirect projects file to a temp location."""
        projects_file = tmp_path / "projects.json"
        monkeypatch.setattr("orchestrator.server._PROJECTS_FILE", projects_file)

    def test_list_empty_initially(self, client: TestClient):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_project(self, client: TestClient, tmp_path: Path):
        resp = client.post("/api/projects", json={"name": "My App", "path": str(tmp_path)})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My App"
        assert "id" in data

    def test_create_then_list(self, client: TestClient, tmp_path: Path):
        client.post("/api/projects", json={"name": "Alpha", "path": str(tmp_path)})
        client.post("/api/projects", json={"name": "Beta", "path": str(tmp_path)})
        resp = client.get("/api/projects")
        names = [p["name"] for p in resp.json()]
        assert "Alpha" in names
        assert "Beta" in names

    def test_delete_project(self, client: TestClient, tmp_path: Path):
        create_resp = client.post("/api/projects", json={"name": "ToDelete", "path": str(tmp_path)})
        project_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/projects/{project_id}")
        assert del_resp.status_code == 204

        projects = client.get("/api/projects").json()
        assert not any(p["id"] == project_id for p in projects)

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        resp = client.delete("/api/projects/does-not-exist")
        assert resp.status_code == 404

    def test_path_is_resolved_to_absolute(self, client: TestClient, tmp_path: Path):
        resp = client.post("/api/projects", json={"name": "X", "path": str(tmp_path)})
        assert Path(resp.json()["path"]).is_absolute()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_empty_log_dir_returns_empty_list(self, client: TestClient, tmp_path: Path):
        resp = client.get(f"/api/history?log_dir={tmp_path / 'nonexistent'}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_entries_from_logs(self, client: TestClient, tmp_path: Path):
        from orchestrator.models import CycleRecord, CycleStatus
        import orchestrator.logger as log_store
        record = _make_record()
        log_store.save(record, "diff here", tmp_path)

        resp = client.get(f"/api/history?log_dir={tmp_path}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["task"] == "test task"

    def test_limit_parameter(self, client: TestClient, tmp_path: Path):
        import orchestrator.logger as log_store
        for i in range(5):
            r = CycleRecord(task=f"task {i}", status=CycleStatus.APPROVED, plan=_make_plan())
            log_store.save(r, "", tmp_path)

        resp = client.get(f"/api/history?log_dir={tmp_path}&limit=3")
        assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_empty_log_dir_returns_total_zero(self, client: TestClient, tmp_path: Path):
        resp = client.get(f"/api/metrics?log_dir={tmp_path / 'empty'}")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_with_approved_run(self, client: TestClient, tmp_path: Path):
        import orchestrator.logger as log_store
        record = _make_record(CycleStatus.APPROVED)
        log_store.save(record, "", tmp_path)

        resp = client.get(f"/api/metrics?log_dir={tmp_path}")
        data = resp.json()
        assert data["total"] == 1
        assert data["approved"] == 1
        assert data["escalated"] == 0
        assert data["approval_rate"] == 1.0


class TestComputeMetrics:
    def test_empty_returns_total_zero(self, tmp_path: Path):
        result = _compute_metrics(str(tmp_path / "empty"))
        assert result == {"total": 0}

    def test_mixed_statuses(self, tmp_path: Path):
        import orchestrator.logger as log_store
        for status in [CycleStatus.APPROVED, CycleStatus.APPROVED, CycleStatus.ESCALATED]:
            r = CycleRecord(task="t", status=status, plan=_make_plan())
            log_store.save(r, "", tmp_path)

        result = _compute_metrics(str(tmp_path))
        assert result["total"] == 3
        assert result["approved"] == 2
        assert result["escalated"] == 1
        assert result["approval_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_recent_capped_at_five(self, tmp_path: Path):
        import orchestrator.logger as log_store
        for i in range(7):
            r = CycleRecord(task=f"t{i}", status=CycleStatus.APPROVED, plan=_make_plan())
            log_store.save(r, "", tmp_path)

        result = _compute_metrics(str(tmp_path))
        assert len(result["recent"]) == 5


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------

class TestStartRun:
    @patch("orchestrator.server._run_cycle_bg", new_callable=AsyncMock)
    def test_returns_run_id_immediately(self, mock_bg, client: TestClient):
        # Prevent real background task
        mock_bg.return_value = None

        resp = client.post("/api/run", json={"task": "add tests", "project_dir": "."})
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"

    @patch("orchestrator.server._run_cycle_bg", new_callable=AsyncMock)
    def test_run_is_registered_in_active_runs(self, mock_bg, client: TestClient):
        mock_bg.return_value = None

        resp = client.post("/api/run", json={"task": "my task", "project_dir": "."})
        run_id = resp.json()["run_id"]
        assert run_id in _active_runs
        assert _active_runs[run_id].task == "my task"


class TestGetRun:
    def test_unknown_run_returns_404(self, client: TestClient):
        resp = client.get("/api/run/nonexistent-id")
        assert resp.status_code == 404

    def test_running_state_has_no_record(self, client: TestClient):
        state = RunState(run_id="r1", task="t", project_dir=".")
        _active_runs["r1"] = state

        resp = client.get("/api/run/r1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "record" not in data

    def test_completed_state_has_record(self, client: TestClient):
        state = RunState(run_id="r2", task="t", project_dir=".", status="approved")
        state.record = _make_record()
        state.diff = "diff content"
        _active_runs["r2"] = state

        resp = client.get("/api/run/r2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert "record" in data
        assert data["diff"] == "diff content"


class TestCancelRun:
    def test_cancel_running_sets_cancelled(self, client: TestClient):
        state = RunState(run_id="r3", task="t", project_dir=".")
        state.bg_task = None  # no real task
        _active_runs["r3"] = state

        resp = client.post("/api/cancel/r3")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        assert _active_runs["r3"].status == "cancelled"

    def test_cancel_already_done_returns_current_status(self, client: TestClient):
        state = RunState(run_id="r4", task="t", project_dir=".", status="approved")
        _active_runs["r4"] = state

        resp = client.post("/api/cancel/r4")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_cancel_nonexistent_returns_404(self, client: TestClient):
        resp = client.post("/api/cancel/nope")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Batch endpoints
# ---------------------------------------------------------------------------

class TestStartBatch:
    @patch("orchestrator.server._run_batch_bg", new_callable=AsyncMock)
    def test_returns_batch_id(self, mock_bg, client: TestClient):
        mock_bg.return_value = None

        resp = client.post("/api/batch", json={"tasks": ["task A", "task B"], "project_dir": "."})
        assert resp.status_code == 202
        data = resp.json()
        assert "batch_id" in data
        assert data["task_count"] == 2

    @patch("orchestrator.server._run_batch_bg", new_callable=AsyncMock)
    def test_creates_child_run_states(self, mock_bg, client: TestClient):
        mock_bg.return_value = None

        resp = client.post("/api/batch", json={"tasks": ["A", "B", "C"], "project_dir": "."})
        batch_id = resp.json()["batch_id"]

        child_ids = [k for k in _active_runs if k.startswith(f"{batch_id}:")]
        assert len(child_ids) == 3

    def test_empty_tasks_returns_422(self, client: TestClient):
        resp = client.post("/api/batch", json={"tasks": [], "project_dir": "."})
        assert resp.status_code == 422


class TestGetBatch:
    def test_unknown_batch_returns_404(self, client: TestClient):
        resp = client.get("/api/batch/nonexistent")
        assert resp.status_code == 404

    @patch("orchestrator.server._run_batch_bg", new_callable=AsyncMock)
    def test_lists_task_states(self, mock_bg, client: TestClient):
        mock_bg.return_value = None

        post_resp = client.post("/api/batch", json={"tasks": ["A", "B"], "project_dir": "."})
        batch_id = post_resp.json()["batch_id"]

        resp = client.get(f"/api/batch/{batch_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["batch_id"] == batch_id
        assert data["task_count"] == 2
        assert len(data["tasks"]) == 2


# ---------------------------------------------------------------------------
# RunState helper tests
# ---------------------------------------------------------------------------

class TestRunState:
    def test_default_status_is_running(self):
        state = RunState(run_id="x", task="t", project_dir=".")
        assert state.status == "running"

    def test_event_bus_is_created_automatically(self):
        state = RunState(run_id="x", task="t", project_dir=".")
        assert state.event_bus is not None
        assert state.event_bus.run_id  # has a non-empty run_id

    def test_two_states_have_different_event_buses(self):
        a = RunState(run_id="a", task="t", project_dir=".")
        b = RunState(run_id="b", task="t", project_dir=".")
        assert a.event_bus is not b.event_bus

    def test_event_bus_run_id_matches_run_state(self):
        state = RunState(run_id="my-run-42", task="t", project_dir=".")
        assert state.event_bus.run_id == "my-run-42"

    def test_event_history_starts_empty(self):
        state = RunState(run_id="x", task="t", project_dir=".")
        assert state.event_history == []

    def test_client_queues_starts_empty(self):
        state = RunState(run_id="x", task="t", project_dir=".")
        assert state._client_queues == []


# ---------------------------------------------------------------------------
# RunState event capture (async — emitting via EventBus)
# ---------------------------------------------------------------------------

class TestRunStateCapture:
    async def test_emitted_event_appended_to_history(self):
        state = RunState(run_id="cap-1", task="t", project_dir=".")
        await state.event_bus.emit(EventType.PLAN_STARTED, {"task": "t"})
        assert len(state.event_history) == 1
        assert state.event_history[0]["type"] == "plan_started"
        assert state.event_history[0]["run_id"] == "cap-1"

    async def test_multiple_events_ordered_in_history(self):
        state = RunState(run_id="cap-2", task="t", project_dir=".")
        await state.event_bus.emit(EventType.PLAN_STARTED, {"task": "t"})
        await state.event_bus.emit(EventType.PLAN_COMPLETED, {"task": "t", "plan": {}})
        await state.event_bus.emit(EventType.EXECUTE_STARTED, {"attempt": 1, "max_attempts": 3})
        assert [e["type"] for e in state.event_history] == [
            "plan_started", "plan_completed", "execute_started"
        ]

    async def test_event_forwarded_to_client_queue(self):
        state = RunState(run_id="cap-3", task="t", project_dir=".")
        q: asyncio.Queue = asyncio.Queue()
        state._client_queues.append(q)

        await state.event_bus.emit(EventType.REVIEW_STARTED, {"attempt": 1})

        assert not q.empty()
        item = q.get_nowait()
        assert item["type"] == "review_started"

    async def test_event_forwarded_to_multiple_queues(self):
        state = RunState(run_id="cap-4", task="t", project_dir=".")
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        state._client_queues.extend([q1, q2])

        await state.event_bus.emit(EventType.PLAN_STARTED, {"task": "t"})

        assert q1.get_nowait()["type"] == "plan_started"
        assert q2.get_nowait()["type"] == "plan_started"

    async def test_terminal_event_sends_sentinel_to_queue(self):
        state = RunState(run_id="cap-5", task="t", project_dir=".")
        q: asyncio.Queue = asyncio.Queue()
        state._client_queues.append(q)

        await state.event_bus.emit(EventType.CYCLE_APPROVED, {"task": "t", "attempt": 1})

        # First item: the event itself
        item = q.get_nowait()
        assert item["type"] == "cycle_approved"
        # Second item: sentinel None
        sentinel = q.get_nowait()
        assert sentinel is None

    async def test_escalated_also_sends_sentinel(self):
        state = RunState(run_id="cap-6", task="t", project_dir=".")
        q: asyncio.Queue = asyncio.Queue()
        state._client_queues.append(q)

        await state.event_bus.emit(EventType.CYCLE_ESCALATED, {"task": "t", "reason": "x"})

        q.get_nowait()           # the event
        assert q.get_nowait() is None  # sentinel


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

class TestWebSocketEndpoint:
    def test_unknown_run_sends_error_json(self, client: TestClient):
        """Connecting to a non-existent run_id gets an error message then close."""
        # _wait_for_run has a 5 s timeout; patch it to return None immediately.
        import orchestrator.server as srv
        import asyncio

        original = srv._wait_for_run

        async def fast_none(run_id, **_kw):
            return None

        srv._wait_for_run = fast_none
        try:
            with client.websocket_connect("/ws/run/no-such-id") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "not found" in msg["detail"]
        except WebSocketDisconnect:
            pass  # server closed after error — that's expected
        finally:
            srv._wait_for_run = original

    def test_history_replayed_to_late_client(self, client: TestClient):
        """Events emitted before client connects are replayed from history."""
        state = RunState(run_id="ws-hist-1", task="t", project_dir=".", status="approved")
        state.event_history.append({
            "type": "plan_started", "run_id": "ws-hist-1",
            "timestamp": "2026-01-01T00:00:00", "data": {"task": "t"},
        })
        _active_runs["ws-hist-1"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/run/ws-hist-1") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        assert any(m["type"] == "plan_started" for m in received)

    def test_finished_run_sends_done_and_closes(self, client: TestClient):
        """A completed run streams history then sends {'type': 'done'} and closes."""
        state = RunState(run_id="ws-done-1", task="t", project_dir=".", status="approved")
        state.event_history.append({
            "type": "cycle_approved", "run_id": "ws-done-1",
            "timestamp": "2026-01-01T00:00:00", "data": {},
        })
        _active_runs["ws-done-1"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/run/ws-done-1") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        types = [m["type"] for m in received]
        assert "cycle_approved" in types
        assert "done" in types

    def test_empty_history_finished_run_just_sends_done(self, client: TestClient):
        """A finished run with no events still sends {'type': 'done'}."""
        state = RunState(run_id="ws-done-2", task="t", project_dir=".", status="cancelled")
        _active_runs["ws-done-2"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/run/ws-done-2") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        assert received[-1]["type"] == "done"

    def test_client_queue_registered_and_cleaned_up(self, client: TestClient):
        """The per-client queue is added on connect and removed on disconnect."""
        state = RunState(run_id="ws-q-1", task="t", project_dir=".", status="approved")
        _active_runs["ws-q-1"] = state

        assert len(state._client_queues) == 0
        with client.websocket_connect("/ws/run/ws-q-1") as ws:
            try:
                while True:
                    ws.receive_json()
            except WebSocketDisconnect:
                pass
        # After disconnect, the queue must be cleaned up.
        assert len(state._client_queues) == 0


# ---------------------------------------------------------------------------
# Pause / Resume / Edit-plan endpoints
# ---------------------------------------------------------------------------

class TestPauseRun:
    def test_pause_running_sets_paused(self, client: TestClient):
        state = RunState(run_id="p1", task="t", project_dir=".", status="running")
        _active_runs["p1"] = state

        resp = client.post("/api/pause/p1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
        assert _active_runs["p1"].status == "paused"
        assert _active_runs["p1"].pause_controller.is_paused

    def test_pause_nonexistent_returns_404(self, client: TestClient):
        resp = client.post("/api/pause/nope")
        assert resp.status_code == 404

    def test_pause_already_done_returns_current_status(self, client: TestClient):
        state = RunState(run_id="p2", task="t", project_dir=".", status="approved")
        _active_runs["p2"] = state

        resp = client.post("/api/pause/p2")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_pause_emits_cycle_paused_event(self, client: TestClient):
        state = RunState(run_id="p3", task="t", project_dir=".", status="running")
        _active_runs["p3"] = state

        client.post("/api/pause/p3")

        assert any(e["type"] == "cycle_paused" for e in state.event_history)


class TestResumeRun:
    def test_resume_paused_sets_running(self, client: TestClient):
        state = RunState(run_id="r1", task="t", project_dir=".", status="paused")
        state.pause_controller.pause()
        _active_runs["r1"] = state

        resp = client.post("/api/resume/r1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert _active_runs["r1"].status == "running"
        assert not _active_runs["r1"].pause_controller.is_paused

    def test_resume_nonexistent_returns_404(self, client: TestClient):
        resp = client.post("/api/resume/nope")
        assert resp.status_code == 404

    def test_resume_not_paused_returns_current_status(self, client: TestClient):
        state = RunState(run_id="r2", task="t", project_dir=".", status="running")
        _active_runs["r2"] = state

        resp = client.post("/api/resume/r2")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_resume_emits_cycle_resumed_event(self, client: TestClient):
        state = RunState(run_id="r3", task="t", project_dir=".", status="paused")
        state.pause_controller.pause()
        _active_runs["r3"] = state

        client.post("/api/resume/r3")

        assert any(e["type"] == "cycle_resumed" for e in state.event_history)


class TestEditPlan:
    def _valid_plan_dict(self) -> dict:
        return {
            "description": "Updated plan",
            "files_to_create": ["new.py"],
            "files_to_modify": [],
            "steps": ["step 1"],
            "acceptance_criteria": ["it works"],
            "estimated_complexity": "low",
        }

    def test_edit_plan_on_paused_run_resumes(self, client: TestClient):
        state = RunState(run_id="ep1", task="t", project_dir=".", status="paused")
        state.pause_controller.pause()
        _active_runs["ep1"] = state

        resp = client.post("/api/edit-plan/ep1", json={"plan": self._valid_plan_dict()})
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert _active_runs["ep1"].status == "running"

    def test_edit_plan_provides_plan_to_controller(self, client: TestClient):
        state = RunState(run_id="ep2", task="t", project_dir=".", status="paused")
        state.pause_controller.pause()
        _active_runs["ep2"] = state

        client.post("/api/edit-plan/ep2", json={"plan": self._valid_plan_dict()})

        # The pause_controller should have an edited_plan ready
        assert state.pause_controller._edited_plan is not None
        assert state.pause_controller._edited_plan.description == "Updated plan"

    def test_edit_plan_on_running_returns_409(self, client: TestClient):
        state = RunState(run_id="ep3", task="t", project_dir=".", status="running")
        _active_runs["ep3"] = state

        resp = client.post("/api/edit-plan/ep3", json={"plan": self._valid_plan_dict()})
        assert resp.status_code == 409

    def test_edit_plan_nonexistent_returns_404(self, client: TestClient):
        resp = client.post("/api/edit-plan/nope", json={"plan": self._valid_plan_dict()})
        assert resp.status_code == 404

    def test_edit_plan_invalid_payload_returns_422(self, client: TestClient):
        state = RunState(run_id="ep4", task="t", project_dir=".", status="paused")
        state.pause_controller.pause()
        _active_runs["ep4"] = state

        resp = client.post("/api/edit-plan/ep4", json={"plan": {"bad": "data"}})
        assert resp.status_code == 422

    def test_edit_plan_emits_cycle_resumed_with_plan_edited(self, client: TestClient):
        state = RunState(run_id="ep5", task="t", project_dir=".", status="paused")
        state.pause_controller.pause()
        _active_runs["ep5"] = state

        client.post("/api/edit-plan/ep5", json={"plan": self._valid_plan_dict()})

        resumed_events = [e for e in state.event_history if e["type"] == "cycle_resumed"]
        assert resumed_events
        assert resumed_events[0]["data"].get("plan_edited") is True


class TestRunStateHasPauseController:
    def test_pause_controller_created_automatically(self):
        state = RunState(run_id="x", task="t", project_dir=".")
        assert state.pause_controller is not None
        assert not state.pause_controller.is_paused

    def test_two_states_have_different_pause_controllers(self):
        a = RunState(run_id="a", task="t", project_dir=".")
        b = RunState(run_id="b", task="t", project_dir=".")
        assert a.pause_controller is not b.pause_controller


# ---------------------------------------------------------------------------
# mount_frontend
# ---------------------------------------------------------------------------

class TestMountFrontend:
    """Tests for the mount_frontend helper."""

    @pytest.fixture(autouse=True)
    def _unmount(self):
        """Remove the 'frontend' mount from the app after each test."""
        yield
        # FastAPI stores mounts in app.router.routes; remove any added by tests.
        app.router.routes[:] = [
            r for r in app.router.routes
            if getattr(r, "name", None) != "frontend"
        ]

    def test_mount_serves_index_html(self, tmp_path: Path):
        from orchestrator.server import mount_frontend

        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>Dashboard</html>")

        mount_frontend(dist)

        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_api_health_still_reachable_after_mount(self, tmp_path: Path):
        from orchestrator.server import mount_frontend

        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>ok</html>")

        mount_frontend(dist)

        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_mount_missing_dist_raises(self, tmp_path: Path):
        from orchestrator.server import mount_frontend

        with pytest.raises(Exception):
            mount_frontend(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# PlanRunState dataclass
# ---------------------------------------------------------------------------

def _make_plan_run_state(state_id: str = "pr-1", status: str = "running") -> PlanRunState:
    return PlanRunState(
        id=state_id,
        project_id="proj",
        project_path=".",
        plan_path="PLANO.md",
        status=status,
    )


class TestPlanRunState:
    def test_default_status_is_running(self):
        state = _make_plan_run_state()
        assert state.status == "running"

    def test_pause_event_starts_set(self):
        state = _make_plan_run_state()
        assert state.pause_event.is_set()

    def test_event_bus_run_id_matches_state_id(self):
        state = _make_plan_run_state("my-plan-42")
        assert state.event_bus.run_id == "my-plan-42"

    def test_event_history_starts_empty(self):
        state = _make_plan_run_state()
        assert state.event_history == []

    def test_client_queues_starts_empty(self):
        state = _make_plan_run_state()
        assert state._client_queues == []

    def test_two_states_have_different_event_buses(self):
        a = _make_plan_run_state("a")
        b = _make_plan_run_state("b")
        assert a.event_bus is not b.event_bus


class TestPlanRunStateCapture:
    """Tests for PlanRunState._on_plan_event (emitted via EventBus)."""

    async def test_event_appended_to_history(self):
        state = _make_plan_run_state("cap-pr-1")
        await state.event_bus.emit(EventType.PLAN_LOADED, {"name": "MyPlan", "total_tasks": 5, "done_tasks": 0})
        assert len(state.event_history) == 1
        assert state.event_history[0]["type"] == "plan_loaded"

    async def test_plan_loaded_updates_plan_name(self):
        state = _make_plan_run_state("cap-pr-2")
        await state.event_bus.emit(EventType.PLAN_LOADED, {"name": "FinanceAI", "total_tasks": 10, "done_tasks": 0})
        assert state.plan_name == "FinanceAI"

    async def test_task_started_updates_current_task_id(self):
        state = _make_plan_run_state("cap-pr-3")
        await state.event_bus.emit(EventType.TASK_STARTED, {"task_id": "1.1.1", "description": "...", "phase_id": "1", "subphase_id": "1.1", "attempt": 1})
        assert state.current_task_id == "1.1.1"

    async def test_task_done_increments_counter_and_clears_task(self):
        state = _make_plan_run_state("cap-pr-4")
        await state.event_bus.emit(EventType.TASK_STARTED, {"task_id": "1.1.1", "description": "...", "phase_id": "1", "subphase_id": "1.1", "attempt": 1})
        await state.event_bus.emit(EventType.TASK_DONE, {"task_id": "1.1.1", "commit_hash": "abc1234", "score": 9, "duration_s": 12.5})
        assert state.tasks_done == 1
        assert state.current_task_id is None

    async def test_task_escalated_increments_counter(self):
        state = _make_plan_run_state("cap-pr-5")
        await state.event_bus.emit(EventType.TASK_ESCALATED, {"task_id": "1.1.2", "reason": "max retries"})
        assert state.tasks_escalated == 1

    async def test_task_skipped_increments_counter(self):
        state = _make_plan_run_state("cap-pr-6")
        await state.event_bus.emit(EventType.TASK_SKIPPED, {"task_id": "1.1.3"})
        assert state.tasks_skipped == 1

    async def test_plan_paused_updates_status_and_reason(self):
        state = _make_plan_run_state("cap-pr-7")
        await state.event_bus.emit(EventType.PLAN_PAUSED, {"reason": "subphase", "context": {"done": 3}})
        assert state.status == "paused"
        assert state.pause_reason == "subphase"
        assert state.pause_context == {"done": 3}

    async def test_plan_resumed_resets_status_and_reason(self):
        state = _make_plan_run_state("cap-pr-8")
        await state.event_bus.emit(EventType.PLAN_PAUSED, {"reason": "phase", "context": {}})
        await state.event_bus.emit(EventType.PLAN_RESUMED, {})
        assert state.status == "running"
        assert state.pause_reason is None
        assert state.pause_context is None

    async def test_plan_complete_sends_sentinel_to_queues(self):
        state = _make_plan_run_state("cap-pr-9")
        q: asyncio.Queue = asyncio.Queue()
        state._client_queues.append(q)

        await state.event_bus.emit(EventType.PLAN_COMPLETE, {"total": 5, "done": 5, "escalated": 0, "skipped": 0, "duration_s": 120.0})

        # First item: the event dict
        item = q.get_nowait()
        assert item["type"] == "plan_complete"
        # Second item: sentinel None
        assert q.get_nowait() is None

    async def test_plan_aborted_sends_sentinel_to_queues(self):
        state = _make_plan_run_state("cap-pr-10")
        q: asyncio.Queue = asyncio.Queue()
        state._client_queues.append(q)

        await state.event_bus.emit(EventType.PLAN_ABORTED, {"reason": "user cancelled"})

        item = q.get_nowait()
        assert item["type"] == "plan_aborted"
        assert q.get_nowait() is None

    async def test_event_forwarded_to_multiple_queues(self):
        state = _make_plan_run_state("cap-pr-11")
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        state._client_queues.extend([q1, q2])

        await state.event_bus.emit(EventType.TASK_STARTED, {"task_id": "1.1.1", "description": "...", "phase_id": "1", "subphase_id": "1.1", "attempt": 1})

        assert q1.get_nowait()["type"] == "task_started"
        assert q2.get_nowait()["type"] == "task_started"


# ---------------------------------------------------------------------------
# WebSocket /ws/plan/{plan_run_id}
# ---------------------------------------------------------------------------

class TestWebSocketPlanEndpoint:
    def test_unknown_plan_run_sends_error_json(self, client: TestClient):
        """Connecting to a non-existent plan_run_id gets an error message then close."""
        import orchestrator.server as srv

        original = srv._wait_for_plan_run

        async def fast_none(plan_run_id: str, **_kw: Any) -> None:
            return None

        srv._wait_for_plan_run = fast_none
        try:
            with client.websocket_connect("/ws/plan/no-such-id") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "not found" in msg["detail"]
        except WebSocketDisconnect:
            pass
        finally:
            srv._wait_for_plan_run = original

    def test_history_replayed_to_late_client(self, client: TestClient):
        """Events emitted before client connects are replayed from history."""
        state = _make_plan_run_state("ws-pr-hist-1", status="complete")
        state.event_history.append({
            "type": "task_done",
            "run_id": "ws-pr-hist-1",
            "timestamp": "2026-01-01T00:00:00",
            "data": {"task_id": "1.1.1", "commit_hash": "abc1234", "score": 9, "duration_s": 5.0},
        })
        _active_plan_runs["ws-pr-hist-1"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/plan/ws-pr-hist-1") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        assert any(m["type"] == "task_done" for m in received)

    def test_finished_run_sends_done_and_closes(self, client: TestClient):
        """A completed plan run streams history then sends {'type': 'done'} and closes."""
        state = _make_plan_run_state("ws-pr-done-1", status="complete")
        state.event_history.append({
            "type": "plan_complete",
            "run_id": "ws-pr-done-1",
            "timestamp": "2026-01-01T00:00:00",
            "data": {"total": 5, "done": 5, "escalated": 0, "skipped": 0, "duration_s": 60.0},
        })
        _active_plan_runs["ws-pr-done-1"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/plan/ws-pr-done-1") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        types = [m["type"] for m in received]
        assert "plan_complete" in types
        assert "done" in types

    def test_aborted_run_sends_done_and_closes(self, client: TestClient):
        """An aborted plan run sends {'type': 'done'} with plan_run_id."""
        state = _make_plan_run_state("ws-pr-done-2", status="aborted")
        state.event_history.append({
            "type": "plan_aborted",
            "run_id": "ws-pr-done-2",
            "timestamp": "2026-01-01T00:00:00",
            "data": {"reason": "user cancelled"},
        })
        _active_plan_runs["ws-pr-done-2"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/plan/ws-pr-done-2") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        types = [m["type"] for m in received]
        assert "plan_aborted" in types
        assert "done" in types

    def test_empty_history_finished_run_just_sends_done(self, client: TestClient):
        """A finished run with no events still sends {'type': 'done'}."""
        state = _make_plan_run_state("ws-pr-done-3", status="complete")
        _active_plan_runs["ws-pr-done-3"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/plan/ws-pr-done-3") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        assert received[-1]["type"] == "done"
        assert received[-1]["plan_run_id"] == "ws-pr-done-3"

    def test_client_queue_registered_and_cleaned_up(self, client: TestClient):
        """The per-client queue is added on connect and removed on disconnect."""
        state = _make_plan_run_state("ws-pr-q-1", status="complete")
        _active_plan_runs["ws-pr-q-1"] = state

        assert len(state._client_queues) == 0
        with client.websocket_connect("/ws/plan/ws-pr-q-1") as ws:
            try:
                while True:
                    ws.receive_json()
            except WebSocketDisconnect:
                pass
        assert len(state._client_queues) == 0

    def test_done_message_carries_plan_run_id(self, client: TestClient):
        """The 'done' message includes the plan_run_id for client correlation."""
        state = _make_plan_run_state("ws-pr-done-4", status="aborted")
        _active_plan_runs["ws-pr-done-4"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/plan/ws-pr-done-4") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        done_msg = next(m for m in received if m["type"] == "done")
        assert done_msg["plan_run_id"] == "ws-pr-done-4"

    def test_multiple_history_events_replayed_in_order(self, client: TestClient):
        """Multiple history events are replayed in insertion order."""
        state = _make_plan_run_state("ws-pr-hist-2", status="complete")
        for evt_type in ("plan_loaded", "task_started", "task_done", "plan_complete"):
            state.event_history.append({
                "type": evt_type,
                "run_id": "ws-pr-hist-2",
                "timestamp": "2026-01-01T00:00:00",
                "data": {},
            })
        _active_plan_runs["ws-pr-hist-2"] = state

        received: list[dict] = []
        with client.websocket_connect("/ws/plan/ws-pr-hist-2") as ws:
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

        # Strip the trailing 'done' message and verify order
        payload = [m for m in received if m["type"] != "done"]
        assert [m["type"] for m in payload] == [
            "plan_loaded", "task_started", "task_done", "plan_complete"
        ]
