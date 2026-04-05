"""Unit tests for orchestrator/logger.py."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orchestrator.logger import _task_slug, list_runs, load_last, save
from orchestrator.models import CycleRecord, CycleStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(task: str = "add hello function", status: CycleStatus = CycleStatus.APPROVED) -> CycleRecord:
    return CycleRecord(task=task, status=status)


# ---------------------------------------------------------------------------
# _task_slug
# ---------------------------------------------------------------------------

class TestTaskSlug:
    def test_basic_lowercases_and_replaces_spaces(self):
        assert _task_slug("Add Hello Function") == "add_hello_function"

    def test_special_chars_removed(self):
        assert _task_slug("fix: bug #123!") == "fix_bug_123"

    def test_truncated_at_max_len(self):
        long = "a" * 100
        assert len(_task_slug(long, max_len=20)) == 20

    def test_empty_string_returns_empty(self):
        assert _task_slug("") == ""

    def test_multiple_separators_collapsed(self):
        result = _task_slug("fix   --  bug")
        assert "__" not in result


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

class TestSave:
    def test_creates_log_dir_if_absent(self, tmp_path):
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        save(_record(), diff="", log_dir=log_dir)
        assert log_dir.exists()

    def test_creates_json_file(self, tmp_path):
        save(_record(), diff="some diff", log_dir=tmp_path)
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_json_contains_task(self, tmp_path):
        save(_record(task="my task"), diff="", log_dir=tmp_path)
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["task"] == "my task"

    def test_json_contains_diff(self, tmp_path):
        save(_record(), diff="--- a\n+++ b\n", log_dir=tmp_path)
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "--- a" in data["diff"]

    def test_json_contains_status(self, tmp_path):
        save(_record(status=CycleStatus.ESCALATED), diff="", log_dir=tmp_path)
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["status"] == "escalated"

    def test_returns_path(self, tmp_path):
        path = save(_record(), diff="", log_dir=tmp_path)
        assert isinstance(path, Path)
        assert path.exists()

    def test_filename_contains_slug(self, tmp_path):
        save(_record(task="add hello"), diff="", log_dir=tmp_path)
        f = next(tmp_path.glob("*.json"))
        assert "add_hello" in f.name

    def test_commit_hash_persisted(self, tmp_path):
        record = _record()
        record.commit_hash = "abc1234"
        save(record, diff="", log_dir=tmp_path)
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["commit_hash"] == "abc1234"


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------

class TestListRuns:
    def test_empty_when_dir_missing(self, tmp_path):
        assert list_runs(tmp_path / "nonexistent") == []

    def test_returns_entries_newest_first(self, tmp_path):
        save(_record(task="first task"), diff="", log_dir=tmp_path)
        time.sleep(0.01)  # ensure different timestamps in filenames
        save(_record(task="second task"), diff="", log_dir=tmp_path)

        entries = list_runs(tmp_path)
        assert len(entries) == 2
        assert entries[0]["task"] == "second task"
        assert entries[1]["task"] == "first task"

    def test_limit_respected(self, tmp_path):
        for i in range(5):
            save(_record(task=f"task {i}"), diff="", log_dir=tmp_path)
            time.sleep(0.01)

        entries = list_runs(tmp_path, limit=3)
        assert len(entries) == 3

    def test_skips_corrupt_files(self, tmp_path):
        (tmp_path / "20260101_000000_bad.json").write_text("not json", encoding="utf-8")
        save(_record(task="good task"), diff="", log_dir=tmp_path)

        entries = list_runs(tmp_path)
        assert len(entries) == 1
        assert entries[0]["task"] == "good task"


# ---------------------------------------------------------------------------
# load_last
# ---------------------------------------------------------------------------

class TestLoadLast:
    def test_returns_none_when_no_logs(self, tmp_path):
        assert load_last(tmp_path / "empty") is None

    def test_returns_most_recent(self, tmp_path):
        save(_record(task="old task"), diff="", log_dir=tmp_path)
        time.sleep(0.01)
        save(_record(task="new task"), diff="", log_dir=tmp_path)

        last = load_last(tmp_path)
        assert last is not None
        assert last["task"] == "new task"
