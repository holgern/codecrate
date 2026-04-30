from __future__ import annotations

import json
import re
from pathlib import Path

from codecrate.cli import main
from codecrate.markdown import render_markdown
from codecrate.model import PackResult
from codecrate.packer import pack_repo
from codecrate.validate import validate_pack_markdown


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
    assert "## Repository Guide" in md
    assert "## Machine Header" in md
    assert "## Function Library" in md
    assert "Quick workflow" in md
    assert "1. **Directory Tree** (L" in md
    assert "2. **Repository Guide** (L" in md
    assert "3. **Symbol Index** (L" in md
    assert "4. **Function Library** (L" in md
    assert "5. **Files** (L" in md
    assert "stubbed functions" in md
    assert "Prefer minimal unified diffs" in md
    assert "- Central modules: `a.py`" in md
    assert "FUNC:v1:" in md
    assert '"marker_format_version": "v1"' in md
    assert '"id_format_version": "sha1-8-upper:v1"' in md
    assert '"manifest_sha256":' in md
    assert "Compact navigation mode is active" not in md
    assert "Manifest section is included" not in md
    assert "Line numbers" not in md
    assert "<<CC:SECTION:" not in md


def test_how_to_use_is_adaptive_for_full_and_no_manifest(tmp_path: Path) -> None:
    pack, canonical = _build_pack(tmp_path / "repo")
    md = render_markdown(
        pack,
        canonical,
        layout="full",
        nav_mode="full",
        include_manifest=False,
    )

    assert "## Repository Guide" in md
    assert "## Function Library" not in md
    assert "## Machine Header" not in md
    assert "Quick workflow" in md
    assert "1. **Directory Tree** (L" in md
    assert "2. **Repository Guide** (L" in md
    assert "3. **Symbol Index** (L" in md
    assert "4. **Files** (L" in md
    assert "4. **Function Library**" not in md
    assert "stubbed functions" not in md
    assert "Prefer minimal unified diffs" in md
    assert "Manifest is omitted in this pack" not in md
    assert "## Manifest" not in md
    assert "Line numbers" not in md
    assert "<<CC:SECTION:" not in md


def _extract_json_fence(text: str, info: str) -> dict[str, object]:
    match = re.search(rf"```{re.escape(info)}\n(.*?)\n```", text, re.DOTALL)
    assert match is not None
    payload = json.loads(match.group(1))
    assert isinstance(payload, dict)
    return payload


def test_portable_agent_how_to_use_includes_standalone_reconstruction_command(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(repo),
            "-o",
            str(tmp_path / "context.md"),
            "--profile",
            "portable-agent",
        ]
    )

    text = (tmp_path / "context.md").read_text(encoding="utf-8")
    assert "Machine reconstruction" in text
    assert (
        "python3 -S context.unpack.py context.md -o reconstructed "
        "--check-machine-header --strict --fail-on-warning"
    ) in text
    assert "/usr/bin/python3" in text
    assert "Do not scrape file bodies from this markdown" in text
    assert "Do not use whole-file regex extraction" in text


def test_non_portable_how_to_use_does_not_claim_standalone_unpacker(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(["pack", str(repo), "-o", str(tmp_path / "context.md"), "--profile", "human"])

    text = (tmp_path / "context.md").read_text(encoding="utf-8")
    assert "Machine reconstruction" not in text
    assert "context.unpack.py" not in text
    assert "```codecrate-agent-workflow" not in text


def test_agent_workflow_block_is_emitted_for_portable_agent(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(repo),
            "-o",
            str(tmp_path / "context.md"),
            "--profile",
            "portable-agent",
        ]
    )

    text = (tmp_path / "context.md").read_text(encoding="utf-8")
    assert "```codecrate-agent-workflow" in text
    payload = _extract_json_fence(text, "codecrate-agent-workflow")
    assert payload["recommended_first_action"] == "reconstruct"
    assert payload["reconstruct_command"][:2] == ["python3", "-S"]
    assert payload["standalone_unpacker"] == "context.unpack.py"
    assert payload["index_json"] == "context.index.json"
    report = validate_pack_markdown(text, strict=True)
    assert report.errors == []
