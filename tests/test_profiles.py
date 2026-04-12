from __future__ import annotations

import json
from pathlib import Path

from codecrate.cli import main


def test_pack_profile_hybrid_implies_index_json(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--profile", "hybrid"])

    assert out_path.exists()
    index_path = tmp_path / "context.index.json"
    assert index_path.exists()
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["format"] == "codecrate.index-json.v1"
    assert payload["mode"] == "full"
    assert payload["pack"]["profiles"] == ["hybrid"]
    assert payload["pack"]["index_json_mode"] == "full"
    assert payload["repositories"][0]["profile"] == "hybrid"


def test_pack_profile_agent_implies_compact_nav_and_normalized_index_json(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--profile", "agent"])

    text = out_path.read_text(encoding="utf-8")
    assert '<a id="src-' in text
    assert '<a id="file-' in text
    assert "— [jump](#src-" not in text
    assert "[jump to index](#file-" not in text
    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    assert payload["format"] == "codecrate.index-json.v3"
    assert payload["mode"] == "normalized"
    assert payload["pack"]["index_json_mode"] == "normalized"
    assert payload["repositories"][0]["locator_space"] == "markdown"


def test_pack_profile_agent_explicit_overrides_win(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--profile",
            "agent",
            "--nav-mode",
            "full",
            "--no-index-json",
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert '<a id="src-' in text
    assert "[jump to index](#file-" in text
    assert not (tmp_path / "context.index.json").exists()


def test_pack_profile_agent_explicit_index_json_keeps_full_mode(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--profile",
            "agent",
            "--index-json",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    assert payload["format"] == "codecrate.index-json.v1"
    assert payload["mode"] == "full"


def test_pack_profile_portable_implies_full_layout_without_index_json(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--profile", "portable"])

    text = out_path.read_text(encoding="utf-8")
    assert "Layout: `full`" in text
    assert not (tmp_path / "context.index.json").exists()


def test_pack_profile_from_config_is_used(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "codecrate.toml").write_text(
        '[codecrate]\nprofile = "agent"\n',
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path)])

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "normalized"
    assert payload["repositories"][0]["locator_space"] == "markdown"
