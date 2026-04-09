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
    assert payload["pack"]["output_files"] == ["context.md"]

    repos = payload["repositories"]
    assert len(repos) == 1
    repo = repos[0]
    assert repo["split_policy"] == "preserve"
    assert repo["layout"] == "full"
    assert repo["markdown_path"] == "context.md"
    assert repo["parts"] == [
        {
            "part_id": f"{repo['slug']}:pack",
            "path": "context.md",
            "kind": "pack",
            "repo_slug": repo["slug"],
            "char_count": repo["parts"][0]["char_count"],
            "token_estimate": repo["parts"][0]["token_estimate"],
            "is_oversized": False,
            "contains": {
                "files": ["a.py"],
                "canonical_ids": [],
                "section_types": ["Pack"],
            },
        }
    ]

    files = repo["files"]
    assert len(files) == 1
    assert files[0]["path"] == "a.py"
    assert files[0]["language"] == "python"
    assert files[0]["language_detected"] == "python"
    assert files[0]["module"] == "a"
    assert files[0]["line_count"] == 3
    assert files[0]["is_stubbed"] is False
    assert files[0]["is_redacted"] is False
    assert files[0]["is_binary_skipped"] is False
    assert files[0]["is_safety_skipped"] is False
    assert files[0]["symbol_backend_requested"] == "python-ast"
    assert files[0]["symbol_backend_used"] == "python-ast"
    assert files[0]["symbol_extraction_status"] == "ok"
    assert files[0]["anchors"] == {"index": "file-a-py", "source": "src-a-py"}
    assert len(files[0]["symbol_ids"]) == 1
    assert files[0]["part_path"] == "context.md"

    symbols = repo["symbols"]
    assert len(symbols) == 1
    assert symbols[0]["qualname"] == "alpha"
    assert symbols[0]["path"] == "a.py"
    assert symbols[0]["has_marker"] is False
    assert symbols[0]["is_deduped"] is False
    assert symbols[0]["file_anchor"] == "src-a-py"
    assert symbols[0]["file_part"] == "context.md"
    assert "canonical_part" not in symbols[0]


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
    assert any(part["kind"] == "index" for part in repo["parts"])
    assert any(part["kind"] == "part" for part in repo["parts"])
    assert repo["files"][0]["part_path"].startswith("context.part")
    assert repo["symbols"][0]["file_part"].startswith("context.part")
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
    assert repo["files"][0]["is_stubbed"] is True
    assert repo["files"][0]["sha256_stubbed"]

    symbols = repo["symbols"]
    assert len(symbols) == 3
    assert all(symbol["has_marker"] is True for symbol in symbols)
    assert all(symbol["canonical_anchor"].startswith("func-") for symbol in symbols)
    assert all(
        symbol["canonical_part"].startswith("context.part") for symbol in symbols
    )
    assert all(symbol["file_part"].startswith("context.part") for symbol in symbols)
    assert any(part["is_oversized"] for part in repo["parts"] if part["kind"] == "part")


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
