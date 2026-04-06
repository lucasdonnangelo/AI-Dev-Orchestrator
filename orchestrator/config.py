"""Configuration loader — merges .env, YAML defaults, and project overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "default.yaml"


@dataclass
class Config:
    """Resolved configuration for the orchestrator."""

    # --- Anthropic ---
    api_key: str
    model: str = "claude-sonnet-4-6"

    # --- Google (Gemini) ---
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Provider assignment per role ---
    planner_provider: str = "anthropic"
    critic_provider: str = "google"
    reviewer_provider: str = "google"
    decisor_provider: str = "google"

    # --- Critic loop ---
    critic_min_rounds: int = 2
    critic_max_rounds: int = 5

    # --- Execution ---
    max_retries: int = 3
    executor_allowed_tools: list[str] = field(
        default_factory=lambda: ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
    )
    confirm_plan: bool = True
    confirm_commit: bool = True
    log_dir: str = "logs"
    log_level: str = "INFO"
    project_dir: str = "."

    # --- Git ---
    git_auto_branch: bool = False
    git_conventional_commits: bool = True

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, project_dir: str | Path = ".") -> Config:
        """Build config by layering: defaults → project YAML → env vars."""

        # 1. Load .env (looks in cwd and parents)
        load_dotenv()

        # 2. Load default YAML
        data: dict = {}
        if _DEFAULT_CONFIG_PATH.exists():
            with open(_DEFAULT_CONFIG_PATH) as f:
                data = yaml.safe_load(f) or {}

        # 3. Layer project-level overrides (.orchestrator.yaml)
        project_path = Path(project_dir).resolve()
        project_yaml = project_path / ".orchestrator.yaml"
        if project_yaml.exists():
            with open(project_yaml) as f:
                project_data = yaml.safe_load(f) or {}
            data.update(project_data)

        # 4. Env-var overrides (highest priority)
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ORCHESTRATOR_MODEL", data.get("model", "claude-sonnet-4-6"))
        critic_min_rounds = int(
            os.getenv("CRITIC_MIN_ROUNDS", data.get("critic_min_rounds", 2))
        )
        critic_max_rounds = int(
            os.getenv("CRITIC_MAX_ROUNDS", data.get("critic_max_rounds", 5))
        )
        max_retries = int(
            os.getenv("ORCHESTRATOR_MAX_RETRIES", data.get("max_retries", 3))
        )
        log_level = os.getenv("ORCHESTRATOR_LOG_LEVEL", data.get("log_level", "INFO"))

        google_api_key = os.getenv("GOOGLE_API_KEY", data.get("google_api_key", ""))
        google_model = os.getenv(
            "GOOGLE_MODEL", data.get("google_model", "gemini-2.5-flash")
        )
        openai_api_key = os.getenv("OPENAI_API_KEY", data.get("openai_api_key", ""))
        openai_model = os.getenv(
            "OPENAI_MODEL", data.get("openai_model", "gpt-4o-mini")
        )

        planner_provider = os.getenv(
            "PLANNER_PROVIDER", data.get("planner_provider", "anthropic")
        )
        critic_provider = os.getenv(
            "CRITIC_PROVIDER", data.get("critic_provider", "google")
        )
        reviewer_provider = os.getenv(
            "REVIEWER_PROVIDER", data.get("reviewer_provider", "google")
        )
        decisor_provider = os.getenv(
            "DECISOR_PROVIDER", data.get("decisor_provider", "google")
        )

        git_auto_branch = str(
            os.getenv("GIT_AUTO_BRANCH", data.get("git_auto_branch", False))
        ).lower() in {"1", "true", "yes"}
        git_conventional_commits = str(
            os.getenv("GIT_CONVENTIONAL_COMMITS", data.get("git_conventional_commits", True))
        ).lower() not in {"0", "false", "no"}

        return cls(
            api_key=api_key,
            model=model,
            google_api_key=google_api_key,
            google_model=google_model,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            planner_provider=planner_provider,
            critic_provider=critic_provider,
            reviewer_provider=reviewer_provider,
            decisor_provider=decisor_provider,
            critic_min_rounds=critic_min_rounds,
            critic_max_rounds=critic_max_rounds,
            max_retries=max_retries,
            executor_allowed_tools=data.get(
                "executor_allowed_tools",
                ["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
            ),
            confirm_plan=data.get("confirm_plan", True),
            confirm_commit=data.get("confirm_commit", True),
            log_dir=data.get("log_dir", "logs"),
            log_level=log_level,
            project_dir=str(project_path),
            git_auto_branch=git_auto_branch,
            git_conventional_commits=git_conventional_commits,
        )

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = OK)."""
        errors: list[str] = []

        # Anthropic key is always required (Planner + Executor use Claude)
        if not self.api_key:
            errors.append(
                "ANTHROPIC_API_KEY not set. "
                "Add it to .env or export it: export ANTHROPIC_API_KEY=sk-ant-..."
            )

        # Check that providers configured for each role have their key available
        google_roles = [
            role
            for role, prov in (
                ("planner", self.planner_provider),
                ("critic", self.critic_provider),
                ("reviewer", self.reviewer_provider),
                ("decisor", self.decisor_provider),
            )
            if prov == "google"
        ]
        if google_roles and not self.google_api_key:
            roles_str = ", ".join(google_roles)
            errors.append(
                f"GOOGLE_API_KEY not set but required for role(s): {roles_str}. "
                "Add it to .env: GOOGLE_API_KEY=AI..."
            )

        openai_roles = [
            role
            for role, prov in (
                ("planner", self.planner_provider),
                ("critic", self.critic_provider),
                ("reviewer", self.reviewer_provider),
                ("decisor", self.decisor_provider),
            )
            if prov == "openai"
        ]
        if openai_roles and not self.openai_api_key:
            roles_str = ", ".join(openai_roles)
            errors.append(
                f"OPENAI_API_KEY not set but required for role(s): {roles_str}. "
                "Add it to .env: OPENAI_API_KEY=sk-..."
            )

        if self.critic_min_rounds < 1:
            errors.append("critic_min_rounds must be >= 1")
        if self.critic_max_rounds < self.critic_min_rounds:
            errors.append("critic_max_rounds must be >= critic_min_rounds")
        if self.max_retries < 1:
            errors.append("max_retries must be >= 1")

        return errors
