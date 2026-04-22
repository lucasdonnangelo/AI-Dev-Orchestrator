"""Unit tests for orchestrator/project_planner.py."""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.project_planner import _build_user_message, _strip_outer_fence, generate_project_plan


# ---------------------------------------------------------------------------
# _build_user_message
# ---------------------------------------------------------------------------


class TestBuildUserMessage:
    def test_description_only(self) -> None:
        msg = _build_user_message("Build a REST API")
        assert "## Project Description" in msg
        assert "Build a REST API" in msg
        assert "## Premises" not in msg
        assert "## Stack" not in msg

    def test_with_premises(self) -> None:
        msg = _build_user_message("Build a REST API", premises="Use PostgreSQL only")
        assert "## Premises and Constraints" in msg
        assert "Use PostgreSQL only" in msg

    def test_with_stack(self) -> None:
        msg = _build_user_message("Build a REST API", stack="Python, FastAPI, SQLAlchemy")
        assert "## Stack / Technology Choices" in msg
        assert "Python, FastAPI, SQLAlchemy" in msg

    def test_with_all_fields(self) -> None:
        msg = _build_user_message(
            "Build a REST API",
            premises="No ORM",
            stack="Go, Gin",
        )
        assert "## Project Description" in msg
        assert "## Premises and Constraints" in msg
        assert "## Stack / Technology Choices" in msg

    def test_empty_premises_not_included(self) -> None:
        msg = _build_user_message("Build something", premises="   ")
        assert "## Premises" not in msg

    def test_empty_stack_not_included(self) -> None:
        msg = _build_user_message("Build something", stack="")
        assert "## Stack" not in msg

    def test_ends_with_generation_instruction(self) -> None:
        msg = _build_user_message("Build something")
        assert "Generate a complete PLANO.md" in msg


# ---------------------------------------------------------------------------
# _strip_outer_fence
# ---------------------------------------------------------------------------


class TestStripOuterFence:
    def test_plain_markdown_unchanged(self) -> None:
        md = "# My Project\n\n## Fase 1 — Setup\n"
        assert _strip_outer_fence(md) == md

    def test_strips_markdown_fence(self) -> None:
        fenced = textwrap.dedent("""\
            ```markdown
            # My Project

            ## Fase 1 — Setup

            ### 1.1 Core

            - [ ] 1.1.1 Do something
            ```
        """)
        result = _strip_outer_fence(fenced)
        assert result.startswith("# My Project")
        assert "```" not in result

    def test_strips_plain_fence(self) -> None:
        fenced = "```\n# Project\n\n## Fase 1 — X\n\n### 1.1 Y\n\n- [ ] 1.1.1 Z\n```"
        result = _strip_outer_fence(fenced)
        assert result.startswith("# Project")
        assert "```" not in result

    def test_no_closing_fence_returns_inner(self) -> None:
        # Edge case: model forgot to close the fence
        fenced = "```markdown\n# Project\n\n## Fase 1 — X\n"
        result = _strip_outer_fence(fenced)
        # Should not crash; inner content returned
        assert "# Project" in result

    def test_preserves_inner_code_fences(self) -> None:
        fenced = textwrap.dedent("""\
            ```markdown
            # Project

            ## Fase 1 — Setup

            ### 1.1 Core

            - [ ] 1.1.1 Create main.py
            ```
        """)
        result = _strip_outer_fence(fenced)
        assert "# Project" in result


# ---------------------------------------------------------------------------
# generate_project_plan
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


@pytest.mark.asyncio
async def test_generate_project_plan_returns_raw_and_parsed() -> None:
    """generate_project_plan returns (raw_md, ProjectPlan) on success."""
    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "You are a project planner."

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=_SAMPLE_PLANO)

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        raw_md, plan = await generate_project_plan(
            description="A financial REST API",
            config=config,
        )

    assert "# FinanceAPI" in raw_md
    assert plan.name == "FinanceAPI"
    assert len(plan.phases) == 2
    assert plan.phases[0].id == "1"
    assert plan.phases[0].name == "Setup"
    assert plan.phases[1].id == "2"


@pytest.mark.asyncio
async def test_generate_project_plan_strips_fence() -> None:
    """generate_project_plan strips outer markdown fence if model wraps output."""
    fenced = f"```markdown\n{_SAMPLE_PLANO}\n```"
    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=fenced)

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        raw_md, plan = await generate_project_plan("desc", config=config)

    assert plan.name == "FinanceAPI"
    assert not raw_md.startswith("```")


@pytest.mark.asyncio
async def test_generate_project_plan_passes_premises_and_stack() -> None:
    """generate_project_plan includes premises and stack in the user message."""
    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    captured: list[str] = []

    async def fake_call(prompt: str, system: str) -> str:
        captured.append(prompt)
        return _SAMPLE_PLANO

    mock_provider = MagicMock()
    mock_provider.call = fake_call

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        await generate_project_plan(
            description="Build something",
            config=config,
            premises="No ORM",
            stack="Python, FastAPI",
        )

    assert captured, "provider.call was not called"
    prompt = captured[0]
    assert "No ORM" in prompt
    assert "Python, FastAPI" in prompt


@pytest.mark.asyncio
async def test_generate_project_plan_raises_on_invalid_markdown() -> None:
    """generate_project_plan raises ValueError if model returns unparseable content."""
    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    mock_provider = AsyncMock()
    # No title heading — parse_plan_text will raise ValueError
    mock_provider.call = AsyncMock(return_value="just some prose with no heading")

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        with pytest.raises(ValueError):
            await generate_project_plan("desc", config=config)


@pytest.mark.asyncio
async def test_generate_project_plan_uses_project_planner_role() -> None:
    """Config.load_prompt is called with role='project_planner'."""
    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=_SAMPLE_PLANO)

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        await generate_project_plan("desc", config=config)

    config.load_prompt.assert_called_once()
    role_arg = config.load_prompt.call_args[0][0]
    assert role_arg == "project_planner"
