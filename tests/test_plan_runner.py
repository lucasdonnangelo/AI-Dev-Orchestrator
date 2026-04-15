"""Unit tests for orchestrator/plan_runner.py."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models import CycleRecord, CycleStatus, DecisionResult, ReviewResult
from orchestrator.plan import (
    Phase,
    PlanTask,
    PlanTaskStatus,
    ProjectPlan,
    SubPhase,
    parse_plan,
    write_plan,
)
from orchestrator.plan_runner import (
    RunPlanOptions,
    RunPlanResult,
    TaskResult,
    _StopExecution,
    _build_phase_context,
    _collect_entries,
    _last_task_in_phase,
    _last_task_in_subphase,
    _maybe_pause_boundaries,
    _next_phase,
    _next_subphase,
    run_plan,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

PLANO_MD = textwrap.dedent("""\
    # Test Project

    ## Fase 1 — Setup

    ### 1.1 Structure

    - [ ] 1.1.1 Create folders
    - [ ] 1.1.2 Create pyproject.toml

    ### 1.2 Config

    - [ ] 1.2.1 Configure env vars
    - [ ] 1.2.2 Configure logging

    ## Fase 2 — Implementation

    ### 2.1 Core

    - [ ] 2.1.1 Create models
    - [ ] 2.1.2 Create services
""")


def _make_plan() -> ProjectPlan:
    from orchestrator.plan import parse_plan_text
    return parse_plan_text(PLANO_MD)


def _make_cycle_record(approved: bool = True) -> CycleRecord:
    status = CycleStatus.APPROVED if approved else CycleStatus.ESCALATED
    record = CycleRecord(task="test task", status=status)
    record.review = MagicMock(spec=ReviewResult)
    record.review.approved = approved
    record.review.score = 9 if approved else 3
    record.review.issues = []
    record.review.suggestions = []
    return record


def _make_decision(approved: bool = True) -> DecisionResult:
    return DecisionResult(
        approved=approved,
        reasoning="looks good" if approved else "diverges from plan",
        inconsistencies=[] if approved else ["issue"],
    )


def _make_config(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.project_dir = str(tmp_path)
    cfg.log_dir = str(tmp_path / "logs")
    cfg.git_conventional_commits = True
    cfg.max_retries = 3
    return cfg


# ---------------------------------------------------------------------------
# RunPlanResult
# ---------------------------------------------------------------------------


class TestRunPlanResult:
    def test_success_true_when_done_and_no_escalated(self) -> None:
        r = RunPlanResult(plan_name="P", tasks_done=3, tasks_escalated=0)
        assert r.success is True

    def test_success_false_when_escalated(self) -> None:
        r = RunPlanResult(plan_name="P", tasks_done=2, tasks_escalated=1)
        assert r.success is False

    def test_success_false_when_nothing_done(self) -> None:
        r = RunPlanResult(plan_name="P", tasks_done=0, tasks_escalated=0)
        assert r.success is False

    def test_total_processed(self) -> None:
        r = RunPlanResult(plan_name="P", tasks_done=1, tasks_escalated=1, tasks_skipped=2, tasks_dry_run=3)
        assert r.total_processed == 7


# ---------------------------------------------------------------------------
# _collect_entries
# ---------------------------------------------------------------------------


class TestCollectEntries:
    def test_no_filter_returns_all(self) -> None:
        plan = _make_plan()
        opts = RunPlanOptions()
        entries = _collect_entries(plan, opts)
        assert len(entries) == 6  # 2+2 in phase 1, 2 in phase 2

    def test_phase_filter(self) -> None:
        plan = _make_plan()
        opts = RunPlanOptions(phase="1")
        entries = _collect_entries(plan, opts)
        assert all(ph.id == "1" for ph, _, _ in entries)
        assert len(entries) == 4

    def test_subtask_filter(self) -> None:
        plan = _make_plan()
        opts = RunPlanOptions(subtask="1.1")
        entries = _collect_entries(plan, opts)
        assert all(sp.id == "1.1" for _, sp, _ in entries)
        assert len(entries) == 2

    def test_phase_and_subtask_filter(self) -> None:
        plan = _make_plan()
        opts = RunPlanOptions(phase="2", subtask="2.1")
        entries = _collect_entries(plan, opts)
        assert len(entries) == 2
        assert entries[0][2].id == "2.1.1"

    def test_nonexistent_phase_returns_empty(self) -> None:
        plan = _make_plan()
        opts = RunPlanOptions(phase="99")
        assert _collect_entries(plan, opts) == []


# ---------------------------------------------------------------------------
# _last_task_in_subphase / _last_task_in_phase
# ---------------------------------------------------------------------------


class TestLastTaskHelpers:
    def test_last_in_subphase(self) -> None:
        plan = _make_plan()
        entries = _collect_entries(plan, RunPlanOptions())
        assert _last_task_in_subphase(entries, "1.1") == "1.1.2"
        assert _last_task_in_subphase(entries, "1.2") == "1.2.2"
        assert _last_task_in_subphase(entries, "2.1") == "2.1.2"

    def test_last_in_phase(self) -> None:
        plan = _make_plan()
        entries = _collect_entries(plan, RunPlanOptions())
        assert _last_task_in_phase(entries, "1") == "1.2.2"
        assert _last_task_in_phase(entries, "2") == "2.1.2"

    def test_nonexistent_returns_none(self) -> None:
        plan = _make_plan()
        entries = _collect_entries(plan, RunPlanOptions())
        assert _last_task_in_subphase(entries, "9.9") is None
        assert _last_task_in_phase(entries, "9") is None


# ---------------------------------------------------------------------------
# _next_phase / _next_subphase
# ---------------------------------------------------------------------------


class TestNextHelpers:
    def test_next_phase(self) -> None:
        plan = _make_plan()
        nxt = _next_phase(plan, "1")
        assert nxt is not None
        assert nxt.id == "2"

    def test_next_phase_last_returns_none(self) -> None:
        plan = _make_plan()
        assert _next_phase(plan, "2") is None

    def test_next_subphase(self) -> None:
        plan = _make_plan()
        nxt = _next_subphase(plan, "1.1")
        assert nxt is not None
        assert nxt.id == "1.2"

    def test_next_subphase_last_returns_none(self) -> None:
        plan = _make_plan()
        assert _next_subphase(plan, "2.1") is None


# ---------------------------------------------------------------------------
# _build_phase_context
# ---------------------------------------------------------------------------


class TestBuildPhaseContext:
    def test_empty_when_no_done_tasks(self) -> None:
        plan = _make_plan()
        task = plan.get_task("1.1.2")
        assert task is not None
        ctx = _build_phase_context(plan, task)
        assert ctx == ""

    def test_includes_done_tasks_from_same_phase(self) -> None:
        plan = _make_plan()
        # Mark 1.1.1 as done
        t111 = plan.get_task("1.1.1")
        assert t111 is not None
        t111.mark_done(commit_hash="abc1234")

        # Build context for 1.1.2 (same subfase, same phase)
        t112 = plan.get_task("1.1.2")
        assert t112 is not None
        ctx = _build_phase_context(plan, t112)

        assert "1.1.1" in ctx
        assert "Create folders" in ctx
        assert "abc1234" in ctx
        assert "Phase 1" in ctx

    def test_excludes_current_task_from_context(self) -> None:
        plan = _make_plan()
        t111 = plan.get_task("1.1.1")
        assert t111 is not None
        t111.mark_done()

        ctx = _build_phase_context(plan, t111)
        # t111 is the current task — should not appear in its own context
        assert ctx == ""

    def test_excludes_done_tasks_from_other_phases(self) -> None:
        plan = _make_plan()
        # Mark a phase-2 task as done
        t211 = plan.get_task("2.1.1")
        assert t211 is not None
        t211.mark_done()

        # Build context for a phase-1 task
        t112 = plan.get_task("1.1.2")
        assert t112 is not None
        ctx = _build_phase_context(plan, t112)

        # Phase 2 tasks should not appear in Phase 1 context
        assert "2.1.1" not in ctx

    def test_context_includes_done_from_different_subfases_of_same_phase(self) -> None:
        plan = _make_plan()
        # Mark all of subfase 1.1 as done
        for tid in ("1.1.1", "1.1.2"):
            t = plan.get_task(tid)
            assert t is not None
            t.mark_done()

        # Build context for a subfase 1.2 task
        t121 = plan.get_task("1.2.1")
        assert t121 is not None
        ctx = _build_phase_context(plan, t121)

        assert "1.1.1" in ctx
        assert "1.1.2" in ctx


# ---------------------------------------------------------------------------
# run_plan — dry_run mode
# ---------------------------------------------------------------------------


class TestRunPlanDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_without_executing(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(dry_run=True)

        with patch("orchestrator.plan_runner.run_cycle") as mock_cycle:
            result = await run_plan(plano, config, opts)

        mock_cycle.assert_not_called()
        assert result.tasks_dry_run == 6
        assert result.tasks_done == 0
        assert all(r.status == "dry_run" for r in result.results)

    @pytest.mark.asyncio
    async def test_dry_run_with_phase_filter(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(dry_run=True, phase="1")

        with patch("orchestrator.plan_runner.run_cycle"):
            result = await run_plan(plano, config, opts)

        assert result.tasks_dry_run == 4  # only phase 1 tasks


# ---------------------------------------------------------------------------
# run_plan — idempotency (skip done / skipped tasks)
# ---------------------------------------------------------------------------


class TestRunPlanIdempotency:
    @pytest.mark.asyncio
    async def test_already_done_tasks_are_skipped(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")

        plan = parse_plan(plano)
        # Pre-mark all tasks as done
        for task in plan.all_tasks:
            task.mark_done(commit_hash="abc1234")
        write_plan(plan, plano)

        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True)

        with patch("orchestrator.plan_runner.run_cycle") as mock_cycle:
            result = await run_plan(plano, config, opts)

        mock_cycle.assert_not_called()
        assert result.tasks_done == 0
        assert all(r.status == "already_done" for r in result.results)

    @pytest.mark.asyncio
    async def test_skipped_tasks_are_counted(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")

        plan = parse_plan(plano)
        for task in plan.all_tasks:
            task.mark_skipped()
        write_plan(plan, plano)

        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True)

        with patch("orchestrator.plan_runner.run_cycle"):
            result = await run_plan(plano, config, opts)

        assert result.tasks_skipped == 6


# ---------------------------------------------------------------------------
# run_plan — successful execution
# ---------------------------------------------------------------------------


class TestRunPlanSuccess:
    @pytest.mark.asyncio
    async def test_executes_all_pending_tasks(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True)

        record = _make_cycle_record(approved=True)
        decision = _make_decision(approved=True)

        with (
            patch("orchestrator.plan_runner.run_cycle", new_callable=AsyncMock) as mock_cycle,
            patch("orchestrator.plan_runner._commit_task", return_value="abc1234"),
            patch("orchestrator.plan_runner.log_store"),
        ):
            mock_cycle.return_value = (record, "diff content", decision)
            result = await run_plan(plano, config, opts)

        assert result.tasks_done == 6
        assert result.tasks_escalated == 0
        assert mock_cycle.call_count == 6

    @pytest.mark.asyncio
    async def test_plano_md_updated_to_done(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True, phase="1", subtask="1.1")

        record = _make_cycle_record(approved=True)

        with (
            patch("orchestrator.plan_runner.run_cycle", new_callable=AsyncMock) as mock_cycle,
            patch("orchestrator.plan_runner._commit_task", return_value="deadbeef"),
            patch("orchestrator.plan_runner.log_store"),
        ):
            mock_cycle.return_value = (record, "", None)
            await run_plan(plano, config, opts)

        updated_plan = parse_plan(plano)
        t111 = updated_plan.get_task("1.1.1")
        t112 = updated_plan.get_task("1.1.2")
        assert t111 is not None and t111.status == PlanTaskStatus.DONE
        assert t112 is not None and t112.status == PlanTaskStatus.DONE
        # Tasks outside filter remain pending
        t121 = updated_plan.get_task("1.2.1")
        assert t121 is not None and t121.status == PlanTaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_commit_hash_stored_on_task(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True, phase="1", subtask="1.1")

        record = _make_cycle_record(approved=True)

        with (
            patch("orchestrator.plan_runner.run_cycle", new_callable=AsyncMock) as mock_cycle,
            patch("orchestrator.plan_runner._commit_task", return_value="cafebabe"),
            patch("orchestrator.plan_runner.log_store"),
        ):
            mock_cycle.return_value = (record, "", None)
            result = await run_plan(plano, config, opts)

        done_results = [r for r in result.results if r.status == "done"]
        assert all(r.commit_hash == "cafebabe" for r in done_results)


# ---------------------------------------------------------------------------
# run_plan — escalation handling
# ---------------------------------------------------------------------------


class TestRunPlanEscalation:
    @pytest.mark.asyncio
    async def test_escalated_cycle_marks_task_and_continues(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        # yes=True so the runner auto-continues past escalated tasks
        opts = RunPlanOptions(yes=True, auto_continue=True, phase="1", subtask="1.1")

        escalated_record = _make_cycle_record(approved=False)
        approved_record = _make_cycle_record(approved=True)

        call_count = 0

        async def side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (escalated_record, "", None)
            return (approved_record, "", None)

        with (
            patch("orchestrator.plan_runner.run_cycle", side_effect=side_effect),
            patch("orchestrator.plan_runner._commit_task", return_value="abc"),
            patch("orchestrator.plan_runner.log_store"),
        ):
            result = await run_plan(plano, config, opts)

        assert result.tasks_escalated == 1
        assert result.tasks_done == 1

        updated_plan = parse_plan(plano)
        assert updated_plan.get_task("1.1.1").status == PlanTaskStatus.ESCALATED
        assert updated_plan.get_task("1.1.2").status == PlanTaskStatus.DONE

    @pytest.mark.asyncio
    async def test_exception_in_run_cycle_marks_escalated(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True, phase="1", subtask="1.1")

        with (
            patch("orchestrator.plan_runner.run_cycle", new_callable=AsyncMock) as mock_cycle,
            patch("orchestrator.plan_runner.log_store"),
        ):
            mock_cycle.side_effect = RuntimeError("API down")
            result = await run_plan(plano, config, opts)

        assert result.tasks_escalated == 2
        assert all(r.status == "escalated" for r in result.results)

        updated_plan = parse_plan(plano)
        assert updated_plan.get_task("1.1.1").status == PlanTaskStatus.ESCALATED


# ---------------------------------------------------------------------------
# run_plan — accumulated context
# ---------------------------------------------------------------------------


class TestAccumulatedContext:
    @pytest.mark.asyncio
    async def test_phase_context_included_in_second_task(self, tmp_path: Path) -> None:
        """The Planner prompt for task 1.1.2 must include context about task 1.1.1."""
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(yes=True, auto_continue=True, phase="1", subtask="1.1")

        approved_record = _make_cycle_record(approved=True)
        captured_tasks: list[str] = []

        async def capture_task(task: str, cfg, **kwargs):  # noqa: ANN002, ANN003
            captured_tasks.append(task)
            return (approved_record, "", None)

        with (
            patch("orchestrator.plan_runner.run_cycle", side_effect=capture_task),
            patch("orchestrator.plan_runner._commit_task", return_value="abc"),
            patch("orchestrator.plan_runner.log_store"),
        ):
            await run_plan(plano, config, opts)

        assert len(captured_tasks) == 2
        # First task: no prior context
        assert "Context" not in captured_tasks[0]
        # Second task: should have context about the first task
        assert "1.1.1" in captured_tasks[1]
        assert "Context" in captured_tasks[1]


# ---------------------------------------------------------------------------
# run_plan — no tasks match filter
# ---------------------------------------------------------------------------


class TestRunPlanNoTasks:
    @pytest.mark.asyncio
    async def test_empty_result_when_no_match(self, tmp_path: Path) -> None:
        plano = tmp_path / "PLANO.md"
        plano.write_text(PLANO_MD, encoding="utf-8")
        config = _make_config(tmp_path)
        opts = RunPlanOptions(phase="99")

        result = await run_plan(plano, config, opts)

        assert result.total_processed == 0
