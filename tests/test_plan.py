"""Unit tests for orchestrator/plan.py — data models and parser for the hierarchical plan."""

from __future__ import annotations

import textwrap

import pytest

from orchestrator.plan import (
    Phase,
    PlanTask,
    PlanTaskStatus,
    ProjectPlan,
    SubPhase,
    parse_plan,
    parse_plan_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_task(
    id: str = "1.1.1",
    description: str = "Do something",
    status: PlanTaskStatus = PlanTaskStatus.PENDING,
) -> PlanTask:
    return PlanTask(id=id, description=description, status=status)


def make_subphase(id: str = "1.1", name: str = "Setup", tasks: list | None = None) -> SubPhase:
    return SubPhase(
        id=id,
        name=name,
        tasks=tasks if tasks is not None else [make_task("1.1.1"), make_task("1.1.2")],
    )


def make_phase(id: str = "1", name: str = "Fase 1", subphases: list | None = None) -> Phase:
    return Phase(
        id=id,
        name=name,
        subphases=subphases if subphases is not None else [make_subphase()],
    )


def make_plan(phases: list | None = None) -> ProjectPlan:
    return ProjectPlan(
        name="Test Project",
        phases=phases if phases is not None else [make_phase()],
    )


# ---------------------------------------------------------------------------
# PlanTaskStatus
# ---------------------------------------------------------------------------


class TestPlanTaskStatus:
    def test_values(self):
        assert PlanTaskStatus.PENDING.value == "pending"
        assert PlanTaskStatus.RUNNING.value == "running"
        assert PlanTaskStatus.DONE.value == "done"
        assert PlanTaskStatus.ESCALATED.value == "escalated"
        assert PlanTaskStatus.SKIPPED.value == "skipped"

    def test_is_str_enum(self):
        assert isinstance(PlanTaskStatus.DONE, str)


# ---------------------------------------------------------------------------
# PlanTask
# ---------------------------------------------------------------------------


class TestPlanTask:
    def test_defaults(self):
        t = PlanTask(id="1.1.1", description="Do x")
        assert t.status == PlanTaskStatus.PENDING
        assert t.commit_hash is None
        assert t.started_at is None
        assert t.finished_at is None

    def test_is_pending(self):
        t = make_task(status=PlanTaskStatus.PENDING)
        assert t.is_pending is True
        assert t.is_done is False

    def test_is_done(self):
        t = make_task(status=PlanTaskStatus.DONE)
        assert t.is_done is True
        assert t.is_pending is False

    def test_is_terminal_done(self):
        assert make_task(status=PlanTaskStatus.DONE).is_terminal is True

    def test_is_terminal_escalated(self):
        assert make_task(status=PlanTaskStatus.ESCALATED).is_terminal is True

    def test_is_terminal_skipped(self):
        assert make_task(status=PlanTaskStatus.SKIPPED).is_terminal is True

    def test_is_not_terminal_pending(self):
        assert make_task(status=PlanTaskStatus.PENDING).is_terminal is False

    def test_is_not_terminal_running(self):
        assert make_task(status=PlanTaskStatus.RUNNING).is_terminal is False

    def test_mark_running(self):
        t = make_task()
        t.mark_running()
        assert t.status == PlanTaskStatus.RUNNING
        assert t.started_at is not None

    def test_mark_done(self):
        t = make_task()
        t.mark_done(commit_hash="abc123")
        assert t.status == PlanTaskStatus.DONE
        assert t.commit_hash == "abc123"
        assert t.finished_at is not None

    def test_mark_done_no_commit(self):
        t = make_task()
        t.mark_done()
        assert t.status == PlanTaskStatus.DONE
        assert t.commit_hash is None

    def test_mark_escalated(self):
        t = make_task()
        t.mark_escalated()
        assert t.status == PlanTaskStatus.ESCALATED
        assert t.finished_at is not None

    def test_mark_skipped(self):
        t = make_task()
        t.mark_skipped()
        assert t.status == PlanTaskStatus.SKIPPED
        assert t.finished_at is not None

    def test_reset(self):
        t = make_task()
        t.mark_done(commit_hash="abc123")
        t.reset()
        assert t.status == PlanTaskStatus.PENDING
        assert t.commit_hash is None
        assert t.started_at is None
        assert t.finished_at is None

    def test_round_trip_dict_minimal(self):
        t = make_task()
        assert PlanTask.from_dict(t.to_dict()) == t

    def test_round_trip_dict_full(self):
        t = PlanTask(
            id="2.3.1",
            description="Complex task",
            status=PlanTaskStatus.DONE,
            commit_hash="deadbeef",
            started_at="2026-01-01T10:00:00",
            finished_at="2026-01-01T10:05:00",
        )
        assert PlanTask.from_dict(t.to_dict()) == t

    def test_from_dict_defaults_status_pending(self):
        t = PlanTask.from_dict({"id": "1.1.1", "description": "x"})
        assert t.status == PlanTaskStatus.PENDING

    def test_to_dict_keys(self):
        t = make_task()
        d = t.to_dict()
        assert set(d) == {"id", "description", "status", "commit_hash", "started_at", "finished_at"}


# ---------------------------------------------------------------------------
# SubPhase
# ---------------------------------------------------------------------------


class TestSubPhase:
    def test_pending_tasks(self):
        sp = make_subphase(tasks=[
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.PENDING),
            make_task("1.1.3", status=PlanTaskStatus.PENDING),
        ])
        assert len(sp.pending_tasks) == 2

    def test_done_tasks(self):
        sp = make_subphase(tasks=[
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.PENDING),
        ])
        assert len(sp.done_tasks) == 1

    def test_is_complete_all_done(self):
        sp = make_subphase(tasks=[
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.SKIPPED),
        ])
        assert sp.is_complete is True

    def test_is_complete_not_all_terminal(self):
        sp = make_subphase(tasks=[
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.PENDING),
        ])
        assert sp.is_complete is False

    def test_has_escalated(self):
        sp = make_subphase(tasks=[
            make_task("1.1.1", status=PlanTaskStatus.ESCALATED),
        ])
        assert sp.has_escalated is True

    def test_has_not_escalated(self):
        sp = make_subphase(tasks=[make_task("1.1.1", status=PlanTaskStatus.DONE)])
        assert sp.has_escalated is False

    def test_next_pending_first(self):
        sp = make_subphase(tasks=[
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.PENDING),
            make_task("1.1.3", status=PlanTaskStatus.PENDING),
        ])
        assert sp.next_pending().id == "1.1.2"

    def test_next_pending_none(self):
        sp = make_subphase(tasks=[make_task("1.1.1", status=PlanTaskStatus.DONE)])
        assert sp.next_pending() is None

    def test_get_task_found(self):
        sp = make_subphase()
        assert sp.get_task("1.1.1") is not None

    def test_get_task_not_found(self):
        sp = make_subphase()
        assert sp.get_task("9.9.9") is None

    def test_round_trip_dict(self):
        sp = make_subphase()
        assert SubPhase.from_dict(sp.to_dict()) == sp

    def test_from_dict_empty_tasks(self):
        sp = SubPhase.from_dict({"id": "1.1", "name": "X"})
        assert sp.tasks == []


# ---------------------------------------------------------------------------
# Phase
# ---------------------------------------------------------------------------


class TestPhase:
    def _make_phase_with_statuses(self, *statuses: PlanTaskStatus) -> Phase:
        tasks = [make_task(f"1.1.{i + 1}", status=s) for i, s in enumerate(statuses)]
        sp = SubPhase(id="1.1", name="Sub", tasks=tasks)
        return Phase(id="1", name="Fase 1", subphases=[sp])

    def test_all_tasks(self):
        ph = make_phase()
        assert len(ph.all_tasks) == 2

    def test_pending_tasks(self):
        ph = self._make_phase_with_statuses(
            PlanTaskStatus.DONE, PlanTaskStatus.PENDING, PlanTaskStatus.PENDING
        )
        assert len(ph.pending_tasks) == 2

    def test_is_complete(self):
        ph = self._make_phase_with_statuses(PlanTaskStatus.DONE, PlanTaskStatus.SKIPPED)
        assert ph.is_complete is True

    def test_is_not_complete(self):
        ph = self._make_phase_with_statuses(PlanTaskStatus.DONE, PlanTaskStatus.PENDING)
        assert ph.is_complete is False

    def test_has_escalated(self):
        ph = self._make_phase_with_statuses(PlanTaskStatus.ESCALATED)
        assert ph.has_escalated is True

    def test_next_pending_respects_order(self):
        tasks = [
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.PENDING),
        ]
        sp1 = SubPhase(id="1.1", name="A", tasks=tasks)
        sp2 = SubPhase(id="1.2", name="B", tasks=[make_task("1.2.1", status=PlanTaskStatus.PENDING)])
        ph = Phase(id="1", name="P", subphases=[sp1, sp2])
        assert ph.next_pending().id == "1.1.2"

    def test_next_pending_none_when_complete(self):
        ph = self._make_phase_with_statuses(PlanTaskStatus.DONE)
        assert ph.next_pending() is None

    def test_get_subphase(self):
        ph = make_phase()
        assert ph.get_subphase("1.1") is not None
        assert ph.get_subphase("9.9") is None

    def test_get_task(self):
        ph = make_phase()
        assert ph.get_task("1.1.1") is not None
        assert ph.get_task("9.9.9") is None

    def test_round_trip_dict(self):
        ph = make_phase()
        assert Phase.from_dict(ph.to_dict()) == ph


# ---------------------------------------------------------------------------
# ProjectPlan
# ---------------------------------------------------------------------------


class TestProjectPlan:
    def test_all_tasks_flattened(self):
        plan = make_plan()
        assert len(plan.all_tasks) == 2

    def test_pending_tasks(self):
        plan = make_plan()
        assert len(plan.pending_tasks) == 2

    def test_is_complete_all_done(self):
        tasks = [make_task("1.1.1", status=PlanTaskStatus.DONE)]
        plan = ProjectPlan(
            name="P",
            phases=[Phase(id="1", name="F", subphases=[SubPhase(id="1.1", name="S", tasks=tasks)])],
        )
        assert plan.is_complete is True

    def test_is_complete_false(self):
        plan = make_plan()
        assert plan.is_complete is False

    def test_next_pending_cross_phases(self):
        ph1_tasks = [make_task("1.1.1", status=PlanTaskStatus.DONE)]
        ph2_tasks = [make_task("2.1.1", status=PlanTaskStatus.PENDING)]
        plan = ProjectPlan(
            name="P",
            phases=[
                Phase(id="1", name="F1", subphases=[SubPhase(id="1.1", name="S1", tasks=ph1_tasks)]),
                Phase(id="2", name="F2", subphases=[SubPhase(id="2.1", name="S2", tasks=ph2_tasks)]),
            ],
        )
        assert plan.next_pending().id == "2.1.1"

    def test_next_pending_none_when_complete(self):
        tasks = [make_task("1.1.1", status=PlanTaskStatus.DONE)]
        plan = ProjectPlan(
            name="P",
            phases=[Phase(id="1", name="F", subphases=[SubPhase(id="1.1", name="S", tasks=tasks)])],
        )
        assert plan.next_pending() is None

    def test_get_phase(self):
        plan = make_plan()
        assert plan.get_phase("1") is not None
        assert plan.get_phase("99") is None

    def test_get_subphase(self):
        plan = make_plan()
        assert plan.get_subphase("1.1") is not None
        assert plan.get_subphase("9.9") is None

    def test_get_task(self):
        plan = make_plan()
        assert plan.get_task("1.1.1") is not None
        assert plan.get_task("9.9.9") is None

    def test_progress_summary_all_pending(self):
        plan = make_plan()
        summary = plan.progress_summary()
        assert summary["pending"] == 2
        assert summary["done"] == 0
        assert summary["running"] == 0
        assert summary["escalated"] == 0
        assert summary["skipped"] == 0

    def test_progress_summary_mixed(self):
        tasks = [
            make_task("1.1.1", status=PlanTaskStatus.DONE),
            make_task("1.1.2", status=PlanTaskStatus.ESCALATED),
            make_task("1.1.3", status=PlanTaskStatus.PENDING),
        ]
        plan = ProjectPlan(
            name="P",
            phases=[Phase(id="1", name="F", subphases=[SubPhase(id="1.1", name="S", tasks=tasks)])],
        )
        summary = plan.progress_summary()
        assert summary["done"] == 1
        assert summary["escalated"] == 1
        assert summary["pending"] == 1

    def test_round_trip_dict_empty(self):
        plan = ProjectPlan(name="Empty")
        assert ProjectPlan.from_dict(plan.to_dict()) == plan

    def test_round_trip_dict_full(self):
        plan = make_plan()
        assert ProjectPlan.from_dict(plan.to_dict()) == plan

    def test_metadata_preserved(self):
        plan = ProjectPlan(name="P", metadata={"author": "Lucas", "version": "1.0"})
        restored = ProjectPlan.from_dict(plan.to_dict())
        assert restored.metadata == {"author": "Lucas", "version": "1.0"}

    def test_from_dict_defaults(self):
        plan = ProjectPlan.from_dict({"name": "Minimal"})
        assert plan.phases == []
        assert plan.metadata == {}


# ---------------------------------------------------------------------------
# parse_plan_text  (Task 6.1.2)
# ---------------------------------------------------------------------------

_FULL_PLAN = textwrap.dedent("""\
    # FinanceAI

    ## Fase 1 — Setup Inicial

    ### 1.1 Estrutura do Projeto

    - [ ] 1.1.1 Criar estrutura de pastas
    - [x] 1.1.2 Configurar pyproject.toml
    - [!] 1.1.3 Configurar banco de dados

    ### 1.2 Autenticacao

    - [ ] 1.2.1 Implementar JWT
    - [ ] 1.2.2 Criar endpoints de login

    ## Fase 2 — Features

    ### 2.1 CRUD

    - [ ] 2.1.1 Criar modelo de dados
""")


class TestParsePlanText:
    def test_project_name(self):
        plan = parse_plan_text(_FULL_PLAN)
        assert plan.name == "FinanceAI"

    def test_phase_count(self):
        plan = parse_plan_text(_FULL_PLAN)
        assert len(plan.phases) == 2

    def test_phase_ids_and_names(self):
        plan = parse_plan_text(_FULL_PLAN)
        assert plan.phases[0].id == "1"
        assert plan.phases[0].name == "Setup Inicial"
        assert plan.phases[1].id == "2"
        assert plan.phases[1].name == "Features"

    def test_subphase_count_phase1(self):
        plan = parse_plan_text(_FULL_PLAN)
        assert len(plan.phases[0].subphases) == 2

    def test_subphase_ids_and_names(self):
        plan = parse_plan_text(_FULL_PLAN)
        sp = plan.phases[0].subphases[0]
        assert sp.id == "1.1"
        assert sp.name == "Estrutura do Projeto"

    def test_task_count_subphase_1_1(self):
        plan = parse_plan_text(_FULL_PLAN)
        assert len(plan.phases[0].subphases[0].tasks) == 3

    def test_task_pending_status(self):
        plan = parse_plan_text(_FULL_PLAN)
        t = plan.get_task("1.1.1")
        assert t is not None
        assert t.status == PlanTaskStatus.PENDING
        assert t.description == "Criar estrutura de pastas"

    def test_task_done_status(self):
        plan = parse_plan_text(_FULL_PLAN)
        t = plan.get_task("1.1.2")
        assert t is not None
        assert t.status == PlanTaskStatus.DONE

    def test_task_escalated_status(self):
        plan = parse_plan_text(_FULL_PLAN)
        t = plan.get_task("1.1.3")
        assert t is not None
        assert t.status == PlanTaskStatus.ESCALATED

    def test_task_ids_correct(self):
        plan = parse_plan_text(_FULL_PLAN)
        ids = [t.id for t in plan.all_tasks]
        assert ids == ["1.1.1", "1.1.2", "1.1.3", "1.2.1", "1.2.2", "2.1.1"]

    def test_total_task_count(self):
        plan = parse_plan_text(_FULL_PLAN)
        assert len(plan.all_tasks) == 6

    def test_next_pending_skips_done_and_escalated(self):
        plan = parse_plan_text(_FULL_PLAN)
        # 1.1.1 is pending, so it should be returned
        assert plan.next_pending().id == "1.1.1"

    def test_progress_summary(self):
        plan = parse_plan_text(_FULL_PLAN)
        s = plan.progress_summary()
        assert s["pending"] == 4
        assert s["done"] == 1
        assert s["escalated"] == 1

    def test_no_title_raises(self):
        with pytest.raises(ValueError, match="no title"):
            parse_plan_text("## Fase 1 — Algo\n### 1.1 Sub\n- [ ] 1.1.1 Task\n")

    def test_empty_phases_no_crash(self):
        text = "# My Project\n"
        plan = parse_plan_text(text)
        assert plan.name == "My Project"
        assert plan.phases == []

    def test_phase_with_colon_separator(self):
        text = textwrap.dedent("""\
            # Proj

            ## Fase 1: Nome da Fase

            ### 1.1 Sub

            - [ ] 1.1.1 Task
        """)
        plan = parse_plan_text(text)
        assert plan.phases[0].id == "1"
        assert plan.phases[0].name == "Nome da Fase"

    def test_phase_without_fase_keyword(self):
        text = textwrap.dedent("""\
            # Proj

            ## 1 — Setup

            ### 1.1 Sub

            - [ ] 1.1.1 Task
        """)
        plan = parse_plan_text(text)
        assert plan.phases[0].id == "1"
        assert plan.phases[0].name == "Setup"

    def test_checkbox_case_insensitive_X(self):
        text = textwrap.dedent("""\
            # P

            ## Fase 1 — F

            ### 1.1 S

            - [X] 1.1.1 Done task
        """)
        plan = parse_plan_text(text)
        assert plan.get_task("1.1.1").status == PlanTaskStatus.DONE

    def test_running_checkbox(self):
        text = textwrap.dedent("""\
            # P

            ## Fase 1 — F

            ### 1.1 S

            - [>] 1.1.1 Running task
        """)
        plan = parse_plan_text(text)
        assert plan.get_task("1.1.1").status == PlanTaskStatus.RUNNING

    def test_blank_lines_ignored(self):
        text = "\n\n# Proj\n\n\n## Fase 1 — F\n\n\n### 1.1 S\n\n- [ ] 1.1.1 T\n\n"
        plan = parse_plan_text(text)
        assert len(plan.all_tasks) == 1

    def test_non_task_list_items_ignored(self):
        text = textwrap.dedent("""\
            # P

            ## Fase 1 — F

            ### 1.1 S

            - [ ] 1.1.1 Task
            - Regular list item (no checkbox)
            - Another item
        """)
        plan = parse_plan_text(text)
        assert len(plan.all_tasks) == 1


class TestParsePlanFile:
    def test_reads_file(self, tmp_path):
        plan_file = tmp_path / "PLANO.md"
        plan_file.write_text(_FULL_PLAN, encoding="utf-8")
        plan = parse_plan(plan_file)
        assert plan.name == "FinanceAI"
        assert len(plan.all_tasks) == 6

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_plan(tmp_path / "NOPE.md")

    def test_accepts_string_path(self, tmp_path):
        plan_file = tmp_path / "PLANO.md"
        plan_file.write_text(_FULL_PLAN, encoding="utf-8")
        plan = parse_plan(str(plan_file))
        assert plan.name == "FinanceAI"
