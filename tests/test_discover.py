from __future__ import annotations

from pathlib import Path

import pytest

from codecrate.config import DEFAULT_INCLUDES
from codecrate.discover import discover_files, discover_python_files


def test_discover_basic(tmp_path: Path) -> None:
    """Test basic file discovery."""
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("text\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 2
    assert disc.root == tmp_path
    assert all(f.suffix == ".py" for f in disc.files)


def test_discover_files_includes_non_py_defaults(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("doc\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool]\n", encoding="utf-8")

    disc = discover_files(
        root=tmp_path,
        include=DEFAULT_INCLUDES,
        exclude=[],
        respect_gitignore=False,
    )
    rels = {p.relative_to(tmp_path).as_posix() for p in disc.files}
    assert "a.py" in rels
    assert "README.md" in rels
    assert "docs/x.md" in rels
    assert "pyproject.toml" in rels


def test_discover_nested_dirs(tmp_path: Path) -> None:
    """Test file discovery in nested directories."""
    (tmp_path / "sub1").mkdir()
    (tmp_path / "sub1" / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "sub2").mkdir()
    (tmp_path / "sub2" / "b.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "sub2" / "c.txt").write_text("text\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 2
    assert (tmp_path / "sub1" / "a.py") in disc.files
    assert (tmp_path / "sub2" / "b.py") in disc.files


def test_discover_with_include_pattern(tmp_path: Path) -> None:
    """Test file discovery with custom include pattern."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "b.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["src/**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 1
    assert disc.files[0] == tmp_path / "src" / "a.py"


def test_discover_with_exclude_pattern(tmp_path: Path) -> None:
    """Test file discovery with exclude pattern."""
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "test_a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "test_b.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=["test_*.py"],
        respect_gitignore=False,
    )

    assert len(disc.files) == 1
    assert disc.files[0] == tmp_path / "a.py"


def test_discover_with_gitignore(tmp_path: Path) -> None:
    """Test file discovery respecting .gitignore."""
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=True,
    )

    assert len(disc.files) == 1
    assert disc.files[0] == tmp_path / "a.py"


def test_discover_with_gitignore_disabled(tmp_path: Path) -> None:
    """Test file discovery not respecting .gitignore when disabled."""
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 2


def test_discover_empty_directory(tmp_path: Path) -> None:
    """Test file discovery in empty directory."""
    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 0


def test_discover_sorted(tmp_path: Path) -> None:
    """Test that discovered files are sorted."""
    (tmp_path / "c.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert disc.files == sorted(disc.files)


def test_discover_init_files(tmp_path: Path) -> None:
    """Test discovery of __init__.py files."""
    (tmp_path / "__init__.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "__init__.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 3


def test_discover_with_codecrateignore(tmp_path: Path) -> None:
    """Test file discovery respecting .codecrateignore (always)."""
    (tmp_path / ".codecrateignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert len(disc.files) == 1
    assert disc.files[0] == tmp_path / "a.py"


def test_discover_files_explicit_respects_codecrateignore(tmp_path: Path) -> None:
    (tmp_path / ".codecrateignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("pass\n", encoding="utf-8")

    disc = discover_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
        explicit_files=[Path("a.py"), Path("ignored.py")],
    )

    assert disc.files == [tmp_path / "a.py"]


def test_discover_files_explicit_respects_exclude_patterns(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("pass\n", encoding="utf-8")

    disc = discover_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=["b.py"],
        respect_gitignore=False,
        explicit_files=[Path("a.py"), Path("b.py")],
    )

    assert disc.files == [tmp_path / "a.py"]


def test_discover_files_explicit_respects_gitignore_when_enabled(
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("pass\n", encoding="utf-8")

    disc = discover_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=True,
        explicit_files=[Path("ok.py"), Path("ignored.py")],
    )

    assert disc.files == [tmp_path / "ok.py"]


def test_discover_files_explicit_rejects_outside_root_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "inside.py").write_text("pass\n", encoding="utf-8")

    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")

    disc = discover_files(
        root=repo,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
        explicit_files=[Path("inside.py"), outside],
    )

    assert disc.files == [repo / "inside.py"]


def test_discover_files_explicit_rejects_parent_relative_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "inside.py").write_text("pass\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")

    disc = discover_files(
        root=repo,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
        explicit_files=[Path("inside.py"), Path("../outside.py")],
    )

    assert disc.files == [repo / "inside.py"]
    skipped = {(item.path, item.reason) for item in disc.skipped}
    assert ("../outside.py", "outside-root") in skipped


def test_discover_files_explicit_reports_skipped_reasons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".codecrateignore").write_text("ignored.py\n", encoding="utf-8")
    (repo / "keep.py").write_text("pass\n", encoding="utf-8")
    (repo / "ignored.py").write_text("pass\n", encoding="utf-8")
    (repo / "excluded.py").write_text("pass\n", encoding="utf-8")

    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")

    disc = discover_files(
        root=repo,
        include=["**/*.py"],
        exclude=["excluded.py"],
        respect_gitignore=False,
        explicit_files=[
            Path("keep.py"),
            Path("keep.py"),
            Path("ignored.py"),
            Path("excluded.py"),
            Path("missing.py"),
            outside,
        ],
    )

    assert disc.files == [repo / "keep.py"]
    got = {(item.path, item.reason) for item in disc.skipped}
    assert ("keep.py", "duplicate") in got
    assert ("ignored.py", "ignored") in got
    assert ("excluded.py", "excluded") in got
    assert ("missing.py", "not-a-file") in got
    assert (outside.as_posix(), "outside-root") in got


def test_discover_codecrateignore_supports_negation(tmp_path: Path) -> None:
    (tmp_path / ".codecrateignore").write_text("*.py\n!keep.py\n", encoding="utf-8")
    (tmp_path / "drop.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )

    assert disc.files == [tmp_path / "keep.py"]


def test_codecrateignore_precedence_over_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / ".codecrateignore").write_text("!ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("pass\n", encoding="utf-8")

    disc = discover_python_files(
        root=tmp_path,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=True,
    )

    assert disc.files == [tmp_path / "ignored.py"]


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not supported: {exc}")


def test_discover_files_excludes_symlink_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "inside.py").write_text("pass\n", encoding="utf-8")

    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    _symlink_or_skip(root / "leak.py", outside)

    disc = discover_files(
        root=root,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )
    rels = {p.relative_to(root).as_posix() for p in disc.files}
    assert "inside.py" in rels
    assert "leak.py" not in rels


def test_discover_python_files_excludes_symlink_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "inside.py").write_text("pass\n", encoding="utf-8")

    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    _symlink_or_skip(root / "leak.py", outside)

    disc = discover_python_files(
        root=root,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )
    rels = {p.relative_to(root).as_posix() for p in disc.files}
    assert "inside.py" in rels
    assert "leak.py" not in rels
