from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from codecrate.cli import main
from codecrate.validate_index_json import validate_index_payload

_ANCHOR_RE = re.compile(r'<a id="([^"]+)"></a>')


def _load_payload(base_dir: Path) -> dict[str, Any]:
    return json.loads((base_dir / "context.index.json").read_text(encoding="utf-8"))


def _anchors_by_path(base_dir: Path, payload: dict[str, Any]) -> dict[str, set[str]]:
    anchors: dict[str, set[str]] = {}
    for rel_path in payload["pack"]["output_files"]:
        text = (base_dir / rel_path).read_text(encoding="utf-8")
        anchors[rel_path] = set(_ANCHOR_RE.findall(text))
    return anchors


def _assert_href_targets_exist(base_dir: Path, payload: dict[str, Any]) -> None:
    anchors = _anchors_by_path(base_dir, payload)
    for repo in payload["repositories"]:
        files_by_path = {entry["path"]: entry for entry in repo["files"]}
        symbols_by_id = {entry["local_id"]: entry for entry in repo["symbols"]}
        display_symbols_by_id = {
            entry["display_local_id"]: entry
            for entry in repo["symbols"]
            if "display_local_id" in entry
        }

        for file_entry in repo["files"]:
            for href in file_entry["hrefs"].values():
                assert href is not None
                rel_path, anchor = href.split("#", 1)
                assert anchor in anchors[rel_path]

        for symbol_entry in repo["symbols"]:
            rel_path, anchor = symbol_entry["file_href"].split("#", 1)
            assert anchor in anchors[rel_path]
            canonical_href = symbol_entry.get("canonical_href")
            if canonical_href is not None:
                canonical_path, canonical_anchor = canonical_href.split("#", 1)
                assert canonical_anchor in anchors[canonical_path]

        lookup = repo.get("lookup", {})

        if "symbols_by_file" in lookup:
            for path, symbol_ids in lookup["symbols_by_file"].items():
                assert path in files_by_path
                for symbol_id in symbol_ids:
                    assert symbols_by_id[symbol_id]["path"] == path

        if "display_symbols_by_file" in lookup:
            for path, symbol_ids in lookup["display_symbols_by_file"].items():
                assert path in files_by_path
                for symbol_id in symbol_ids:
                    assert display_symbols_by_id[symbol_id]["path"] == path


def test_index_json_hrefs_match_rendered_markdown_full_nav(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(["pack", str(tmp_path), "-o", str(tmp_path / "context.md"), "--index-json"])

    payload = _load_payload(tmp_path)
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_hrefs_match_rendered_markdown_compact_nav(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--profile",
            "agent",
            "--index-json",
        ]
    )

    payload = _load_payload(tmp_path)
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_compact_v2_hrefs_and_validation(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json-mode",
            "compact",
        ]
    )

    payload = _load_payload(tmp_path)
    assert payload["format"] == "codecrate.index-json.v2"
    assert payload["mode"] == "compact"
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_minimal_v2_hrefs_and_validation(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json-mode",
            "minimal",
        ]
    )

    payload = _load_payload(tmp_path)
    assert payload["format"] == "codecrate.index-json.v2"
    assert payload["mode"] == "minimal"
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_normalized_v3_validation(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "service.py").write_text(
        "from .helpers import helper\n\n" "def run() -> int:\n" "    return helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "helpers.py").write_text(
        "def helper() -> int:\n    return 1\n",
        encoding="utf-8",
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json-mode",
            "normalized",
        ]
    )

    payload = _load_payload(tmp_path)
    assert payload["format"] == "codecrate.index-json.v3"
    assert payload["mode"] == "normalized"
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_compact_v2_without_lookup_hrefs_and_validation(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json-mode",
            "compact",
            "--no-index-json-lookup",
        ]
    )

    payload = _load_payload(tmp_path)
    assert payload["repositories"][0]["index_json_features"] == {
        "lookup": False,
        "symbol_index_lines": True,
    }
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_compact_v2_without_symbol_lines_hrefs_and_validation(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json-mode",
            "compact",
            "--no-index-json-symbol-index-lines",
        ]
    )

    payload = _load_payload(tmp_path)
    assert payload["repositories"][0]["index_json_features"] == {
        "lookup": True,
        "symbol_index_lines": False,
    }
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_minimal_v2_without_lookup_hrefs_and_validation(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json-mode",
            "minimal",
            "--no-index-json-lookup",
        ]
    )

    payload = _load_payload(tmp_path)
    assert payload["repositories"][0]["index_json_features"] == {
        "lookup": False,
        "symbol_index_lines": False,
    }
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []


def test_index_json_split_locators_match_split_outputs(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def alpha():\n    return 1\n\n"
        "def beta():\n    return 2\n\n"
        "def gamma():\n    return 3\n",
        encoding="utf-8",
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--layout",
            "stubs",
            "--split-max-chars",
            "350",
            "--index-json",
        ]
    )

    payload = _load_payload(tmp_path)
    _assert_href_targets_exist(tmp_path, payload)
    assert validate_index_payload(payload, base_dir=tmp_path) == []
