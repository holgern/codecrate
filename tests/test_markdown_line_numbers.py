from __future__ import annotations

import re
from pathlib import Path

from codecrate.discover import discover_python_files
from codecrate.markdown import render_markdown
from codecrate.model import PackResult
from codecrate.packer import pack_repo


def _section_bounds(lines: list[str], title: str) -> tuple[int, int]:
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == title:
            start_idx = idx
            break
    if start_idx is None:
        return (0, 0)
    start_line = start_idx + 2
    end_line = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if lines[j].startswith("## ") and lines[j].strip() != title:
            end_line = j
            break
    return (start_line, end_line)


def _find_line(lines: list[str], start: int, end: int, needle: str) -> str:
    for idx in range(start - 1, end):
        if needle in lines[idx]:
            return lines[idx]
    raise AssertionError(f"Did not find '{needle}' in section")


def _extract_range(line: str) -> tuple[int, int]:
    match = re.search(r"\(L(\d+)-(\d+)\)", line)
    if not match:
        raise AssertionError(f"No line range found in: {line}")
    return int(match.group(1)), int(match.group(2))


def _pack_repo(root: Path) -> tuple[PackResult, dict[str, str]]:
    disc = discover_python_files(
        root, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    return pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)


def test_full_layout_line_numbers(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(
        "def f():\n    return 1\n\nclass C:\n    def m(self):\n        return 2\n",
        encoding="utf-8",
    )

    pack, canon = _pack_repo(root)
    md = render_markdown(pack, canon, layout="full")
    lines = md.splitlines()

    sym_start, sym_end = _section_bounds(lines, "## Symbol Index")
    file_start, file_end = _section_bounds(lines, "## Files")

    file_line = _find_line(lines, file_start, file_end, "### `a.py`")
    f_start, f_end = _extract_range(file_line)
    assert lines[f_start - 1].lstrip().startswith("def f(")
    assert lines[f_end - 1].lstrip() == "return 2"

    class_line = _find_line(lines, sym_start, sym_end, "class C")
    c_start, c_end = _extract_range(class_line)
    assert lines[c_start - 1].lstrip().startswith("class C")
    assert lines[c_end - 1].lstrip() == "return 2"

    def_line = _find_line(lines, sym_start, sym_end, "`f` →")
    d_start, d_end = _extract_range(def_line)
    assert lines[d_start - 1].lstrip().startswith("def f(")
    assert lines[d_end - 1].lstrip() == "return 1"


def test_stub_layout_line_numbers(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(
        "def f():\n    return 1\n\nclass C:\n    def m(self):\n        return 2\n",
        encoding="utf-8",
    )

    pack, canon = _pack_repo(root)
    md = render_markdown(pack, canon, layout="stubs")
    lines = md.splitlines()

    sym_start, sym_end = _section_bounds(lines, "## Symbol Index")
    lib_start, lib_end = _section_bounds(lines, "## Function Library")
    file_start, file_end = _section_bounds(lines, "## Files")

    def_line = _find_line(lines, sym_start, sym_end, "`f` →")
    d_start, d_end = _extract_range(def_line)
    assert lib_start < d_start <= lib_end
    assert lines[d_start - 1].lstrip().startswith("def f(")
    assert lines[d_end - 1].lstrip() == "return 1"

    class_line = _find_line(lines, sym_start, sym_end, "class C")
    c_start, c_end = _extract_range(class_line)
    assert file_start < c_start <= file_end
    assert lines[c_start - 1].lstrip().startswith("class C")
    assert "FUNC:" in lines[c_end - 1]

    file_line = _find_line(lines, file_start, file_end, "### `a.py`")
    f_start, f_end = _extract_range(file_line)
    assert file_start < f_start <= file_end
    assert lines[f_start - 1].lstrip().startswith("def f(")
    assert "FUNC:" in lines[f_end - 1]


def test_full_layout_line_numbers_with_markdown_fences(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text(
        "# Title\n\n## Section\n\n```bash\necho hi\n```\n\n## More\n",
        encoding="utf-8",
    )
    (root / "a.py").write_text(
        "def f():\n    return 1\n",
        encoding="utf-8",
    )

    pack, canon = pack_repo(
        root,
        [root / "README.md", root / "a.py"],
        keep_docstrings=True,
        dedupe=False,
    )
    md = render_markdown(pack, canon, layout="full")
    lines = md.splitlines()

    sym_start, sym_end = _section_bounds(lines, "## Symbol Index")
    file_line = _find_line(lines, sym_start, sym_end, "### `a.py`")
    _extract_range(file_line)
    assert "(empty)" not in file_line
    assert "<<CC:FILE:" not in file_line

    def_line = _find_line(lines, sym_start, sym_end, "`f` →")
    _extract_range(def_line)
