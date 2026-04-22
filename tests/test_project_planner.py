"""Unit tests for orchestrator/project_planner.py."""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.project_planner import (
    _build_user_message,
    _strip_outer_fence,
    generate_project_plan,
    refine_project_plan,
    run_project_plan_critic_loop,
)


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


# ---------------------------------------------------------------------------
# refine_project_plan
# ---------------------------------------------------------------------------

_IMPROVED_PLANO = textwrap.dedent("""\
    # FinanceAPI

    ## Fase 1 — Setup

    ### 1.1 Project Structure

    - [ ] 1.1.1 Create pyproject.toml with dependencies
    - [ ] 1.1.2 Create directory structure
    - [ ] 1.1.3 Configure environment variables
    - [ ] 1.1.4 Write initial pytest configuration

    ## Fase 2 — Core

    ### 2.1 Models

    - [ ] 2.1.1 Create SQLAlchemy models
    - [ ] 2.1.2 Create Alembic migration
    - [ ] 2.1.3 Write unit tests for models
""")


@pytest.mark.asyncio
async def test_refine_project_plan_returns_improved_plan() -> None:
    """refine_project_plan calls the planner provider and returns updated plan."""
    from orchestrator.models import CriticResult

    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=_IMPROVED_PLANO)

    critic_result = CriticResult(
        consensus=False,
        observations=["Missing test tasks"],
        suggestions=["Add pytest tasks at the end of each subphase"],
        score=6,
        round=1,
    )

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        new_raw, new_plan = await refine_project_plan(
            description="A financial REST API",
            raw_md=_SAMPLE_PLANO,
            critic_result=critic_result,
            config=config,
        )

    assert "# FinanceAPI" in new_raw
    assert new_plan.name == "FinanceAPI"
    # Improved plan has more tasks in subphase 1.1
    assert len(new_plan.phases[0].subphases[0].tasks) == 4


@pytest.mark.asyncio
async def test_refine_project_plan_includes_critic_feedback_in_prompt() -> None:
    """refine_project_plan embeds observations and suggestions in the user message."""
    from orchestrator.models import CriticResult

    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    captured: list[str] = []

    async def fake_call(prompt: str, system: str) -> str:
        captured.append(prompt)
        return _IMPROVED_PLANO

    mock_provider = MagicMock()
    mock_provider.call = fake_call

    critic_result = CriticResult(
        consensus=False,
        observations=["No test coverage"],
        suggestions=["Add pytest tasks"],
        score=5,
        round=1,
    )

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        await refine_project_plan(
            description="A financial REST API",
            raw_md=_SAMPLE_PLANO,
            critic_result=critic_result,
            config=config,
        )

    assert captured
    prompt = captured[0]
    assert "No test coverage" in prompt
    assert "Add pytest tasks" in prompt
    assert "score 5/10" in prompt


@pytest.mark.asyncio
async def test_refine_project_plan_uses_project_planner_role() -> None:
    """refine_project_plan loads the prompt with role='project_planner'."""
    from orchestrator.models import CriticResult

    config = MagicMock()
    config.planner_provider = "anthropic"
    config.load_prompt.return_value = "system"

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=_IMPROVED_PLANO)

    critic_result = CriticResult(
        consensus=False, observations=[], suggestions=[], score=5, round=1
    )

    with patch("orchestrator.project_planner.make_provider", return_value=mock_provider):
        await refine_project_plan("desc", _SAMPLE_PLANO, critic_result, config)

    role_arg = config.load_prompt.call_args[0][0]
    assert role_arg == "project_planner"


# ---------------------------------------------------------------------------
# run_project_plan_critic_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critic_loop_stops_at_consensus() -> None:
    """Loop stops after min_rounds when consensus is reached."""
    from orchestrator.models import CriticResult
    from orchestrator.plan import parse_plan_text

    config = MagicMock()
    config.critic_min_rounds = 1
    config.critic_max_rounds = 3

    consensus_result = CriticResult(
        consensus=True, observations=["Looks good"], suggestions=[], score=9, round=1
    )

    plan = parse_plan_text(_SAMPLE_PLANO)

    with patch(
        "orchestrator.project_planner.critique_project_plan",
        new=AsyncMock(return_value=consensus_result),
    ):
        final_raw, final_plan = await run_project_plan_critic_loop(
            description="A financial REST API",
            raw_md=_SAMPLE_PLANO,
            plan=plan,
            config=config,
        )

    assert final_plan.name == "FinanceAPI"
    assert final_raw == _SAMPLE_PLANO  # no refinement needed


@pytest.mark.asyncio
async def test_critic_loop_refines_on_no_consensus() -> None:
    """Loop calls refine_project_plan when Critic does not reach consensus."""
    from orchestrator.models import CriticResult
    from orchestrator.plan import parse_plan_text

    config = MagicMock()
    config.critic_min_rounds = 1
    config.critic_max_rounds = 2

    no_consensus = CriticResult(
        consensus=False, observations=["Missing tests"], suggestions=["Add tests"], score=5, round=1
    )
    consensus = CriticResult(
        consensus=True, observations=["Good now"], suggestions=[], score=9, round=2
    )

    plan = parse_plan_text(_SAMPLE_PLANO)
    improved_plan = parse_plan_text(_IMPROVED_PLANO)

    critique_calls: list[int] = []

    async def fake_critique(raw_md: str, config: object, round_num: int, **kwargs: object) -> CriticResult:
        critique_calls.append(round_num)
        return no_consensus if round_num == 1 else consensus

    async def fake_refine(*args: object, **kwargs: object) -> tuple[str, object]:
        return _IMPROVED_PLANO, improved_plan

    with (
        patch("orchestrator.project_planner.critique_project_plan", side_effect=fake_critique),
        patch("orchestrator.project_planner.refine_project_plan", side_effect=fake_refine),
    ):
        final_raw, final_plan = await run_project_plan_critic_loop(
            description="A financial REST API",
            raw_md=_SAMPLE_PLANO,
            plan=plan,
            config=config,
        )

    assert critique_calls == [1, 2]
    assert final_raw == _IMPROVED_PLANO


@pytest.mark.asyncio
async def test_critic_loop_stops_at_max_rounds() -> None:
    """Loop exits after max_rounds even without consensus, returning last plan."""
    from orchestrator.models import CriticResult
    from orchestrator.plan import parse_plan_text

    config = MagicMock()
    config.critic_min_rounds = 2
    config.critic_max_rounds = 2

    no_consensus = CriticResult(
        consensus=False, observations=["Still bad"], suggestions=[], score=4, round=1
    )

    plan = parse_plan_text(_SAMPLE_PLANO)

    critique_calls: list[int] = []

    async def fake_critique(raw_md: str, config: object, round_num: int, **kwargs: object) -> CriticResult:
        critique_calls.append(round_num)
        return no_consensus

    async def fake_refine(*args: object, **kwargs: object) -> tuple[str, object]:
        return _SAMPLE_PLANO, plan

    with (
        patch("orchestrator.project_planner.critique_project_plan", side_effect=fake_critique),
        patch("orchestrator.project_planner.refine_project_plan", side_effect=fake_refine),
    ):
        final_raw, final_plan = await run_project_plan_critic_loop(
            description="desc",
            raw_md=_SAMPLE_PLANO,
            plan=plan,
            config=config,
        )

    # Should have run exactly max_rounds rounds
    assert len(critique_calls) == 2
    assert final_plan.name == "FinanceAPI"


# ---------------------------------------------------------------------------
# critique_project_plan (unit test for the critic.py function)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_project_plan_parses_result() -> None:
    """critique_project_plan calls critic provider and returns CriticResult."""
    import json

    from orchestrator.critic import critique_project_plan

    config = MagicMock()
    config.critic_provider = "google"
    config.load_prompt.return_value = "system"

    critic_json = json.dumps({
        "consensus": True,
        "observations": ["Well structured"],
        "suggestions": [],
        "score": 9,
        "round": 1,
    })

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=critic_json)

    with patch("orchestrator.critic.make_provider", return_value=mock_provider):
        result = await critique_project_plan(
            raw_md=_SAMPLE_PLANO,
            config=config,
            round_num=1,
            description="A financial API",
        )

    assert result.consensus is True
    assert result.score == 9
    assert result.round == 1
    assert "Well structured" in result.observations


@pytest.mark.asyncio
async def test_critique_project_plan_uses_plan_critic_role() -> None:
    """critique_project_plan loads the prompt with role='plan_critic'."""
    import json

    from orchestrator.critic import critique_project_plan

    config = MagicMock()
    config.critic_provider = "google"
    config.load_prompt.return_value = "system"

    critic_json = json.dumps({
        "consensus": True, "observations": [], "suggestions": [], "score": 8, "round": 1
    })

    mock_provider = AsyncMock()
    mock_provider.call = AsyncMock(return_value=critic_json)

    with patch("orchestrator.critic.make_provider", return_value=mock_provider):
        await critique_project_plan(_SAMPLE_PLANO, config, round_num=1)

    role_arg = config.load_prompt.call_args[0][0]
    assert role_arg == "plan_critic"


@pytest.mark.asyncio
async def test_critique_project_plan_includes_description_in_prompt() -> None:
    """critique_project_plan includes the project description in the user message."""
    import json

    from orchestrator.critic import critique_project_plan

    config = MagicMock()
    config.critic_provider = "google"
    config.load_prompt.return_value = "system"

    captured: list[str] = []

    async def fake_call(prompt: str, system: str) -> str:
        captured.append(prompt)
        return json.dumps({
            "consensus": True, "observations": [], "suggestions": [], "score": 8, "round": 1
        })

    mock_provider = MagicMock()
    mock_provider.call = fake_call

    with patch("orchestrator.critic.make_provider", return_value=mock_provider):
        await critique_project_plan(
            _SAMPLE_PLANO, config, round_num=1,
            description="Build a financial REST API with JWT auth"
        )

    assert captured
    assert "Build a financial REST API with JWT auth" in captured[0]
