"""Unit tests for orchestrator/chat.py — agent chat module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.chat import ROLES, send
from orchestrator.config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**kwargs) -> Config:
    defaults = dict(
        api_key="sk-ant",
        google_api_key="AI123",
        planner_provider="anthropic",
        critic_provider="google",
        reviewer_provider="google",
        decisor_provider="google",
    )
    defaults.update(kwargs)
    return Config(**defaults)


# ---------------------------------------------------------------------------
# ROLES constant
# ---------------------------------------------------------------------------


class TestRoles:
    def test_contains_all_four_roles(self) -> None:
        assert set(ROLES) == {"planner", "critic", "reviewer", "decisor"}

    def test_is_list(self) -> None:
        assert isinstance(ROLES, list)

    def test_has_four_entries(self) -> None:
        assert len(ROLES) == 4


# ---------------------------------------------------------------------------
# send() — provider and system prompt selection
# ---------------------------------------------------------------------------


class TestSend:
    """Tests for chat.send() — verify correct provider + prompt routing."""

    def _mock_provider(self, response: str = "mock response") -> MagicMock:
        provider = MagicMock()
        provider.call = AsyncMock(return_value=response)
        return provider

    @pytest.mark.asyncio
    async def test_send_planner_calls_planner_provider(self) -> None:
        cfg = _cfg(planner_provider="anthropic")
        mock_provider = self._mock_provider("plan response")

        with patch("orchestrator.chat.make_provider", return_value=mock_provider) as mock_mp:
            result = await send("planner", "Design a REST API", cfg)

        mock_mp.assert_called_once_with("anthropic", cfg)
        mock_provider.call.assert_called_once()
        assert result == "plan response"

    @pytest.mark.asyncio
    async def test_send_critic_calls_critic_provider(self) -> None:
        cfg = _cfg(critic_provider="google")
        mock_provider = self._mock_provider("critique")

        with patch("orchestrator.chat.make_provider", return_value=mock_provider) as mock_mp:
            await send("critic", "Evaluate this plan", cfg)

        mock_mp.assert_called_once_with("google", cfg)

    @pytest.mark.asyncio
    async def test_send_reviewer_calls_reviewer_provider(self) -> None:
        cfg = _cfg(reviewer_provider="google")
        mock_provider = self._mock_provider("review")

        with patch("orchestrator.chat.make_provider", return_value=mock_provider) as mock_mp:
            await send("reviewer", "Review this diff", cfg)

        mock_mp.assert_called_once_with("google", cfg)

    @pytest.mark.asyncio
    async def test_send_decisor_calls_decisor_provider(self) -> None:
        cfg = _cfg(decisor_provider="google")
        mock_provider = self._mock_provider("decision")

        with patch("orchestrator.chat.make_provider", return_value=mock_provider) as mock_mp:
            await send("decisor", "Is this coherent?", cfg)

        mock_mp.assert_called_once_with("google", cfg)

    @pytest.mark.asyncio
    async def test_send_passes_message_as_prompt(self) -> None:
        cfg = _cfg()
        mock_provider = self._mock_provider()

        with patch("orchestrator.chat.make_provider", return_value=mock_provider):
            await send("planner", "My task message", cfg)

        call_args = mock_provider.call.call_args
        # provider.call(message, system=...) — message is the first positional arg
        assert call_args.args[0] == "My task message"

    @pytest.mark.asyncio
    async def test_send_passes_system_prompt(self) -> None:
        cfg = _cfg()
        mock_provider = self._mock_provider()

        with patch("orchestrator.chat.make_provider", return_value=mock_provider):
            await send("planner", "Hello", cfg)

        call_args = mock_provider.call.call_args
        # system param must be non-empty (either bundled file or fallback)
        system = call_args[1].get("system") or (call_args[0][1] if len(call_args[0]) > 1 else "")
        assert system  # must not be empty string

    @pytest.mark.asyncio
    async def test_send_respects_prompt_override(self, tmp_path) -> None:
        """config.prompt_overrides["planner"] must reach the provider's system param."""
        cfg = Config(
            api_key="sk",
            project_dir=str(tmp_path),
            prompt_overrides={"planner": "Custom inline prompt"},
        )
        mock_provider = self._mock_provider()

        with patch("orchestrator.chat.make_provider", return_value=mock_provider):
            await send("planner", "Hello", cfg)

        call_args = mock_provider.call.call_args
        system = call_args[1].get("system") or (call_args[0][1] if len(call_args[0]) > 1 else "")
        assert system == "Custom inline prompt"

    @pytest.mark.asyncio
    async def test_send_returns_provider_response(self) -> None:
        cfg = _cfg()
        mock_provider = self._mock_provider("The final answer")

        with patch("orchestrator.chat.make_provider", return_value=mock_provider):
            result = await send("reviewer", "Any question", cfg)

        assert result == "The final answer"

    @pytest.mark.asyncio
    async def test_send_unknown_role_raises_key_error(self) -> None:
        cfg = _cfg()
        with pytest.raises(KeyError, match="Unknown role"):
            await send("unknown_role", "hello", cfg)

    @pytest.mark.asyncio
    async def test_send_all_valid_roles_succeed(self) -> None:
        cfg = _cfg()
        mock_provider = self._mock_provider("ok")

        with patch("orchestrator.chat.make_provider", return_value=mock_provider):
            for role in ROLES:
                result = await send(role, "test", cfg)
                assert result == "ok"

    @pytest.mark.asyncio
    async def test_send_uses_fallback_when_prompt_file_missing(self, tmp_path) -> None:
        """When no bundled prompt file exists and no override, fallback is used."""
        cfg = Config(
            api_key="sk",
            project_dir=str(tmp_path),
            planner_provider="anthropic",
        )
        mock_provider = self._mock_provider("response")

        # Patch the path so it points to a non-existent file
        nonexistent = tmp_path / "does_not_exist.md"
        with (
            patch("orchestrator.chat.make_provider", return_value=mock_provider),
            patch.dict(
                "orchestrator.chat._PROMPT_PATHS",
                {"planner": nonexistent},
            ),
        ):
            await send("planner", "Hello", cfg)

        call_args = mock_provider.call.call_args
        system = call_args[1].get("system") or (call_args[0][1] if len(call_args[0]) > 1 else "")
        # Should have used the fallback
        assert "planning assistant" in system.lower()
