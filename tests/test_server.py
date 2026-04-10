"""Unit tests for orchestrator/server.py — REST API endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.models import CycleRecord, CycleStatus, TaskPlan, Complexity
from orchestrator.server import (
    RunState,
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
    """Reset in-memory run store between tests."""
    _active_runs.clear()
    yield
    _active_runs.clear()


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
