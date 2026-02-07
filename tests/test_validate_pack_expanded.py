from __future__ import annotations

import re
from pathlib import Path

from codecrate.cli import main
from codecrate.mdparse import parse_packed_markdown
from codecrate.validate import validate_pack_markdown


def _pack_text(tmp_path: Path, files: dict[str, str], *, layout: str = "auto") -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--layout", layout])
    return packed.read_text(encoding="utf-8")


def test_validate_detects_manifest_file_block_mismatch(tmp_path: Path) -> None:
    text = _pack_text(tmp_path, {"a.py": "def a():\n    return 1\n"})
    tampered = text.replace("## Files\n\n### `a.py`", "## Files\n\n### `other.py`", 1)

    report = validate_pack_markdown(tampered)
    assert any(
        "Manifest file missing from file blocks: a.py" in e for e in report.errors
    )
    assert any(
        "File block not present in manifest: other.py" in e for e in report.errors
    )


def test_validate_detects_duplicate_file_blocks(tmp_path: Path) -> None:
    text = _pack_text(tmp_path, {"a.py": "def a():\n    return 1\n"})
    start = text.index("### `a.py`")
    file_block = text[start:]
    tampered = text.rstrip() + "\n\n" + file_block

    report = validate_pack_markdown(tampered)
    assert any("Duplicate file block for a.py" in e for e in report.errors)


def test_validate_detects_orphan_function_library_entries(tmp_path: Path) -> None:
    text = _pack_text(tmp_path, {"a.py": "def a():\n    return 1\n"}, layout="stubs")
    orphan = "\n### DEADC0DE\n```python\ndef orphan():\n    return 1\n```\n\n"
    tampered = text.replace("## Files\n\n", orphan + "## Files\n\n", 1)

    report = validate_pack_markdown(tampered)
    assert any("Orphan function-library entry: id=DEADC0DE" in e for e in report.errors)


def test_validate_reports_repo_scope_marker_collisions(tmp_path: Path) -> None:
    text = _pack_text(
        tmp_path,
        {
            "a.py": "def a():\n    return 1\n",
            "b.py": "def b():\n    return 2\n",
        },
        layout="stubs",
    )
    ids = re.findall(r"FUNC:v1:([0-9A-F]{8})", text)
    assert len(ids) >= 2
    tampered = text.replace(f"FUNC:v1:{ids[1]}", f"FUNC:v1:{ids[0]}", 1)

    report = validate_pack_markdown(tampered)
    assert any("Repo-scope marker collision" in w for w in report.warnings)


def test_manifest_marks_defs_with_has_marker_for_nested_defs(tmp_path: Path) -> None:
    text = _pack_text(
        tmp_path,
        {
            "a.py": (
                "def outer():\n    def inner():\n        return 1\n    return inner()\n"
            )
        },
        layout="stubs",
    )
    packed = parse_packed_markdown(text)
    defs = packed.manifest["files"][0]["defs"]

    assert any(d.get("has_marker") is True for d in defs)
    assert any(d.get("has_marker") is False for d in defs)

    report = validate_pack_markdown(text)
    assert not any("Missing FUNC marker" in w for w in report.warnings)


def test_validate_requires_exactly_one_machine_header_block(tmp_path: Path) -> None:
    text = _pack_text(tmp_path, {"a.py": "def a():\n    return 1\n"})

    # Missing machine header
    no_header = text.replace("```codecrate-machine-header", "```not-header", 1)
    report_missing = validate_pack_markdown(no_header)
    assert any(
        "expected exactly one codecrate-machine-header block" in e
        for e in report_missing.errors
    )

    # Duplicate machine header
    start = text.index("```codecrate-machine-header")
    end = text.index("```", start + 3)
    end = text.index("\n", end) + 1
    header_block = text[start:end]
    duplicate = text.rstrip() + "\n\n" + header_block
    report_dup = validate_pack_markdown(duplicate)
    assert any(
        "expected exactly one codecrate-machine-header block" in e
        for e in report_dup.errors
    )


def test_validate_checks_manifest_format_versions(tmp_path: Path) -> None:
    text = _pack_text(tmp_path, {"a.py": "def a():\n    return 1\n"})
    tampered = text.replace(
        '"format": "codecrate.v4"',
        '"format": "codecrate.v9"',
        1,
    ).replace(
        '"id_format_version": "sha1-8-upper:v1"',
        '"id_format_version": "bad:v0"',
        1,
    )

    report = validate_pack_markdown(tampered)
    assert any("Unsupported manifest format" in e for e in report.errors)
    assert any("Unsupported id_format_version" in e for e in report.errors)
