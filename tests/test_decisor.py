"""Unit tests for Phase 2.3 — DecisionResult model and decisor.decide()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models import (
    DecisionResult,
    ReviewResult,
    TaskPlan,
    Complexity,
)


# ---------------------------------------------------------------------------
# DecisionResult — model serialization
# ---------------------------------------------------------------------------

class TestDecisionResult:
    def _make(self, **kwargs) -> DecisionResult:
        defaults = dict(
            approved=True,
            reasoning="Implementation matches the plan perfectly.",
            inconsistencies=[],
        )
        defaults.update(kwargs)
        return DecisionResult(**defaults)

    def test_round_trip_approved(self):
        dr = self._make()
        assert DecisionResult.from_dict(dr.to_dict()) == dr

    def test_round_trip_rejected_with_inconsistencies(self):
        dr = self._make(
            approved=False,
            reasoning="Core step was skipped.",
            inconsistencies=["File foo.py was not created", "Step 2 not implemented"],
        )
        restored = DecisionResult.from_dict(dr.to_dict())
        assert restored.approved is False
        assert len(restored.inconsistencies) == 2
        assert "foo.py" in restored.inconsistencies[0]

    def test_to_dict_keys(self):
        dr = self._make()
        assert set(dr.to_dict()) == {"approved", "reasoning", "inconsistencies"}

    def test_from_dict_defaults_empty_inconsistencies(self):
        dr = DecisionResult.from_dict({"approved": True, "reasoning": "ok"})
        assert dr.inconsistencies == []

    def test_approved_coerced_to_bool(self):
        # Some models may return 1/0 instead of true/false
        dr = DecisionResult.from_dict({"approved": 1, "reasoning": "ok"})
        assert dr.approved is True
        dr2 = DecisionResult.from_dict({"approved": 0, "reasoning": "no"})
        assert dr2.approved is False

    def test_reasoning_defaults_to_empty_string(self):
        dr = DecisionResult.from_dict({"approved": True})
        assert dr.reasoning == ""


# ---------------------------------------------------------------------------
# decisor.decide() — unit test with mocked provider
# ---------------------------------------------------------------------------

class TestDecide:
    def _make_plan(self) -> TaskPlan:
        return TaskPlan(
            description="Add foo feature",
            files_to_create=["foo.py"],
            files_to_modify=[],
            steps=["Create foo.py", "Add tests"],
            acceptance_criteria=["pytest passes"],
            estimated_complexity=Complexity.LOW,
        )

    def _make_review(self, approved: bool = True) -> ReviewResult:
        return ReviewResult(approved=approved, score=9, summary="Looks good")

    @pytest.mark.asyncio
    async def test_decide_approved(self):
        plan = self._make_plan()
        review = self._make_review(approved=True)
        diff = "+def foo(): pass"

        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(
            return_value='{"approved": true, "reasoning": "All good.", "inconsistencies": []}'
        )

        with patch("orchestrator.decisor.make_provider", return_value=mock_provider):
            from orchestrator.decisor import decide
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            result = await decide(plan, diff, review, config, session_context="session ctx")

        assert result.approved is True
        assert result.reasoning == "All good."
        assert result.inconsistencies == []

    @pytest.mark.asyncio
    async def test_decide_rejected(self):
        plan = self._make_plan()
        review = self._make_review(approved=True)
        diff = ""

        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(
            return_value=(
                '{"approved": false, "reasoning": "foo.py was not created.", '
                '"inconsistencies": ["foo.py missing from diff"]}'
            )
        )

        with patch("orchestrator.decisor.make_provider", return_value=mock_provider):
            from orchestrator.decisor import decide
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            result = await decide(plan, diff, review, config, session_context="ctx")

        assert result.approved is False
        assert len(result.inconsistencies) == 1

    @pytest.mark.asyncio
    async def test_decide_strips_json_fences(self):
        plan = self._make_plan()
        review = self._make_review()
        diff = "+code"

        fenced = '```json\n{"approved": true, "reasoning": "ok", "inconsistencies": []}\n```'
        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(return_value=fenced)

        with patch("orchestrator.decisor.make_provider", return_value=mock_provider):
            from orchestrator.decisor import decide
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            result = await decide(plan, diff, review, config, session_context="ctx")

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_decide_uses_provided_session_context(self):
        """Provider call must include the supplied session context in the prompt."""
        plan = self._make_plan()
        review = self._make_review()

        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(
            return_value='{"approved": true, "reasoning": "ok", "inconsistencies": []}'
        )

        with patch("orchestrator.decisor.make_provider", return_value=mock_provider):
            from orchestrator.decisor import decide
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            await decide(plan, "+diff", review, config, session_context="CUSTOM_CTX")

        call_args = mock_provider.call.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "CUSTOM_CTX" in prompt
