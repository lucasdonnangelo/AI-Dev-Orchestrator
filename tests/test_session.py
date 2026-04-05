"""Unit tests for Phase 2.4 — session.load() and session.update()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.models import (
    Complexity,
    DecisionResult,
    ReviewResult,
    TaskPlan,
)


# ---------------------------------------------------------------------------
# session.load()
# ---------------------------------------------------------------------------

class TestSessionLoad:
    def test_load_returns_content_when_file_exists(self, tmp_path):
        content = "# Sessao\nConteudo de teste."
        session_file = tmp_path / "SESSAO_ATUAL.md"
        session_file.write_text(content, encoding="utf-8")

        with patch("orchestrator.session._SESSION_PATH", session_file):
            from orchestrator import session
            result = session.load()

        assert result == content

    def test_load_returns_empty_string_when_missing(self, tmp_path):
        missing = tmp_path / "SESSAO_ATUAL.md"

        with patch("orchestrator.session._SESSION_PATH", missing):
            from orchestrator import session
            result = session.load()

        assert result == ""


# ---------------------------------------------------------------------------
# session.update()
# ---------------------------------------------------------------------------

class TestSessionUpdate:
    def _make_plan(self) -> TaskPlan:
        return TaskPlan(
            description="Add bar feature",
            files_to_create=["bar.py"],
            files_to_modify=[],
            steps=["Create bar.py"],
            acceptance_criteria=["pytest passes"],
            estimated_complexity=Complexity.LOW,
        )

    def _make_review(self) -> ReviewResult:
        return ReviewResult(approved=True, score=9, summary="Looks good")

    def _make_decision(self) -> DecisionResult:
        return DecisionResult(approved=True, reasoning="Coherent with plan.")

    @pytest.mark.asyncio
    async def test_update_writes_file(self, tmp_path):
        session_file = tmp_path / "SESSAO_ATUAL.md"
        session_file.write_text("# Old content", encoding="utf-8")

        new_content = "# Updated SESSAO_ATUAL\nNew state."
        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(return_value=new_content)

        with (
            patch("orchestrator.session._SESSION_PATH", session_file),
            patch("orchestrator.session.make_provider", return_value=mock_provider),
        ):
            from orchestrator import session
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            await session.update(
                "Add bar feature",
                self._make_plan(),
                "+def bar(): pass",
                self._make_review(),
                self._make_decision(),
                config,
            )

        assert session_file.read_text(encoding="utf-8") == new_content

    @pytest.mark.asyncio
    async def test_update_strips_markdown_fences(self, tmp_path):
        session_file = tmp_path / "SESSAO_ATUAL.md"
        session_file.write_text("# Old", encoding="utf-8")

        fenced = "```markdown\n# New content\nclean.\n```"
        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(return_value=fenced)

        with (
            patch("orchestrator.session._SESSION_PATH", session_file),
            patch("orchestrator.session.make_provider", return_value=mock_provider),
        ):
            from orchestrator import session
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            await session.update(
                "task",
                self._make_plan(),
                "+code",
                self._make_review(),
                self._make_decision(),
                config,
            )

        written = session_file.read_text(encoding="utf-8")
        assert not written.startswith("```")
        assert "# New content" in written

    @pytest.mark.asyncio
    async def test_update_includes_task_in_prompt(self, tmp_path):
        session_file = tmp_path / "SESSAO_ATUAL.md"
        session_file.write_text("", encoding="utf-8")

        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(return_value="# Updated")

        with (
            patch("orchestrator.session._SESSION_PATH", session_file),
            patch("orchestrator.session.make_provider", return_value=mock_provider),
        ):
            from orchestrator import session
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            await session.update(
                "UNIQUE_TASK_NAME_XYZ",
                self._make_plan(),
                "+code",
                self._make_review(),
                self._make_decision(),
                config,
            )

        call_args = mock_provider.call.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "UNIQUE_TASK_NAME_XYZ" in prompt

    @pytest.mark.asyncio
    async def test_update_truncates_large_diff(self, tmp_path):
        """Diff is capped at 3000 chars to avoid token overflow."""
        session_file = tmp_path / "SESSAO_ATUAL.md"
        session_file.write_text("", encoding="utf-8")

        large_diff = "+" + "x" * 10_000

        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(return_value="# Updated")

        with (
            patch("orchestrator.session._SESSION_PATH", session_file),
            patch("orchestrator.session.make_provider", return_value=mock_provider),
        ):
            from orchestrator import session
            from orchestrator.config import Config

            config = MagicMock(spec=Config)
            config.decisor_provider = "google"

            await session.update(
                "task",
                self._make_plan(),
                large_diff,
                self._make_review(),
                self._make_decision(),
                config,
            )

        call_args = mock_provider.call.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        # The full large_diff must NOT appear in the prompt
        assert large_diff not in prompt
