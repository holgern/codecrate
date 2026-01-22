from __future__ import annotations

from pathlib import Path

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
