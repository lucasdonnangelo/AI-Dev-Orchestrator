"""Tests for orchestrator.templates — template registry and init_project()."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.templates import (
    Template,
    get_template,
    init_project,
    list_templates,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestListTemplates:
    def test_returns_three_templates(self) -> None:
        assert len(list_templates()) == 3

    def test_sorted_by_name(self) -> None:
        names = [t.name for t in list_templates()]
        assert names == sorted(names)

    def test_all_have_required_fields(self) -> None:
        for t in list_templates():
            assert t.name
            assert t.description
            assert isinstance(t.files, dict)
            assert t.files, f"Template '{t.name}' has no files"


class TestGetTemplate:
    def test_returns_correct_template(self) -> None:
        t = get_template("fastapi")
        assert t is not None
        assert t.name == "fastapi"

    def test_python_cli_exists(self) -> None:
        assert get_template("python-cli") is not None

    def test_react_exists(self) -> None:
        assert get_template("react") is not None

    def test_unknown_returns_none(self) -> None:
        assert get_template("does-not-exist") is None

    def test_case_sensitive(self) -> None:
        assert get_template("FastAPI") is None


# ---------------------------------------------------------------------------
# Template content invariants
# ---------------------------------------------------------------------------


class TestTemplateContents:
    @pytest.mark.parametrize("name", ["fastapi", "python-cli", "react"])
    def test_each_template_has_orchestrator_yaml(self, name: str) -> None:
        t = get_template(name)
        assert t is not None
        assert ".orchestrator.yaml" in t.files

    @pytest.mark.parametrize("name", ["fastapi", "python-cli", "react"])
    def test_each_template_has_tasks_txt(self, name: str) -> None:
        t = get_template(name)
        assert t is not None
        assert "tasks.txt" in t.files

    @pytest.mark.parametrize("name", ["fastapi", "python-cli", "react"])
    def test_tasks_txt_has_multiple_tasks(self, name: str) -> None:
        t = get_template(name)
        assert t is not None
        tasks = [
            line.strip()
            for line in t.files["tasks.txt"].splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert len(tasks) >= 5, f"Template '{name}' has fewer than 5 tasks"

    @pytest.mark.parametrize("name", ["fastapi", "python-cli", "react"])
    def test_orchestrator_yaml_is_valid_yaml(self, name: str) -> None:
        import yaml

        t = get_template(name)
        assert t is not None
        data = yaml.safe_load(t.files[".orchestrator.yaml"])
        # May be None if only comments, but should not raise
        assert data is None or isinstance(data, dict)


# ---------------------------------------------------------------------------
# init_project
# ---------------------------------------------------------------------------


class TestInitProject:
    def test_creates_files_in_directory(self, tmp_path: Path) -> None:
        t = get_template("python-cli")
        assert t is not None
        written = init_project(t, tmp_path)
        assert set(written) == set(t.files.keys())
        for rel in t.files:
            assert (tmp_path / rel).exists()

    def test_file_content_matches_template(self, tmp_path: Path) -> None:
        t = get_template("fastapi")
        assert t is not None
        init_project(t, tmp_path)
        for rel, expected in t.files.items():
            actual = (tmp_path / rel).read_text(encoding="utf-8")
            assert actual == expected, f"Content mismatch for {rel}"

    def test_creates_target_directory_if_missing(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "brand" / "new" / "project"
        t = get_template("react")
        assert t is not None
        init_project(t, new_dir)
        assert new_dir.is_dir()

    def test_raises_on_existing_file_without_force(self, tmp_path: Path) -> None:
        t = get_template("fastapi")
        assert t is not None
        # Pre-create one of the template files
        (tmp_path / ".orchestrator.yaml").write_text("existing", encoding="utf-8")
        with pytest.raises(FileExistsError, match=".orchestrator.yaml"):
            init_project(t, tmp_path, force=False)

    def test_no_files_written_on_conflict_without_force(self, tmp_path: Path) -> None:
        """init_project() must not write any file when it raises FileExistsError."""
        t = get_template("python-cli")
        assert t is not None
        (tmp_path / ".orchestrator.yaml").write_text("existing", encoding="utf-8")
        try:
            init_project(t, tmp_path, force=False)
        except FileExistsError:
            pass
        # tasks.txt must NOT have been created
        assert not (tmp_path / "tasks.txt").exists()

    def test_force_overwrites_existing_files(self, tmp_path: Path) -> None:
        t = get_template("fastapi")
        assert t is not None
        (tmp_path / ".orchestrator.yaml").write_text("old content", encoding="utf-8")
        init_project(t, tmp_path, force=True)
        content = (tmp_path / ".orchestrator.yaml").read_text(encoding="utf-8")
        assert content != "old content"
        assert "fastapi" in content

    def test_returns_list_of_written_paths(self, tmp_path: Path) -> None:
        t = get_template("react")
        assert t is not None
        written = init_project(t, tmp_path)
        assert isinstance(written, list)
        assert len(written) == len(t.files)

    def test_custom_template_with_nested_path(self, tmp_path: Path) -> None:
        """Files with subdirectory paths are created with parent dirs."""
        t = Template(
            name="custom",
            description="test",
            files={
                "sub/dir/file.txt": "hello",
                "root.txt": "world",
            },
        )
        init_project(t, tmp_path)
        assert (tmp_path / "sub" / "dir" / "file.txt").read_text() == "hello"
        assert (tmp_path / "root.txt").read_text() == "world"
