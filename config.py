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

    api_key: str
    model: str = "claude-sonnet-4-6"
    max_retries: int = 3
    executor_allowed_tools: list[str] = field(
        default_factory=lambda: ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
    )
    confirm_plan: bool = True
    confirm_commit: bool = True
    log_dir: str = "logs"
    log_level: str = "INFO"
    project_dir: str = "."

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
        max_retries = int(
            os.getenv("ORCHESTRATOR_MAX_RETRIES", data.get("max_retries", 3))
        )
        log_level = os.getenv("ORCHESTRATOR_LOG_LEVEL", data.get("log_level", "INFO"))

        return cls(
            api_key=api_key,
            model=model,
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
        )

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = OK)."""
        errors: list[str] = []
        if not self.api_key:
            errors.append(
                "ANTHROPIC_API_KEY not set. "
                "Add it to .env or export it: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        if self.max_retries < 1:
            errors.append("max_retries must be >= 1")
        return errors
