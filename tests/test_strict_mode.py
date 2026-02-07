from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

from codecrate.discover import discover_python_files
from codecrate.markdown import render_markdown
from codecrate.packer import pack_repo
from codecrate.unpacker import unpack_to_dir
from codecrate.validate import validate_pack_markdown


def _make_stub_pack(root: Path) -> str:
    disc = discover_python_files(
        root,
        include=["**/*.py"],
        exclude=[],
        respect_gitignore=False,
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    return render_markdown(pack, canon, layout="stubs")


def _break_first_marker(markdown: str) -> str:
    return re.sub(
        r"FUNC:(?:v\d+:)?[0-9A-Fa-f]{8}", "BROKEN:DEADBEEF", markdown, count=1
    )


def test_unpack_strict_fails_on_unresolved_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    broken_md = _break_first_marker(_make_stub_pack(repo))
    out_dir = tmp_path / "out"

    with pytest.raises(ValueError):
        unpack_to_dir(broken_md, out_dir, strict=True)


def test_unpack_non_strict_warns_on_unresolved_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    broken_md = _break_first_marker(_make_stub_pack(repo))
    out_dir = tmp_path / "out"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        unpack_to_dir(broken_md, out_dir, strict=False)

    assert any("Unresolved marker mapping" in str(w.message) for w in caught)
    assert (out_dir / "a.py").exists()


def test_validate_strict_escalates_unresolved_marker_to_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    broken_md = _break_first_marker(_make_stub_pack(repo))

    non_strict = validate_pack_markdown(broken_md, strict=False)
    strict = validate_pack_markdown(broken_md, strict=True)

    assert any("Unresolved marker mapping" in w for w in non_strict.warnings)
    assert any("Unresolved marker mapping" in e for e in strict.errors)
