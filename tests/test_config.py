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
