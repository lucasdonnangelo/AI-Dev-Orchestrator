"""Unit tests for orchestrator/models.py — serialization round-trips and edge cases."""

from __future__ import annotations

import pytest

from orchestrator.models import (
    Complexity,
    CriticResult,
    CycleRecord,
    CycleStatus,
    ReviewIssue,
    ReviewResult,
    Severity,
    TaskPlan,
)


# ---------------------------------------------------------------------------
# TaskPlan
# ---------------------------------------------------------------------------

class TestTaskPlan:
    def _make(self, **kwargs) -> TaskPlan:
        defaults = dict(
            description="Do something",
            files_to_create=["a.py"],
            files_to_modify=["b.py"],
            steps=["Step 1", "Step 2"],
            acceptance_criteria=["It works"],
            estimated_complexity=Complexity.LOW,
        )
        defaults.update(kwargs)
        return TaskPlan(**defaults)

    def test_to_dict_keys(self):
        plan = self._make()
        d = plan.to_dict()
        assert set(d) == {
            "description", "files_to_create", "files_to_modify",
            "steps", "acceptance_criteria", "estimated_complexity",
        }

    def test_round_trip_dict(self):
        plan = self._make()
        assert TaskPlan.from_dict(plan.to_dict()) == plan

    def test_round_trip_json(self):
        plan = self._make()
        assert TaskPlan.from_json(plan.to_json()) == plan

    def test_complexity_serialized_as_string(self):
        plan = self._make(estimated_complexity=Complexity.HIGH)
        assert plan.to_dict()["estimated_complexity"] == "high"

    def test_from_dict_defaults_empty_lists(self):
        plan = TaskPlan.from_dict({"description": "minimal"})
        assert plan.files_to_create == []
        assert plan.files_to_modify == []
        assert plan.steps == []
        assert plan.acceptance_criteria == []
        assert plan.estimated_complexity == Complexity.MEDIUM

    def test_from_json_strips_nothing_extra(self):
        raw = '{"description": "test", "steps": ["s1"], "estimated_complexity": "low"}'
        plan = TaskPlan.from_json(raw)
        assert plan.description == "test"
        assert plan.steps == ["s1"]
        assert plan.estimated_complexity == Complexity.LOW


# ---------------------------------------------------------------------------
# CriticResult
# ---------------------------------------------------------------------------

class TestCriticResult:
    def _make(self, **kwargs) -> CriticResult:
        defaults = dict(
            consensus=True,
            observations=["Looks good"],
            suggestions=["Add more tests"],
            score=9,
            round=2,
        )
        defaults.update(kwargs)
        return CriticResult(**defaults)

    def test_round_trip(self):
        cr = self._make()
        assert CriticResult.from_dict(cr.to_dict()) == cr

    def test_consensus_false(self):
        cr = self._make(consensus=False, score=5)
        assert cr.consensus is False
        assert CriticResult.from_dict(cr.to_dict()).consensus is False

    def test_from_dict_empty_lists(self):
        cr = CriticResult.from_dict({"consensus": True, "score": 8, "round": 1})
        assert cr.observations == []
        assert cr.suggestions == []

    def test_score_boundaries(self):
        for score in (1, 5, 10):
            cr = self._make(score=score)
            assert CriticResult.from_dict(cr.to_dict()).score == score

    def test_round_field_preserved(self):
        cr = self._make(round=5)
        assert CriticResult.from_dict(cr.to_dict()).round == 5


# ---------------------------------------------------------------------------
# ReviewIssue + ReviewResult
# ---------------------------------------------------------------------------

class TestReviewIssue:
    def test_round_trip_full(self):
        issue = ReviewIssue(
            severity=Severity.CRITICAL,
            description="Null pointer",
            file="foo.py",
            line=42,
            suggestion="Add a guard",
        )
        assert ReviewIssue.from_dict(issue.to_dict()) == issue

    def test_round_trip_minimal(self):
        issue = ReviewIssue(severity=Severity.INFO, description="minor note")
        d = issue.to_dict()
        assert "file" not in d
        assert "line" not in d
        assert "suggestion" not in d
        restored = ReviewIssue.from_dict(d)
        assert restored.file == ""
        assert restored.line is None
        assert restored.suggestion == ""

    def test_severity_values(self):
        for sev in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
            issue = ReviewIssue(severity=sev, description="x")
            assert ReviewIssue.from_dict(issue.to_dict()).severity == sev


class TestReviewResult:
    def _make(self, **kwargs) -> ReviewResult:
        defaults = dict(
            approved=True,
            score=8,
            issues=[],
            suggestions=["Use type hints"],
            summary="Looks good",
        )
        defaults.update(kwargs)
        return ReviewResult(**defaults)

    def test_round_trip_approved(self):
        rr = self._make()
        assert ReviewResult.from_dict(rr.to_dict()) == rr

    def test_round_trip_rejected_with_issues(self):
        rr = self._make(
            approved=False,
            score=3,
            issues=[
                ReviewIssue(severity=Severity.CRITICAL, description="Bug"),
                ReviewIssue(severity=Severity.WARNING, description="Style"),
            ],
        )
        restored = ReviewResult.from_dict(rr.to_dict())
        assert restored.approved is False
        assert len(restored.issues) == 2
        assert restored.issues[0].severity == Severity.CRITICAL


# ---------------------------------------------------------------------------
# CycleRecord
# ---------------------------------------------------------------------------

class TestCycleRecord:
    def test_to_dict_without_plan_or_review(self):
        rec = CycleRecord(task="do x", status=CycleStatus.PLANNED)
        d = rec.to_dict()
        assert d["task"] == "do x"
        assert d["status"] == "planned"
        assert d["plan"] is None
        assert d["review"] is None

    def test_to_dict_with_plan(self):
        plan = TaskPlan(description="p", steps=["s"])
        rec = CycleRecord(task="do x", status=CycleStatus.APPROVED, plan=plan)
        d = rec.to_dict()
        assert d["plan"]["description"] == "p"

    def test_started_at_is_set_automatically(self):
        rec = CycleRecord(task="t", status=CycleStatus.PLANNED)
        assert rec.started_at  # not empty
