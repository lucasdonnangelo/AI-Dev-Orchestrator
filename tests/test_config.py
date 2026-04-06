"""Unit tests for orchestrator/config.py — field defaults, env-var loading, and validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from orchestrator.config import Config


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestConfigDefaults:
    def test_provider_defaults(self):
        c = Config(api_key="sk")
        assert c.planner_provider == "anthropic"
        assert c.critic_provider == "google"
        assert c.reviewer_provider == "google"
        assert c.decisor_provider == "google"

    def test_model_defaults(self):
        c = Config(api_key="sk")
        assert c.model == "claude-sonnet-4-6"
        assert c.google_model == "gemini-2.5-flash"
        assert c.openai_model == "gpt-4o-mini"

    def test_critic_round_defaults(self):
        c = Config(api_key="sk")
        assert c.critic_min_rounds == 2
        assert c.critic_max_rounds == 5

    def test_retry_default(self):
        c = Config(api_key="sk")
        assert c.max_retries == 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestConfigValidation:
    def test_missing_anthropic_key(self):
        c = Config(api_key="")
        errs = c.validate()
        assert any("ANTHROPIC_API_KEY" in e for e in errs)

    def test_valid_anthropic_only(self):
        c = Config(
            api_key="sk-ant",
            planner_provider="anthropic",
            critic_provider="anthropic",
            reviewer_provider="anthropic",
            decisor_provider="anthropic",
        )
        assert c.validate() == []

    def test_google_provider_without_key(self):
        c = Config(api_key="sk-ant", reviewer_provider="google", google_api_key="")
        errs = c.validate()
        assert any("GOOGLE_API_KEY" in e for e in errs)
        assert any("reviewer" in e for e in errs)

    def test_google_provider_with_key(self):
        c = Config(
            api_key="sk-ant",
            reviewer_provider="google",
            google_api_key="AI123",
            critic_provider="anthropic",
            decisor_provider="anthropic",
        )
        assert c.validate() == []

    def test_openai_provider_without_key(self):
        c = Config(api_key="sk-ant", critic_provider="openai", openai_api_key="")
        errs = c.validate()
        assert any("OPENAI_API_KEY" in e for e in errs)
        assert any("critic" in e for e in errs)

    def test_multiple_google_roles_reported_together(self):
        c = Config(
            api_key="sk-ant",
            critic_provider="google",
            reviewer_provider="google",
            decisor_provider="google",
            google_api_key="",
        )
        errs = c.validate()
        google_err = next(e for e in errs if "GOOGLE_API_KEY" in e)
        assert "critic" in google_err
        assert "reviewer" in google_err
        assert "decisor" in google_err

    def test_critic_max_rounds_less_than_min(self):
        c = Config(api_key="sk", critic_min_rounds=5, critic_max_rounds=2)
        errs = c.validate()
        assert any("critic_max_rounds" in e for e in errs)

    def test_max_retries_less_than_one(self):
        c = Config(api_key="sk", max_retries=0)
        errs = c.validate()
        assert any("max_retries" in e for e in errs)

    def test_valid_full_config(self):
        c = Config(
            api_key="sk-ant",
            google_api_key="AI123",
            planner_provider="anthropic",
            critic_provider="google",
            reviewer_provider="google",
            decisor_provider="google",
            critic_min_rounds=2,
            critic_max_rounds=5,
            max_retries=3,
        )
        assert c.validate() == []


# ---------------------------------------------------------------------------
# Env-var overrides (via Config.load)
# ---------------------------------------------------------------------------

class TestConfigLoad:
    def test_env_vars_override_defaults(self, tmp_path):
        env = {
            "ANTHROPIC_API_KEY": "sk-test",
            "GOOGLE_API_KEY": "AItest",
            "OPENAI_API_KEY": "sk-oai",
            "PLANNER_PROVIDER": "anthropic",
            "CRITIC_PROVIDER": "google",
            "REVIEWER_PROVIDER": "openai",
            "GOOGLE_MODEL": "gemini-2.5-flash",
            "OPENAI_MODEL": "gpt-4o",
            "CRITIC_MIN_ROUNDS": "3",
            "CRITIC_MAX_ROUNDS": "4",
        }
        with patch.dict(os.environ, env, clear=False):
            c = Config.load(str(tmp_path))
        assert c.api_key == "sk-test"
        assert c.google_api_key == "AItest"
        assert c.reviewer_provider == "openai"
        assert c.openai_model == "gpt-4o"
        assert c.critic_min_rounds == 3
        assert c.critic_max_rounds == 4

    def test_project_dir_is_resolved_absolute(self, tmp_path):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk"}, clear=False):
            c = Config.load(str(tmp_path))
        assert os.path.isabs(c.project_dir)

    def test_prompt_overrides_loaded_from_yaml(self, tmp_path):
        (tmp_path / ".orchestrator.yaml").write_text(
            "prompts:\n  planner: 'Custom planner prompt'\n  reviewer: 'Custom reviewer'\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk"}, clear=False):
            c = Config.load(str(tmp_path))
        assert c.prompt_overrides == {
            "planner": "Custom planner prompt",
            "reviewer": "Custom reviewer",
        }

    def test_prompt_overrides_empty_by_default(self, tmp_path):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk"}, clear=False):
            c = Config.load(str(tmp_path))
        assert c.prompt_overrides == {}


# ---------------------------------------------------------------------------
# load_prompt
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    def _config(self, tmp_path, overrides: dict | None = None) -> "Config":
        return Config(
            api_key="sk",
            project_dir=str(tmp_path),
            prompt_overrides=overrides or {},
        )

    def test_returns_default_file_when_no_override(self, tmp_path):
        default = tmp_path / "default_system.md"
        default.write_text("Default system prompt", encoding="utf-8")
        c = self._config(tmp_path)
        result = c.load_prompt("planner", default, fallback="Fallback")
        assert result == "Default system prompt"

    def test_returns_fallback_when_no_file_and_no_override(self, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        c = self._config(tmp_path)
        result = c.load_prompt("planner", missing, fallback="Fallback text")
        assert result == "Fallback text"

    def test_inline_override_takes_priority_over_default_file(self, tmp_path):
        default = tmp_path / "default.md"
        default.write_text("Default", encoding="utf-8")
        c = self._config(tmp_path, overrides={"planner": "Inline override"})
        result = c.load_prompt("planner", default, fallback="Fallback")
        assert result == "Inline override"

    def test_inline_override_takes_priority_over_fallback(self, tmp_path):
        missing = tmp_path / "no_file.md"
        c = self._config(tmp_path, overrides={"planner": "Inline override"})
        result = c.load_prompt("planner", missing, fallback="Fallback")
        assert result == "Inline override"

    def test_file_path_override_resolved_relative_to_project_dir(self, tmp_path):
        custom_prompt = tmp_path / "my_prompt.md"
        custom_prompt.write_text("Custom from file", encoding="utf-8")
        c = self._config(tmp_path, overrides={"reviewer": "my_prompt.md"})
        result = c.load_prompt("reviewer", tmp_path / "default.md", fallback="Fallback")
        assert result == "Custom from file"

    def test_file_path_override_in_subdirectory(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        custom = tmp_path / "prompts" / "custom.md"
        custom.write_text("Subdir prompt", encoding="utf-8")
        c = self._config(tmp_path, overrides={"critic": "prompts/custom.md"})
        result = c.load_prompt("critic", tmp_path / "default.md", fallback="Fallback")
        assert result == "Subdir prompt"

    def test_override_treated_as_inline_when_path_does_not_exist(self, tmp_path):
        c = self._config(tmp_path, overrides={"decisor": "Not a real path but inline text"})
        result = c.load_prompt("decisor", tmp_path / "default.md", fallback="Fallback")
        assert result == "Not a real path but inline text"

    def test_role_without_override_falls_through_to_default(self, tmp_path):
        default = tmp_path / "default.md"
        default.write_text("Default", encoding="utf-8")
        c = self._config(tmp_path, overrides={"planner": "Override only planner"})
        # "reviewer" has no override — should use default file
        result = c.load_prompt("reviewer", default, fallback="Fallback")
        assert result == "Default"

    def test_empty_overrides_dict_uses_default_file(self, tmp_path):
        default = tmp_path / "default.md"
        default.write_text("Default content", encoding="utf-8")
        c = self._config(tmp_path, overrides={})
        assert c.load_prompt("planner", default) == "Default content"
