"""Execution logger — persists cycle records to logs/ as JSON files."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.models import CycleRecord


def _task_slug(task: str, max_len: int = 40) -> str:
    """Turn a task string into a safe filename fragment."""
    slug = task.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:max_len]


def _log_path(log_dir: str | Path, record: CycleRecord) -> Path:
    """Return the Path where this record should be saved."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    slug = _task_slug(record.task)
    filename = f"{ts}_{slug}.json" if slug else f"{ts}.json"
    return Path(log_dir) / filename


def save(record: CycleRecord, diff: str, log_dir: str | Path) -> Path:
    """Persist a cycle record to *log_dir* as a JSON file.

    Args:
        record: Completed CycleRecord (with optional commit_hash already set).
        diff: Unified diff string captured during execution.
        log_dir: Directory where log files are stored (created if absent).

    Returns:
        Path of the written file.
    """
    dir_path = Path(log_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    path = _log_path(log_dir, record)

    payload: dict[str, Any] = record.to_dict()
    payload["diff"] = diff

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_runs(log_dir: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    """Return up to *limit* log entries, sorted newest-first.

    Args:
        log_dir: Directory to scan for ``*.json`` log files.
        limit: Maximum number of entries to return.

    Returns:
        List of raw dicts loaded from JSON files (newest first).
        Empty list if *log_dir* does not exist or contains no logs.
    """
    dir_path = Path(log_dir)
    if not dir_path.exists():
        return []

    files = sorted(dir_path.glob("*.json"), reverse=True)[:limit]
    entries: list[dict[str, Any]] = []
    for f in files:
        try:
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return entries


def load_last(log_dir: str | Path) -> dict[str, Any] | None:
    """Return the most recent log entry, or None if none exist."""
    runs = list_runs(log_dir, limit=1)
    return runs[0] if runs else None
