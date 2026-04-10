from __future__ import annotations

import json
from pathlib import Path

from codecrate.cli import main
from codecrate.model import DefRef
from codecrate.symbol_backend import SymbolExtractionResult


def test_pack_index_json_default_path_single_repo(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--index-json"])

    index_path = tmp_path / "context.index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))

    assert payload["format"] == "codecrate.index-json.v1"
    assert payload["pack"]["format"] == "codecrate.v4"
    assert payload["pack"]["is_split"] is False
    assert payload["pack"]["display_id_format_version"] == "sha1-8-upper:v1"
    assert payload["pack"]["canonical_id_format_version"] == "sha256-64-lower:v1"
    assert payload["pack"]["output_files"] == ["context.md"]
    assert payload["pack"]["capabilities"] == {
        "has_manifest": True,
        "has_machine_header": True,
        "supports_unpack": True,
        "supports_patch": True,
        "supports_validate": True,
        "has_unsplit_line_ranges": True,
        "has_split_line_ranges": False,
    }
    assert payload["pack"]["authority"] == {
        "full_layout_source": "files",
        "stub_layout_source": "files+function-library+manifest",
        "patch_source": "unified-diff",
    }

    repos = payload["repositories"]
    assert len(repos) == 1
    repo = repos[0]
    assert repo["split_policy"] == "preserve"
    assert repo["layout"] == "full"
    assert repo["effective_layout"] == "full"
    assert repo["nav_mode"] == "compact"
    assert repo["locator_mode"] == "anchors+line-ranges"
    assert repo["has_manifest"] is True
    assert repo["has_machine_header"] is True
    assert repo["markdown_path"] == "context.md"
    assert repo["parts"][0]["part_id"] == f"{repo['slug']}:pack"
    assert repo["parts"][0]["path"] == "context.md"
    assert repo["parts"][0]["kind"] == "pack"
    assert repo["parts"][0]["repo_slug"] == repo["slug"]
    assert repo["parts"][0]["is_oversized"] is False
    assert repo["parts"][0]["line_count"] > 0
    assert len(repo["parts"][0]["sha256_content"]) == 64
    assert repo["parts"][0]["contains"] == {
        "files": ["a.py"],
        "canonical_ids": [],
        "display_canonical_ids": [],
        "section_types": ["Pack"],
    }

    files = repo["files"]
    assert len(files) == 1
    assert files[0]["path"] == "a.py"
    assert files[0]["language"] == "python"
    assert files[0]["fence_language"] == "python"
    assert files[0]["language_detected"] == "python"
    assert files[0]["language_family"] == "python"
    assert files[0]["module"] == "a"
    assert files[0]["line_count"] == 3
    assert files[0]["sha256_effective"] == files[0]["sha256_original"]
    assert files[0]["is_stubbed"] is False
    assert files[0]["is_redacted"] is False
    assert files[0]["is_binary_skipped"] is False
    assert files[0]["is_safety_skipped"] is False
    assert files[0]["symbol_backend_requested"] == "python-ast"
    assert files[0]["symbol_backend_used"] == "python-ast"
    assert files[0]["symbol_extraction_status"] == "ok"
    assert files[0]["hrefs"] == {
        "index": "context.md#file-a-py",
        "source": "context.md#src-a-py",
    }
    assert files[0]["anchors"] == {"index": "file-a-py", "source": "src-a-py"}
    assert files[0]["locators"] == {
        "mode": "anchors+line-ranges",
        "source_anchor_available": True,
        "index_anchor_available": True,
        "part_line_ranges_available": False,
        "unsplit_line_ranges_available": True,
    }
    assert files[0]["sizes"]["original"]["chars"] > 0
    assert files[0]["sizes"]["original"]["bytes"] > 0
    assert files[0]["sizes"]["original"]["token_estimate"] > 0
    assert files[0]["sizes"]["effective"]["chars"] > 0
    assert len(files[0]["symbol_ids"]) == 1
    assert len(files[0]["display_symbol_ids"]) == 1
    assert len(files[0]["symbol_canonical_ids"]) == 1
    assert len(files[0]["symbol_ids"][0]) == 64
    assert len(files[0]["symbol_canonical_ids"][0]) == 64
    assert len(files[0]["display_symbol_ids"][0]) == 8
    assert files[0]["part_path"] == "context.md"
    assert files[0]["markdown_path"] == "context.md"
    assert (
        files[0]["markdown_lines"]["start_line"]
        < files[0]["markdown_lines"]["end_line"]
    )

    symbols = repo["symbols"]
    assert len(symbols) == 1
    assert symbols[0]["display_id"] == files[0]["display_symbol_ids"][0]
    assert symbols[0]["canonical_id"] == files[0]["symbol_canonical_ids"][0]
    assert symbols[0]["display_local_id"] == files[0]["display_symbol_ids"][0]
    assert symbols[0]["local_id"] == files[0]["symbol_ids"][0]
    assert symbols[0]["ids"] == {
        "display_canonical_id": symbols[0]["display_id"],
        "display_occurrence_id": symbols[0]["display_local_id"],
        "machine_canonical_id": symbols[0]["canonical_id"],
        "machine_occurrence_id": symbols[0]["local_id"],
    }
    assert symbols[0]["qualname"] == "alpha"
    assert symbols[0]["path"] == "a.py"
    assert symbols[0]["has_marker"] is False
    assert symbols[0]["is_deduped"] is False
    assert symbols[0]["occurrence_count_for_canonical_id"] == 1
    assert symbols[0]["file_href"] == "context.md#src-a-py"
    assert symbols[0]["file_anchor"] == "src-a-py"
    assert symbols[0]["file_part"] == "context.md"
    assert symbols[0]["locators"] == {
        "mode": "anchors+line-ranges",
        "source_anchor_available": True,
        "index_anchor_available": True,
        "part_line_ranges_available": False,
        "unsplit_line_ranges_available": True,
    }
    assert symbols[0]["index_markdown_path"] == "context.md"
    assert symbols[0]["index_markdown_lines"]["start_line"] > 0
    assert symbols[0]["file_markdown_path"] == "context.md"
    assert "canonical_part" not in symbols[0]

    assert repo["lookup"]["symbols_by_file"] == {"a.py": files[0]["symbol_ids"]}
    assert repo["lookup"]["display_symbols_by_file"] == {
        "a.py": files[0]["display_symbol_ids"]
    }
    assert repo["lookup"]["file_by_symbol"] == {files[0]["symbol_ids"][0]: "a.py"}
    assert repo["lookup"]["file_by_display_symbol"] == {
        files[0]["display_symbol_ids"][0]: "a.py"
    }
    assert repo["lookup"]["file_by_path"] == {
        "a.py": {
            "path": "a.py",
            "part_path": "context.md",
            "index_href": "context.md#file-a-py",
            "source_href": "context.md#src-a-py",
        }
    }
    assert repo["lookup"]["part_by_file"] == {"a.py": "context.md"}
    assert (
        repo["lookup"]["symbol_by_local_id"][files[0]["symbol_ids"][0]]["path"]
        == "a.py"
    )
    assert (
        repo["lookup"]["symbol_by_display_local_id"][files[0]["display_symbol_ids"][0]][
            "path"
        ]
        == "a.py"
    )
    assert (
        repo["lookup"]["symbols_by_canonical_id"][symbols[0]["canonical_id"]][0][
            "path"
        ]
        == "a.py"
    )
    assert (
        repo["lookup"]["symbols_by_display_id"][symbols[0]["display_id"]][0]["path"]
        == "a.py"
    )


def test_pack_index_json_explicit_path_multi_repo(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    repo1.mkdir()
    repo2.mkdir()
    (repo1 / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (repo2 / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")

    out_md = tmp_path / "combined.md"
    out_json = tmp_path / "combined.index.json"
    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "-o",
            str(out_md),
            "--index-json",
            str(out_json),
        ]
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["pack"]["is_split"] is False
    assert payload["pack"]["output_files"] == ["combined.md"]

    repos = payload["repositories"]
    assert len(repos) == 2
    assert {repo["slug"] for repo in repos} == {"repo1", "repo2"}
    assert all(repo["markdown_path"] == "combined.md" for repo in repos)
    assert all(repo["parts"][0]["path"] == "combined.md" for repo in repos)
    assert {repo["files"][0]["path"] for repo in repos} == {"a.py", "b.py"}
    assert {tuple(repo["parts"][0]["contains"]["files"]) for repo in repos} == {
        ("a.py",),
        ("b.py",),
    }


def test_pack_index_json_includes_split_output_paths(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def alpha():\n" + "".join(f"    value_{i} = {i}\n" for i in range(80)),
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--split-max-chars",
            "250",
            "--index-json",
            "--split-allow-cut-files",
        ]
    )

    index_path = tmp_path / "context.index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))

    assert payload["pack"]["is_split"] is True
    assert "context.index.md" in payload["pack"]["output_files"]
    assert any(
        path.startswith("context.part") for path in payload["pack"]["output_files"]
    )

    repo = payload["repositories"][0]
    assert repo["split_policy"] == "cut-files"
    assert repo["markdown_path"] is None
    assert repo["locator_mode"] == "anchors"
    assert any(part["kind"] == "index" for part in repo["parts"])
    assert any(part["kind"] == "part" for part in repo["parts"])
    assert all(part["line_count"] > 0 for part in repo["parts"])
    assert all(len(part["sha256_content"]) == 64 for part in repo["parts"])
    assert repo["files"][0]["part_path"].startswith("context.part")
    assert repo["files"][0]["locators"]["mode"] == "anchors"
    assert repo["files"][0]["hrefs"]["source"].startswith("context.part")
    assert repo["symbols"][0]["file_part"].startswith("context.part")
    assert repo["symbols"][0]["locators"]["mode"] == "anchors"
    assert repo["symbols"][0]["file_href"].startswith("context.part")
    assert any(
        part["contains"]["files"] for part in repo["parts"] if part["kind"] == "part"
    )
    assert all(
        not part["is_oversized"] for part in repo["parts"] if part["kind"] == "part"
    )


def test_pack_index_json_split_stubs_tracks_canonical_parts(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def alpha():\n    return 1\n\n"
        "def beta():\n    return 2\n\n"
        "def gamma():\n    return 3\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--layout",
            "stubs",
            "--index-json",
            "--split-max-chars",
            "350",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]

    assert repo["split_policy"] == "preserve"
    assert repo["layout"] == "stubs"
    assert any(part["contains"]["canonical_ids"] for part in repo["parts"])
    assert any(part["contains"]["display_canonical_ids"] for part in repo["parts"])
    assert repo["files"][0]["is_stubbed"] is True
    assert repo["files"][0]["sha256_stubbed"]
    assert repo["files"][0]["sha256_effective"] == repo["files"][0]["sha256_stubbed"]

    symbols = repo["symbols"]
    assert len(symbols) == 3
    assert all(symbol["has_marker"] is True for symbol in symbols)
    assert all(symbol["canonical_anchor"].startswith("func-") for symbol in symbols)
    assert all(
        symbol["canonical_part"].startswith("context.part") for symbol in symbols
    )
    assert all(
        symbol["canonical_href"].startswith("context.part") for symbol in symbols
    )
    assert all(symbol["file_part"].startswith("context.part") for symbol in symbols)
    assert all(len(symbol["canonical_id"]) == 64 for symbol in symbols)
    assert all(len(symbol["display_id"]) == 8 for symbol in symbols)
    assert all(
        symbol["ids"]["machine_canonical_id"] == symbol["canonical_id"]
        for symbol in symbols
    )
    assert all("canonical_markdown_path" not in symbol for symbol in symbols)
    assert all("canonical_markdown_lines" not in symbol for symbol in symbols)
    assert any(part["is_oversized"] for part in repo["parts"] if part["kind"] == "part")


def test_pack_index_json_unsplit_stubs_include_canonical_markdown_lines(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--layout",
            "stubs",
            "--index-json",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    symbols = payload["repositories"][0]["symbols"]
    assert all(symbol["canonical_markdown_path"] == "context.md" for symbol in symbols)
    assert all(
        symbol["canonical_markdown_lines"]["start_line"] > 0 for symbol in symbols
    )


def test_pack_index_json_reports_non_python_backend_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "demo.java"
    path.write_text("class Demo {}\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    fake_def = DefRef(
        path=path,
        module="demo",
        qualname="Demo",
        id="ABCDEF12",
        local_id="ABCDEF12",
        kind="symbol_class",
        decorator_start=1,
        def_line=1,
        body_start=1,
        end_line=1,
    )

    def _fake_extract_non_python_symbols(**kwargs: object) -> SymbolExtractionResult:
        return SymbolExtractionResult(
            defs=[fake_def],
            backend_requested="tree-sitter",
            backend_used="tree-sitter",
            language_detected="java",
            extraction_status="ok",
        )

    monkeypatch.setattr(
        "codecrate.packer.extract_non_python_symbols",
        _fake_extract_non_python_symbols,
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--include",
            "*.java",
            "--symbol-backend",
            "tree-sitter",
            "--index-json",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    file_entry = payload["repositories"][0]["files"][0]
    assert file_entry["language_detected"] == "java"
    assert file_entry["symbol_backend_requested"] == "tree-sitter"
    assert file_entry["symbol_backend_used"] == "tree-sitter"
    assert file_entry["symbol_extraction_status"] == "ok"
