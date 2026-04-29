"""Unit tests for orchestrator/providers/ — factory, plugin registry, and instantiation."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.config import Config
from orchestrator.providers import (
    BaseAgent,
    ClaudeProvider,
    GeminiProvider,
    OpenAIProvider,
    make_provider,
    register_provider,
)
from orchestrator.providers import _plugin_registry
from orchestrator.providers.anthropic import _EmptyResponseError
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

def _mock_response(text: str) -> MagicMock:
    """Build a minimal Anthropic-like response with a single text block."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


def _empty_response() -> MagicMock:
    """Build an Anthropic-like response with no content blocks."""
    response = MagicMock()
    response.content = []
    return response


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

    # ------------------------------------------------------------------
    # Empty / unparseable response retry behaviour
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_call_retries_on_json_decode_error(self, monkeypatch):
        """json.JSONDecodeError (HTTP 200 with empty body) triggers a retry."""
        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _noop_sleep)
        p = ClaudeProvider(api_key="sk-ant")
        calls = {"n": 0}

        async def _fake_create(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise json.JSONDecodeError("Expecting value", "", 0)
            return _mock_response("hello")

        monkeypatch.setattr(p._client.messages, "create", _fake_create)
        result = await p.call("test prompt")
        assert result == "hello"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_call_retries_on_empty_content_list(self, monkeypatch):
        """Empty content list (200 OK, no blocks) triggers a retry."""
        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _noop_sleep)
        p = ClaudeProvider(api_key="sk-ant")
        calls = {"n": 0}

        async def _fake_create(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _empty_response()
            return _mock_response("world")

        monkeypatch.setattr(p._client.messages, "create", _fake_create)
        result = await p.call("test prompt")
        assert result == "world"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_call_raises_empty_response_error_after_exhausting_retries(self, monkeypatch):
        """Persistent empty content exhausts retries and raises _EmptyResponseError."""
        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _noop_sleep)
        p = ClaudeProvider(api_key="sk-ant")

        async def _fake_create(**kwargs):
            return _empty_response()

        monkeypatch.setattr(p._client.messages, "create", _fake_create)
        with pytest.raises(_EmptyResponseError):
            await p.call("test prompt")

    @pytest.mark.asyncio
    async def test_call_raises_json_decode_error_after_exhausting_retries(self, monkeypatch):
        """Persistent JSONDecodeError exhausts retries and re-raises."""
        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _noop_sleep)
        p = ClaudeProvider(api_key="sk-ant")

        async def _fake_create(**kwargs):
            raise json.JSONDecodeError("Expecting value", "", 0)

        monkeypatch.setattr(p._client.messages, "create", _fake_create)
        with pytest.raises(json.JSONDecodeError):
            await p.call("test prompt")


async def _noop_sleep(_: float) -> None:
    """Drop-in replacement for asyncio.sleep that returns immediately."""


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------

class TestGeminiProvider:
    def test_is_base_agent_subclass(self):
        assert issubclass(GeminiProvider, BaseAgent)

    def test_instantiates_with_key(self):
        mock_genai = MagicMock()
        with patch("orchestrator.providers.google._genai", mock_genai):
            p = GeminiProvider(api_key="AI123", model="gemini-2.5-flash")
        assert isinstance(p, BaseAgentDirect)

    def test_call_is_coroutine(self):
        import inspect
        mock_genai = MagicMock()
        with patch("orchestrator.providers.google._genai", mock_genai):
            p = GeminiProvider(api_key="AI123")
        assert inspect.iscoroutinefunction(p.call)


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    def test_is_base_agent_subclass(self):
        assert issubclass(OpenAIProvider, BaseAgent)

    def test_instantiates_with_key(self):
        mock_openai = MagicMock()
        with patch("orchestrator.providers.openai._AsyncOpenAI", mock_openai):
            p = OpenAIProvider(api_key="sk-oai", model="gpt-4o-mini")
        assert isinstance(p, BaseAgentDirect)

    def test_call_is_coroutine(self):
        import inspect
        mock_openai = MagicMock()
        with patch("orchestrator.providers.openai._AsyncOpenAI", mock_openai):
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
        mock_genai = MagicMock()
        with patch("orchestrator.providers.google._genai", mock_genai):
            p = make_provider("google", self._cfg())
        assert isinstance(p, GeminiProvider)

    def test_openai_returns_openai_provider(self):
        mock_openai = MagicMock()
        with patch("orchestrator.providers.openai._AsyncOpenAI", mock_openai):
            p = make_provider("openai", self._cfg())
        assert isinstance(p, OpenAIProvider)

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            make_provider("mistral", self._cfg())

    def test_case_insensitive(self):
        p = make_provider("Anthropic", self._cfg())
        assert isinstance(p, ClaudeProvider)

    def test_whitespace_stripped(self):
        mock_genai = MagicMock()
        with patch("orchestrator.providers.google._genai", mock_genai):
            p = make_provider(" google ", self._cfg())
        assert isinstance(p, GeminiProvider)

    def test_all_return_base_agent(self):
        cfg = self._cfg()
        mock_genai = MagicMock()
        mock_openai = MagicMock()
        with (
            patch("orchestrator.providers.google._genai", mock_genai),
            patch("orchestrator.providers.openai._AsyncOpenAI", mock_openai),
        ):
            for name in ("anthropic", "google", "openai"):
                assert isinstance(make_provider(name, cfg), BaseAgent)


# ---------------------------------------------------------------------------
# Plugin registry — register_provider + make_provider integration
# ---------------------------------------------------------------------------


class _FakeProvider(BaseAgent):
    """Minimal BaseAgent subclass used in plugin tests."""

    def __init__(self, config: Config) -> None:
        self.config = config

    async def call(self, prompt: str, system: str = "") -> str:
        return f"fake:{prompt}"


class TestRegisterProvider:
    """Tests for the global plugin registry (register_provider API)."""

    def setup_method(self):
        # Snapshot registry before each test so we can restore it after.
        self._original = dict(_plugin_registry)

    def teardown_method(self):
        _plugin_registry.clear()
        _plugin_registry.update(self._original)

    def _cfg(self) -> Config:
        return Config(api_key="sk-ant")

    def test_registered_provider_returned_by_make_provider(self):
        register_provider("fake", _FakeProvider)
        p = make_provider("fake", self._cfg())
        assert isinstance(p, _FakeProvider)

    def test_registered_provider_receives_config(self):
        register_provider("fake", _FakeProvider)
        cfg = self._cfg()
        p = make_provider("fake", cfg)
        assert p.config is cfg  # type: ignore[attr-defined]

    def test_registry_is_case_insensitive(self):
        register_provider("MyProv", _FakeProvider)
        p = make_provider("myprov", self._cfg())
        assert isinstance(p, _FakeProvider)

    def test_registry_strips_whitespace(self):
        register_provider("  spaced  ", _FakeProvider)
        p = make_provider("spaced", self._cfg())
        assert isinstance(p, _FakeProvider)

    def test_re_registration_overwrites_previous(self):
        register_provider("fake", _FakeProvider)

        class _OtherProvider(_FakeProvider):
            pass

        register_provider("fake", _OtherProvider)
        p = make_provider("fake", self._cfg())
        assert isinstance(p, _OtherProvider)

    def test_unregistered_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            make_provider("not-registered", self._cfg())

    def test_register_provider_is_hot_swap(self):
        """Registering after make_provider has already been called changes future calls."""
        cfg = self._cfg()
        with pytest.raises(ValueError):
            make_provider("hot", cfg)
        register_provider("hot", _FakeProvider)
        p = make_provider("hot", cfg)
        assert isinstance(p, _FakeProvider)


# ---------------------------------------------------------------------------
# Plugin providers via config.plugin_providers
# ---------------------------------------------------------------------------


class TestConfigPluginProviders:
    """Tests for config-level providers (.orchestrator.yaml `providers:` block)."""

    def _cfg(self, plugin_providers: dict | None = None) -> Config:
        return Config(api_key="sk-ant", plugin_providers=plugin_providers or {})

    def test_dotted_path_in_plugin_providers_loaded(self):
        # Inject a synthetic module into sys.modules so importlib can find it.
        mod = types.ModuleType("_test_providers_mod")
        mod.FakeProvider = _FakeProvider  # type: ignore[attr-defined]
        sys.modules["_test_providers_mod"] = mod
        try:
            cfg = self._cfg({"myprov": "_test_providers_mod.FakeProvider"})
            p = make_provider("myprov", cfg)
            assert isinstance(p, _FakeProvider)
        finally:
            del sys.modules["_test_providers_mod"]

    def test_plugin_providers_loaded_from_yaml(self, tmp_path):
        """Config.load() parses 'providers:' block into plugin_providers dict."""
        (tmp_path / ".orchestrator.yaml").write_text(
            "providers:\n  myprov: 'some.module.MyClass'\n",
            encoding="utf-8",
        )
        from unittest.mock import patch as _patch
        import os
        with _patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk"}, clear=False):
            cfg = Config.load(str(tmp_path))
        assert cfg.plugin_providers == {"myprov": "some.module.MyClass"}

    def test_plugin_providers_empty_by_default(self):
        cfg = self._cfg()
        assert cfg.plugin_providers == {}


# ---------------------------------------------------------------------------
# Dotted-path provider name (make_provider fallback)
# ---------------------------------------------------------------------------


class TestDottedPathProvider:
    """Tests for passing 'module.ClassName' directly as the provider name."""

    def _cfg(self) -> Config:
        return Config(api_key="sk-ant")

    def _inject_module(self, mod_name: str, cls):
        mod = types.ModuleType(mod_name)
        setattr(mod, cls.__name__, cls)
        sys.modules[mod_name] = mod
        return mod

    def test_dotted_path_loads_provider(self):
        self._inject_module("_dp_test_mod", _FakeProvider)
        try:
            p = make_provider("_dp_test_mod._FakeProvider", self._cfg())
            assert isinstance(p, _FakeProvider)
        finally:
            del sys.modules["_dp_test_mod"]

    def test_dotted_path_provider_receives_config(self):
        self._inject_module("_dp_cfg_mod", _FakeProvider)
        try:
            cfg = self._cfg()
            p = make_provider("_dp_cfg_mod._FakeProvider", cfg)
            assert p.config is cfg  # type: ignore[attr-defined]
        finally:
            del sys.modules["_dp_cfg_mod"]

    def test_missing_module_raises_import_error(self):
        from orchestrator.providers import _load_plugin
        with pytest.raises(ImportError, match="Cannot import provider module"):
            _load_plugin("nonexistent_module_xyz.MyClass", self._cfg())

    def test_missing_class_raises_attribute_error(self):
        from orchestrator.providers import _load_plugin
        mod = types.ModuleType("_dp_empty_mod")
        sys.modules["_dp_empty_mod"] = mod
        try:
            with pytest.raises(AttributeError, match="no attribute"):
                _load_plugin("_dp_empty_mod.Missing", self._cfg())
        finally:
            del sys.modules["_dp_empty_mod"]

    def test_non_base_agent_class_raises_type_error(self):
        from orchestrator.providers import _load_plugin

        class NotAnAgent:
            pass

        mod = types.ModuleType("_dp_notbase_mod")
        mod.NotAnAgent = NotAnAgent  # type: ignore[attr-defined]
        sys.modules["_dp_notbase_mod"] = mod
        try:
            with pytest.raises(TypeError, match="subclass of BaseAgent"):
                _load_plugin("_dp_notbase_mod.NotAnAgent", self._cfg())
        finally:
            del sys.modules["_dp_notbase_mod"]

    def test_malformed_path_no_dot_raises_value_error(self):
        from orchestrator.providers import _load_plugin
        with pytest.raises(ValueError, match="Invalid provider path"):
            _load_plugin("NoDotClassName", self._cfg())

    def test_malformed_path_leading_dot_raises_value_error(self):
        from orchestrator.providers import _load_plugin
        with pytest.raises(ValueError, match="Invalid provider path"):
            _load_plugin(".OnlyClass", self._cfg())
