"""Tests for 'orchestrate plan generate' CLI command."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from orchestrator.cli import cli, _prompt_plan_approval, _print_generated_plan_view
from orchestrator.plan import parse_plan_text

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_PLANO = textwrap.dedent("""\
    # FinanceAPI

    ## Fase 1 — Setup

    ### 1.1 Project Structure

    - [ ] 1.1.1 Create pyproject.toml with dependencies
    - [ ] 1.1.2 Create directory structure
    - [ ] 1.1.3 Configure environment variables

    ## Fase 2 — Core

    ### 2.1 Models

    - [ ] 2.1.1 Create SQLAlchemy models
    - [ ] 2.1.2 Create Alembic migration
""")

_SAMPLE_PLAN = parse_plan_text(_SAMPLE_PLANO)


def _make_config(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.project_dir = str(tmp_path)
    cfg.validate.return_value = []
    cfg.critic_min_rounds = 1
    cfg.critic_max_rounds = 2
    return cfg


# ---------------------------------------------------------------------------
# _prompt_plan_approval
# ---------------------------------------------------------------------------


class TestPromptPlanApproval:
    def test_y_returns_y(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                ["plan", "generate", "--help"],
            )
        # Just verify _prompt_plan_approval logic via direct calls
        import io
        from unittest.mock import patch as _patch

        with _patch("click.prompt", return_value="y"):
            assert _prompt_plan_approval() == "y"

    def test_yes_returns_y(self) -> None:
        with patch("click.prompt", return_value="yes"):
            assert _prompt_plan_approval() == "y"

    def test_n_returns_n(self) -> None:
        with patch("click.prompt", return_value="n"):
            assert _prompt_plan_approval() == "n"

    def test_no_returns_n(self) -> None:
        with patch("click.prompt", return_value="no"):
            assert _prompt_plan_approval() == "n"

    def test_edit_returns_edit(self) -> None:
        with patch("click.prompt", return_value="edit"):
            assert _prompt_plan_approval() == "edit"

    def test_e_returns_edit(self) -> None:
        with patch("click.prompt", return_value="e"):
            assert _prompt_plan_approval() == "edit"

    def test_invalid_then_valid(self) -> None:
        with patch("click.prompt", side_effect=["bad", "y"]):
            assert _prompt_plan_approval() == "y"


# ---------------------------------------------------------------------------
# _print_generated_plan_view
# ---------------------------------------------------------------------------


class TestPrintGeneratedPlanView:
    def test_prints_without_error(self, capsys) -> None:
        """_print_generated_plan_view should not raise for a valid plan."""
        _print_generated_plan_view(_SAMPLE_PLAN)

    def test_shows_all_phases(self, capsys) -> None:
        from io import StringIO
        from rich.console import Console as RichConsole

        buf = StringIO()
        # Patch the module-level console to capture output
        with patch("orchestrator.cli.console", new=RichConsole(file=buf, highlight=False)):
            _print_generated_plan_view(_SAMPLE_PLAN)
        output = buf.getvalue()
        assert "Fase 1" in output
        assert "Fase 2" in output
        assert "FinanceAPI" in output


# ---------------------------------------------------------------------------
# plan generate command (integration via CliRunner)
# ---------------------------------------------------------------------------


class TestPlanGenerateCommand:
    def _invoke(self, tmp_path: Path, extra_args: list[str] = (), input_text: str = "") -> object:
        runner = CliRunner()
        config = _make_config(tmp_path)

        with (
            patch("orchestrator.cli.Config.load", return_value=config),
            patch(
                "orchestrator.project_planner.generate_project_plan",
                new=AsyncMock(return_value=(_SAMPLE_PLANO, _SAMPLE_PLAN)),
            ),
            patch(
                "orchestrator.project_planner.run_project_plan_critic_loop",
                new=AsyncMock(return_value=(_SAMPLE_PLANO, _SAMPLE_PLAN)),
            ),
        ):
            return runner.invoke(
                cli,
                ["plan", "generate", "Build a financial REST API", "-d", str(tmp_path), *extra_args],
                input=input_text,
                catch_exceptions=False,
            )

    def test_saves_plano_with_yes_flag(self, tmp_path: Path) -> None:
        result = self._invoke(tmp_path, extra_args=["-y"])
        assert result.exit_code == 0, result.output
        plano = tmp_path / "PLANO.md"
        assert plano.exists()
        assert "FinanceAPI" in plano.read_text(encoding="utf-8")

    def test_output_shows_plan_name(self, tmp_path: Path) -> None:
        result = self._invoke(tmp_path, extra_args=["-y"])
        assert "FinanceAPI" in result.output

    def test_output_shows_saved_path(self, tmp_path: Path) -> None:
        result = self._invoke(tmp_path, extra_args=["-y"])
        assert "PLANO.md saved" in result.output

    def test_discards_when_user_says_no(self, tmp_path: Path) -> None:
        # User input: "n" to discard, then "N" to skip execution
        result = self._invoke(tmp_path, input_text="n\n")
        assert result.exit_code == 0
        assert not (tmp_path / "PLANO.md").exists()
        assert "discarded" in result.output

    def test_approves_when_user_says_y(self, tmp_path: Path) -> None:
        # User input: "y" to approve, then "n" to skip execution
        result = self._invoke(tmp_path, input_text="y\nn\n")
        assert result.exit_code == 0
        assert (tmp_path / "PLANO.md").exists()

    def test_no_critic_skips_loop(self, tmp_path: Path) -> None:
        runner = CliRunner()
        config = _make_config(tmp_path)

        loop_called = []

        with (
            patch("orchestrator.cli.Config.load", return_value=config),
            patch(
                "orchestrator.project_planner.generate_project_plan",
                new=AsyncMock(return_value=(_SAMPLE_PLANO, _SAMPLE_PLAN)),
            ),
            patch(
                "orchestrator.project_planner.run_project_plan_critic_loop",
                side_effect=lambda *a, **k: loop_called.append(1),
            ),
        ):
            result = runner.invoke(
                cli,
                ["plan", "generate", "desc", "-d", str(tmp_path), "--no-critic", "-y"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert len(loop_called) == 0, "Critic loop should not have been called"

    def test_critic_loop_called_by_default(self, tmp_path: Path) -> None:
        runner = CliRunner()
        config = _make_config(tmp_path)

        loop_called = []

        async def fake_loop(*args, **kwargs):
            loop_called.append(1)
            return _SAMPLE_PLANO, _SAMPLE_PLAN

        with (
            patch("orchestrator.cli.Config.load", return_value=config),
            patch(
                "orchestrator.project_planner.generate_project_plan",
                new=AsyncMock(return_value=(_SAMPLE_PLANO, _SAMPLE_PLAN)),
            ),
            patch("orchestrator.project_planner.run_project_plan_critic_loop", side_effect=fake_loop),
        ):
            runner.invoke(
                cli,
                ["plan", "generate", "desc", "-d", str(tmp_path), "-y"],
                catch_exceptions=False,
            )

        assert len(loop_called) == 1

    def test_config_validation_error_exits(self, tmp_path: Path) -> None:
        runner = CliRunner()
        bad_config = MagicMock()
        bad_config.validate.return_value = ["ANTHROPIC_API_KEY is required"]

        with patch("orchestrator.cli.Config.load", return_value=bad_config):
            result = runner.invoke(
                cli,
                ["plan", "generate", "desc", "-d", str(tmp_path)],
                catch_exceptions=False,
            )

        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output

    def test_invalid_generated_plan_exits(self, tmp_path: Path) -> None:
        runner = CliRunner()
        config = _make_config(tmp_path)

        with (
            patch("orchestrator.cli.Config.load", return_value=config),
            patch(
                "orchestrator.project_planner.generate_project_plan",
                side_effect=ValueError("no title heading"),
            ),
        ):
            result = runner.invoke(
                cli,
                ["plan", "generate", "desc", "-d", str(tmp_path)],
                catch_exceptions=False,
            )

        assert result.exit_code != 0
        assert "Could not parse" in result.output

    def test_overwrites_existing_plano_with_yes(self, tmp_path: Path) -> None:
        # Pre-existing PLANO.md
        (tmp_path / "PLANO.md").write_text("# Old Project\n", encoding="utf-8")
        result = self._invoke(tmp_path, extra_args=["-y"])
        assert result.exit_code == 0
        content = (tmp_path / "PLANO.md").read_text(encoding="utf-8")
        assert "FinanceAPI" in content

    def test_premises_and_stack_passed_to_generator(self, tmp_path: Path) -> None:
        runner = CliRunner()
        config = _make_config(tmp_path)

        captured_kwargs: list[dict] = []

        async def fake_generate(desc, cfg, premises="", stack=""):
            captured_kwargs.append({"premises": premises, "stack": stack})
            return _SAMPLE_PLANO, _SAMPLE_PLAN

        with (
            patch("orchestrator.cli.Config.load", return_value=config),
            patch("orchestrator.project_planner.generate_project_plan", side_effect=fake_generate),
            patch(
                "orchestrator.project_planner.run_project_plan_critic_loop",
                new=AsyncMock(return_value=(_SAMPLE_PLANO, _SAMPLE_PLAN)),
            ),
        ):
            runner.invoke(
                cli,
                [
                    "plan", "generate", "desc", "-d", str(tmp_path),
                    "-p", "No ORM", "-s", "Python, FastAPI", "-y",
                ],
                catch_exceptions=False,
            )

        assert captured_kwargs
        assert captured_kwargs[0]["premises"] == "No ORM"
        assert captured_kwargs[0]["stack"] == "Python, FastAPI"

    def test_task_count_shown_in_output(self, tmp_path: Path) -> None:
        result = self._invoke(tmp_path, extra_args=["-y"])
        assert "5 tasks" in result.output  # _SAMPLE_PLANO has 5 tasks total
