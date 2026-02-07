from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codecrate.cli import main
from codecrate.diffgen import generate_patch_markdown
from codecrate.discover import discover_python_files
from codecrate.markdown import render_markdown
from codecrate.packer import pack_repo
from codecrate.udiff import FileDiff, apply_file_diffs, parse_unified_diff


def _extract_diff_blocks(md_text: str) -> str:
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "```diff":
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                out.append(lines[i])
                i += 1
        i += 1
    return "\n".join(out) + "\n"


def test_patch_apply_roundtrip(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    f = root / "a.py"
    f.write_text("def f():\n    return 1\n", encoding="utf-8")

    # old pack is just a baseline markdown with one file; for this test, keep it simple:
    old_md = (
        "# Codecrate Context Pack\n\n"
        "## Manifest\n\n"
        "```codecrate-manifest\n"
        "{\n"
        '  "format": "codecrate.v4",\n'
        '  "id_format_version": "sha1-8-upper:v1",\n'
        '  "marker_format_version": "v1",\n'
        '  "root": ".",\n'
        '  "files": [\n'
        '    {"path": "a.py", "module": "a", "line_count": 2, "classes": [],\n'
        '     "defs": [{"path": "a.py", "module": "a", "qualname": "f", '
        '"id": "DEADBEEF", "local_id": "DEADBEEF", "kind": "function", '
        '"decorator_start": 1, "def_line": 1, "body_start": 2, '
        '"end_line": 2, "doc_start": null, "doc_end": null, '
        '"is_single_line": false}]}\n'
        "  ]\n"
        "}\n"
        "```\n\n"
        "## Function Library\n\n"
        "### DEADBEEF — `a.f` (a.py:L1–L2)\n"
        "```python\n"
        "def f():\n"
        "    return 1\n"
        "```\n\n"
        "## Files\n\n"
        "### `a.py` (L1–L2)\n"
        "```python\n"
        "def f():\n"
        "    ...  # ↪ FUNC:v1:DEADBEEF\n"
        "```\n"
    )

    # change current file in a working copy
    cur = tmp_path / "cur"
    shutil.copytree(root, cur)
    (cur / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")

    patch_md = generate_patch_markdown(old_md, cur)
    diff_text = _extract_diff_blocks(patch_md)
    diffs = parse_unified_diff(diff_text)
    apply_root = tmp_path / "apply"
    shutil.copytree(root, apply_root)
    apply_file_diffs(diffs, apply_root)

    assert (apply_root / "a.py").read_text(encoding="utf-8") == (
        cur / "a.py"
    ).read_text(encoding="utf-8")


def test_patch_apply_add_delete(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()

    (base / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (base / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")

    disc = discover_python_files(
        base, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    old_md = render_markdown(pack, canon)

    # Create a "current" repo: delete b.py, add c.py
    cur = tmp_path / "cur"
    shutil.copytree(base, cur)
    (cur / "b.py").unlink()
    (cur / "c.py").write_text("def c():\n    return 3\n", encoding="utf-8")

    patch_md = generate_patch_markdown(old_md, cur)
    diff_text = _extract_diff_blocks(patch_md)
    diffs = parse_unified_diff(diff_text)

    # Apply patch to a fresh copy of base
    apply_root = tmp_path / "apply"
    shutil.copytree(base, apply_root)
    apply_file_diffs(diffs, apply_root)

    assert (apply_root / "a.py").read_text(encoding="utf-8") == (
        cur / "a.py"
    ).read_text(encoding="utf-8")
    assert not (apply_root / "b.py").exists()
    assert (apply_root / "c.py").read_text(encoding="utf-8") == (
        cur / "c.py"
    ).read_text(encoding="utf-8")


def test_parse_unified_diff_classifies_add_and_delete_ops() -> None:
    diff_text = (
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1 @@\n"
        "+x\n"
        "--- a/old.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-y\n"
    )

    diffs = parse_unified_diff(diff_text)
    assert len(diffs) == 2
    assert diffs[0].op == "add"
    assert diffs[0].path == "new.py"
    assert diffs[1].op == "delete"
    assert diffs[1].path == "old.py"


def test_parse_unified_diff_normalizes_crlf_input() -> None:
    diff_text = "--- a/a.py\r\n+++ b/a.py\r\n@@ -1,1 +1,1 @@\r\n-a\r\n+A\r\n"

    diffs = parse_unified_diff(diff_text)
    assert len(diffs) == 1
    assert diffs[0].path == "a.py"
    assert diffs[0].hunks[0][0] == "@@ -1,1 +1,1 @@"


def _single_add_diff(to_path: str) -> str:
    return f"--- /dev/null\n+++ {to_path}\n@@ -0,0 +1 @@\n+owned\n"


@pytest.mark.parametrize(
    "to_path",
    ["b/../evil.txt", "/abs/path", "b/a/../../evil", "b/"],
    ids=["parent-traversal", "absolute", "nested-traversal", "empty"],
)
def test_parse_unified_diff_rejects_unsafe_paths(to_path: str) -> None:
    with pytest.raises(ValueError):
        parse_unified_diff(_single_add_diff(to_path))


@pytest.mark.parametrize(
    "to_path",
    [r"b/C:\\temp\\evil.txt", "b/C:/temp/evil.txt", r"b/\\server\\share\\x.py"],
    ids=["windows-drive-backslash", "windows-drive-slash", "windows-unc"],
)
def test_parse_unified_diff_rejects_windows_like_paths(to_path: str) -> None:
    with pytest.raises(ValueError):
        parse_unified_diff(_single_add_diff(to_path))


@pytest.mark.parametrize(
    "bad_path",
    ["../evil.txt", "/abs/path", "a/../../evil", ""],
    ids=["parent-traversal", "absolute", "nested-traversal", "empty"],
)
def test_apply_rejects_unsafe_filediff_paths(tmp_path: Path, bad_path: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    diffs = [
        FileDiff(path=bad_path, hunks=[["@@ -0,0 +1 @@", "+owned"]], op="add"),
    ]

    with pytest.raises(ValueError):
        apply_file_diffs(diffs, root)


@pytest.mark.parametrize(
    "bad_path",
    [r"C:\\temp\\evil.txt", "C:/temp/evil.txt", r"\\server\\share\\x.py"],
    ids=["windows-drive-backslash", "windows-drive-slash", "windows-unc"],
)
def test_apply_rejects_windows_like_filediff_paths(
    tmp_path: Path, bad_path: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    diffs = [
        FileDiff(path=bad_path, hunks=[["@@ -0,0 +1 @@", "+owned"]], op="add"),
    ]

    with pytest.raises(ValueError):
        apply_file_diffs(diffs, root)


def test_apply_rejects_context_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("a\nb\n", encoding="utf-8")

    diff_text = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n a\n-x\n+b\n"
    diffs = parse_unified_diff(diff_text)

    with pytest.raises(ValueError):
        apply_file_diffs(diffs, root)


def test_apply_error_message_includes_path_hunk_and_excerpt(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("alpha\nbeta\n", encoding="utf-8")

    diff_text = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n alpha\n-gamma\n+G\n"
    diffs = parse_unified_diff(diff_text)

    with pytest.raises(ValueError) as excinfo:
        apply_file_diffs(diffs, root)

    msg = str(excinfo.value)
    assert "a.py" in msg
    assert "@@ -1,2 +1,2 @@" in msg
    assert "expected 'gamma'" in msg
    assert "got 'beta'" in msg


def test_apply_handles_trailing_newline_removal(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "a.py"
    target.write_text("a\n", encoding="utf-8")

    diff_text = (
        "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+a\n\\ No newline at end of file\n"
    )
    diffs = parse_unified_diff(diff_text)
    apply_file_diffs(diffs, root)

    assert target.read_text(encoding="utf-8") == "a"


def test_apply_handles_trailing_newline_addition(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "a.py"
    target.write_text("a", encoding="utf-8")

    diff_text = (
        "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+a\n"
    )
    diffs = parse_unified_diff(diff_text)
    apply_file_diffs(diffs, root)

    assert target.read_text(encoding="utf-8") == "a\n"


def test_apply_normalizes_crlf_to_lf_consistently(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "a.py"
    target.write_bytes(b"a\r\nb\r\n")

    diff_text = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
    diffs = parse_unified_diff(diff_text)
    apply_file_diffs(diffs, root)

    assert target.read_text(encoding="utf-8") == "a\nB\n"


def test_apply_creates_parent_dirs_for_nested_add(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    diff_text = (
        "--- /dev/null\n"
        "+++ b/new/deep/file.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def x():\n"
        "+    return 1\n"
    )
    diffs = parse_unified_diff(diff_text)
    apply_file_diffs(diffs, root)

    created = root / "new" / "deep" / "file.py"
    assert created.exists()
    assert created.read_text(encoding="utf-8") == "def x():\n    return 1\n"


def test_apply_dry_run_validates_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "a.py"
    target.write_text("a\nb\n", encoding="utf-8")

    patch_md = tmp_path / "patch.md"
    patch_md.write_text(
        "# Codecrate Patch\n\n"
        "```diff\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,2 +1,2 @@\n"
        " a\n"
        "-b\n"
        "+B\n"
        "```\n",
        encoding="utf-8",
    )

    main(["apply", str(patch_md), str(root), "--dry-run"])
    assert target.read_text(encoding="utf-8") == "a\nb\n"


def test_generate_patch_includes_baseline_metadata(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    disc = discover_python_files(
        root, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    old_md = render_markdown(pack, canon)

    (root / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    patch_md = generate_patch_markdown(old_md, root)

    assert "```codecrate-patch-meta" in patch_md
    assert "baseline_manifest_sha256" in patch_md
    assert "baseline_files_sha256" in patch_md


def test_apply_refuses_when_baseline_mismatch_detected(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    disc = discover_python_files(
        base, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    old_md = render_markdown(pack, canon)

    cur = tmp_path / "cur"
    shutil.copytree(base, cur)
    (cur / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")

    patch_md = tmp_path / "patch.md"
    patch_md.write_text(generate_patch_markdown(old_md, cur), encoding="utf-8")

    apply_root = tmp_path / "apply"
    shutil.copytree(base, apply_root)
    (apply_root / "a.py").write_text("def f():\n    return 999\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["apply", str(patch_md), str(apply_root)])

    assert "baseline does not match" in str(excinfo.value)


def test_generate_patch_strict_encoding_fails_on_invalid_utf8(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    disc = discover_python_files(
        root, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    old_md = render_markdown(pack, canon)

    (root / "a.py").write_bytes(b"def f():\n    return '\xff'\n")

    with pytest.raises(ValueError) as excinfo:
        generate_patch_markdown(old_md, root, encoding_errors="strict")

    assert "Failed to decode UTF-8" in str(excinfo.value)


def test_apply_file_diffs_strict_encoding_fails_on_invalid_utf8(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "a.py"
    target.write_bytes(b"a\n\xff\n")

    diff_text = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n a\n-x\n+B\n"
    diffs = parse_unified_diff(diff_text)

    with pytest.raises(ValueError) as excinfo:
        apply_file_diffs(diffs, root, encoding_errors="strict")

    assert "failed to decode UTF-8" in str(excinfo.value)
