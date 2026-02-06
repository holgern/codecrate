from __future__ import annotations

from pathlib import Path

from codecrate.markdown import render_markdown
from codecrate.model import PackResult
from codecrate.packer import pack_repo


def _build_pack(root: Path) -> tuple[PackResult, dict[str, str]]:
    root.mkdir()
    (root / "a.py").write_text(
        "def f():\n    return 1\n\nclass C:\n    def m(self):\n        return 2\n",
        encoding="utf-8",
    )
    return pack_repo(root, [root / "a.py"], keep_docstrings=True, dedupe=False)


def test_how_to_use_is_adaptive_for_stubs_and_compact_nav(tmp_path: Path) -> None:
    pack, canonical = _build_pack(tmp_path / "repo")
    md = render_markdown(
        pack,
        canonical,
        layout="stubs",
        nav_mode="compact",
        include_manifest=True,
    )

    assert "## How to Use This Pack" in md
    assert "## Function Library" in md
    assert "Quick workflow" in md
    assert "stubbed functions" in md
    assert "Prefer minimal unified diffs" in md
    assert "Compact navigation mode is active" not in md
    assert "Manifest section is included" not in md
    assert "Line numbers" not in md


def test_how_to_use_is_adaptive_for_full_and_no_manifest(tmp_path: Path) -> None:
    pack, canonical = _build_pack(tmp_path / "repo")
    md = render_markdown(
        pack,
        canonical,
        layout="full",
        nav_mode="full",
        include_manifest=False,
    )

    assert "## Function Library" not in md
    assert "Quick workflow" in md
    assert "stubbed functions" not in md
    assert "Prefer minimal unified diffs" in md
    assert "Manifest is omitted in this pack" not in md
    assert "## Manifest" not in md
    assert "Line numbers" not in md
