"""Unit tests for orchestrator/providers/ — factory and provider instantiation."""

from __future__ import annotations

import pytest

from orchestrator.config import Config
from orchestrator.providers import (
    BaseAgent,
    ClaudeProvider,
    GeminiProvider,
    OpenAIProvider,
    make_provider,
)
from orchestrator.providers.base import BaseAgent as BaseAgentDirect


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------

class TestBaseAgent:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseAgent()  # type: ignore[abstract]

    def test_call_is_abstract(self):
        import inspect
        assert inspect.isabstract(BaseAgent)


# ---------------------------------------------------------------------------
# ClaudeProvider
# ---------------------------------------------------------------------------

class TestClaudeProvider:
    def test_instantiates_with_key_and_model(self):
        p = ClaudeProvider(api_key="sk-ant", model="claude-sonnet-4-6")
        assert isinstance(p, BaseAgentDirect)

    def test_is_base_agent_subclass(self):
        assert issubclass(ClaudeProvider, BaseAgent)

    def test_call_is_coroutine(self):
        import inspect
        p = ClaudeProvider(api_key="sk")
        assert inspect.iscoroutinefunction(p.call)


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------

class TestGeminiProvider:
    def test_is_base_agent_subclass(self):
        assert issubclass(GeminiProvider, BaseAgent)

    def test_instantiates_with_key(self):
        p = GeminiProvider(api_key="AI123", model="gemini-2.5-flash")
        assert isinstance(p, BaseAgentDirect)

    def test_call_is_coroutine(self):
        import inspect
        p = GeminiProvider(api_key="AI123")
        assert inspect.iscoroutinefunction(p.call)


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    def test_is_base_agent_subclass(self):
        assert issubclass(OpenAIProvider, BaseAgent)

    def test_instantiates_with_key(self):
        p = OpenAIProvider(api_key="sk-oai", model="gpt-4o-mini")
        assert isinstance(p, BaseAgentDirect)

    def test_call_is_coroutine(self):
        import inspect
        p = OpenAIProvider(api_key="sk-oai")
        assert inspect.iscoroutinefunction(p.call)


# ---------------------------------------------------------------------------
# make_provider factory
# ---------------------------------------------------------------------------

class TestMakeProvider:
    def _cfg(self, **kwargs) -> Config:
        defaults = dict(
            api_key="sk-ant",
            google_api_key="AI123",
            openai_api_key="sk-oai",
            google_model="gemini-2.5-flash",
            openai_model="gpt-4o-mini",
        )
        defaults.update(kwargs)
        return Config(**defaults)

    def test_anthropic_returns_claude_provider(self):
        p = make_provider("anthropic", self._cfg())
        assert isinstance(p, ClaudeProvider)

    def test_google_returns_gemini_provider(self):
        p = make_provider("google", self._cfg())
        assert isinstance(p, GeminiProvider)

    def test_openai_returns_openai_provider(self):
        p = make_provider("openai", self._cfg())
        assert isinstance(p, OpenAIProvider)

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            make_provider("mistral", self._cfg())

    def test_case_insensitive(self):
        p = make_provider("Anthropic", self._cfg())
        assert isinstance(p, ClaudeProvider)

    def test_whitespace_stripped(self):
        p = make_provider(" google ", self._cfg())
        assert isinstance(p, GeminiProvider)

    def test_all_return_base_agent(self):
        cfg = self._cfg()
        for name in ("anthropic", "google", "openai"):
            assert isinstance(make_provider(name, cfg), BaseAgent)
