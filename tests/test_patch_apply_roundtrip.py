from __future__ import annotations

from pathlib import Path

from codecrate.diffgen import generate_patch_markdown
from codecrate.udiff import apply_file_diffs, parse_unified_diff


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
        '  "format": "codecrate.v3",\n'
        '  "root": ".",\n'
        '  "files": [\n'
        '    {"path": "a.py", "module": "a", "line_count": 2, "classes": [],\n'
        '     "defs": [{"path": "a.py", "module": "a", "qualname": "f", '
        '"id": "ID", "local_id": "ID", "kind": "function", '
        '"decorator_start": 1, "def_line": 1, "body_start": 2, '
        '"end_line": 2, "doc_start": null, "doc_end": null, '
        '"is_single_line": false}]}\n'
        "  ]\n"
        "}\n"
        "```\n\n"
        "## Function Library\n\n"
        "### ID — `a.f` (a.py:L1–L2)\n"
        "```python\n"
        "def f():\n"
        "    return 1\n"
        "```\n\n"
        "## Files\n\n"
        "### `a.py` (L1–L2)\n"
        "```python\n"
        "def f():\n"
        "    # ↪ FUNC:ID (L1–L2)\n"
        "```\n"
    )

    # change current file
    f.write_text("def f():\n    return 2\n", encoding="utf-8")

    patch_md = generate_patch_markdown(old_md, root)
    diff_text = _extract_diff_blocks(patch_md)
    diffs = parse_unified_diff(diff_text)
    apply_file_diffs(diffs, root)

    assert f.read_text(encoding="utf-8") == "def f():\n    return 2\n"
