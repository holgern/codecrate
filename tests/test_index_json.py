from __future__ import annotations

import json
from pathlib import Path

from codecrate.cli import main
from codecrate.model import DefRef
from codecrate.symbol_backend import SymbolExtractionResult


def _make_ratio_guardrail_module(
    prefix: str, *, symbol_count: int, filler_lines: int
) -> str:
    body = ['"""Module docs.\\n' + ("Extra context.\\n" * filler_lines) + '"""\\n\\n']
    for i in range(symbol_count):
        body.append(
            f"class {prefix.title()}Class{i}:\\n"
            f"    def method_{i}(self, value: int) -> int:\\n"
            "        total = value\\n"
            + "".join(f"        total += {j}\\n" for j in range(filler_lines))
            + "        return total\\n\\n"
            f"def {prefix}_func_{i}(value: int) -> int:\\n"
            "    total = value\\n"
            + "".join(f"    total += {j}\\n" for j in range(filler_lines))
            + "    return total\\n\\n"
        )
    return "".join(body)


def test_pack_index_json_default_path_single_repo(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--index-json"])

    index_path = tmp_path / "context.index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))

    assert payload["format"] == "codecrate.index-json.v1"
    assert payload["mode"] == "full"
    assert payload["pack"]["format"] == "codecrate.v4"
    assert payload["pack"]["index_json_mode"] == "full"
    assert payload["pack"]["is_split"] is False
    assert payload["pack"]["display_id_format_version"] == "sha1-8-upper:v1"
    assert payload["pack"]["canonical_id_format_version"] == "sha256-64-lower:v1"
    assert payload["pack"]["semantic_id_format_version"] == "sha256-64-lower:v1"
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
    assert repo["locator_space"] == "markdown"
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
        "markdown": {
            "path": "context.md",
            "lines": {
                "start": files[0]["markdown_lines"]["start_line"],
                "end": files[0]["markdown_lines"]["end_line"],
            },
        },
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
    assert files[0]["summary"]["primary_symbols"] == ["alpha"]
    assert files[0]["relationships"] == {
        "depends_on": [],
        "used_by": [],
        "related_tests": [],
        "same_package_neighbors": [],
        "entrypoint_reachability": [],
    }

    symbols = repo["symbols"]
    assert len(symbols) == 1
    assert symbols[0]["display_id"] == files[0]["display_symbol_ids"][0]
    assert symbols[0]["canonical_id"] == files[0]["symbol_canonical_ids"][0]
    assert symbols[0]["display_local_id"] == files[0]["display_symbol_ids"][0]
    assert symbols[0]["local_id"] == files[0]["symbol_ids"][0]
    assert len(symbols[0]["semantic_id"]) == 64
    assert symbols[0]["ids"] == {
        "display_canonical_id": symbols[0]["display_id"],
        "display_occurrence_id": symbols[0]["display_local_id"],
        "machine_canonical_id": symbols[0]["canonical_id"],
        "machine_occurrence_id": symbols[0]["local_id"],
        "semantic_id": symbols[0]["semantic_id"],
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
        "markdown": {
            "path": "context.md",
            "file_lines": {
                "start": files[0]["markdown_lines"]["start_line"],
                "end": files[0]["markdown_lines"]["end_line"],
            },
            "symbol_index_lines": {
                "start": symbols[0]["index_markdown_lines"]["start_line"],
                "end": symbols[0]["index_markdown_lines"]["end_line"],
            },
        },
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
        repo["lookup"]["symbols_by_canonical_id"][symbols[0]["canonical_id"]][0]["path"]
        == "a.py"
    )
    assert (
        repo["lookup"]["symbols_by_display_id"][symbols[0]["display_id"]][0]["path"]
        == "a.py"
    )


def test_pack_index_json_includes_analysis_metadata(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "helpers.py").write_text(
        "def helper() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "service.py").write_text(
        '"""Service module."""\n'
        "from pkg import helpers\n"
        '__all__ = ["Service"]\n'
        "@decorator\n"
        "class Service(Base):\n"
        "    @staticmethod\n"
        "    def run() -> int:\n"
        "        return helpers.helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_service.py").write_text(
        "from pkg.service import Service\n\n"
        "def test_run() -> None:\n"
        "    assert Service.run() == 1\n",
        encoding="utf-8",
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]
    files_by_path = {entry["path"]: entry for entry in repo["files"]}

    service_file = files_by_path["pkg/service.py"]
    assert service_file["exports"] == ["Service"]
    assert service_file["module_docstring_lines"] == {"start_line": 1, "end_line": 1}
    assert service_file["role_hint"] is None
    assert service_file["imports"][0]["module"] == "pkg"
    assert service_file["imports"][0]["imported_name"] == "helpers"
    assert service_file["imports"][0]["target_path"] == "pkg/helpers.py"

    test_file = files_by_path["tests/test_service.py"]
    assert test_file["role_hint"] == "test"

    assert repo["classes"][0]["qualname"] == "Service"
    assert repo["classes"][0]["base_classes"] == ["Base"]
    assert repo["classes"][0]["decorators"] == ["decorator"]
    assert repo["classes"][0]["semantic_id"]

    method_symbol = next(
        symbol for symbol in repo["symbols"] if symbol["qualname"] == "Service.run"
    )
    assert method_symbol["owner_class"] == repo["classes"][0]["local_id"]
    assert method_symbol["decorators"] == ["staticmethod"]
    assert method_symbol["semantic"]["is_method"] is True
    assert method_symbol["semantic"]["is_staticmethod"] is True
    assert method_symbol["semantic"]["return_annotation"] == "int"
    assert method_symbol["semantic"]["parameters"] == []
    assert service_file["summary"]["primary_symbols"][:2] == ["Service", "Service.run"]
    assert service_file["summary"]["summary_text"].startswith("source file;")
    assert repo["classes"][0]["purpose_text"].startswith("public class;")
    assert (
        method_symbol["purpose_text"] == "public staticmethod on Service; returns int"
    )
    assert "pkg/helpers.py" in service_file["relationships"]["depends_on"]
    assert "tests/test_service.py" in service_file["relationships"]["related_tests"]

    assert repo["graph"]["import_edges"]
    assert {
        (entry["source_path"], entry["target_path"])
        for entry in repo["graph"]["import_edges"]
        if entry["target_path"] is not None
    } >= {
        ("pkg/service.py", "pkg/helpers.py"),
        ("tests/test_service.py", "pkg/service.py"),
    }
    assert repo["test_links"] == [
        {
            "source_path": "pkg/service.py",
            "test_path": "tests/test_service.py",
            "match_reason": "import-heuristic",
            "score": 120,
            "link_kind": "import",
            "evidence": [
                "import-edge",
                "imported-name:Service",
                "resolved-module:pkg.service",
            ],
        }
    ]


def test_pack_index_json_includes_architecture_map_when_detectable(
    tmp_path: Path,
) -> None:
    (tmp_path / "cli.py").write_text(
        "def main() -> int:\n    return 0\n", encoding="utf-8"
    )
    (tmp_path / "index_json.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "parse.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "security.py").write_text("VALUE = 1\n", encoding="utf-8")

    main(["pack", str(tmp_path), "-o", str(tmp_path / "context.md"), "--index-json"])

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    architecture = payload["repositories"][0]["architecture"]

    assert "cli_frontends" in architecture
    assert "format_schema_layer" in architecture
    assert "parsing_symbol_extraction_layer" in architecture
    assert "security_layer" in architecture


def test_pack_index_json_compact_v2_shape(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--index-json-mode",
            "compact",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]
    file_entry = repo["files"][0]
    symbol_entry = repo["symbols"][0]

    assert payload["format"] == "codecrate.index-json.v2"
    assert payload["mode"] == "compact"
    assert payload["pack"]["index_json_mode"] == "compact"
    assert repo["index_json_features"] == {
        "lookup": True,
        "symbol_index_lines": True,
    }
    assert set(repo["lookup"]) == {
        "file_by_path",
        "file_by_symbol",
        "part_by_file",
        "symbol_by_local_id",
    }
    assert repo["locator_space"] == "markdown"
    assert "effective_layout" not in repo
    assert "contains_manifest" not in repo
    assert "symbol_ids" not in file_entry
    assert "display_symbol_ids" not in file_entry
    assert "symbol_canonical_ids" not in file_entry
    assert "purpose_text" in symbol_entry
    assert file_entry["locators"] == {
        "markdown": {
            "path": "context.md",
            "lines": {
                "start": file_entry["markdown_lines"]["start_line"],
                "end": file_entry["markdown_lines"]["end_line"],
            },
        }
    }
    assert "anchors" not in file_entry
    assert "canonical_id" not in symbol_entry
    assert "display_id" not in symbol_entry
    assert "display_local_id" not in symbol_entry
    assert "ids" not in symbol_entry
    assert "index_markdown_lines" in symbol_entry
    assert symbol_entry["locators"] == {
        "markdown": {
            "path": "context.md",
            "file_lines": {
                "start": file_entry["markdown_lines"]["start_line"],
                "end": file_entry["markdown_lines"]["end_line"],
            },
            "symbol_index_lines": {
                "start": symbol_entry["index_markdown_lines"]["start_line"],
                "end": symbol_entry["index_markdown_lines"]["end_line"],
            },
        }
    }


def test_pack_index_json_minimal_v2_shape(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--index-json-mode",
            "minimal",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]
    file_entry = repo["files"][0]
    symbol_entry = repo["symbols"][0]

    assert payload["format"] == "codecrate.index-json.v2"
    assert payload["mode"] == "minimal"
    assert payload["pack"]["index_json_mode"] == "minimal"
    assert repo["index_json_features"] == {
        "lookup": True,
        "symbol_index_lines": False,
    }
    assert set(repo["lookup"]) == {"file_by_path", "symbol_by_local_id"}
    assert repo["locator_space"] == "markdown"
    assert "language_family" not in file_entry
    assert "index_markdown_lines" not in symbol_entry
    assert "canonical_id" not in symbol_entry
    assert "locators" in file_entry
    assert file_entry["locators"]["markdown"]["path"] == "context.md"
    assert symbol_entry["locators"]["markdown"]["path"] == "context.md"
    assert "symbol_index_lines" in symbol_entry["locators"]["markdown"]


def test_pack_index_json_normalized_v3_shape(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "service.py").write_text(
        '"""Service module."""\n'
        "from . import helpers\n"
        '__all__ = ["Service"]\n'
        "@decorator\n"
        "class Service(Base):\n"
        "    @staticmethod\n"
        "    def run() -> int:\n"
        "        return helpers.helper()\n",
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

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]
    tables = repo["tables"]
    file_entry = next(
        entry
        for entry in repo["files"]
        if tables["paths"][entry["p"]] == "pkg/service.py"
    )
    class_entry = repo["classes"][0]
    symbol_entry = next(
        entry
        for entry in repo["symbols"]
        if tables["qualnames"][entry["q"]] == "Service.run"
    )

    assert payload["format"] == "codecrate.index-json.v3"
    assert payload["mode"] == "normalized"
    assert payload["pack"]["index_json_mode"] == "normalized"
    assert repo["locator_space"] == "markdown"
    assert set(tables) == {"paths", "parts", "qualnames", "strings"}
    assert tables["paths"][file_entry["p"]] == "pkg/service.py"
    assert tables["strings"][file_entry["lang"]] == "python"
    assert tables["strings"][file_entry["mod"]] == "pkg.service"
    assert tables["paths"][file_entry["imp"][0]["t"]] == "pkg/helpers.py"
    assert tables["strings"][file_entry["exp"][0]] == "Service"
    assert file_entry["doc"] == [1, 1]
    assert tables["strings"][file_entry["sum"]["st"]].startswith("source file;")
    assert tables["qualnames"][class_entry["q"]] == "Service"
    assert tables["strings"][class_entry["b"][0]] == "Base"
    assert tables["strings"][class_entry["d"][0]] == "decorator"
    assert tables["strings"][class_entry["pt"]].startswith("public class;")
    assert tables["qualnames"][symbol_entry["q"]] == "Service.run"
    assert symbol_entry["o"] == class_entry["i"]
    assert tables["strings"][symbol_entry["d"][0]] == "staticmethod"
    assert (
        tables["strings"][symbol_entry["pt"]]
        == "public staticmethod on Service; returns int"
    )
    assert len(file_entry["loc"]["m"]) == 2
    assert file_entry["loc"]["m"][0] <= file_entry["loc"]["m"][1]
    assert symbol_entry["loc"]["m"]["f"] == file_entry["loc"]["m"]
    assert "i" in symbol_entry["loc"]["m"]
    assert repo["graph"]["import_edges"]


def test_pack_index_json_dual_locator_space_includes_markdown_and_reconstructed(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text(
        "@dec\ndef alpha():\n    return 1\n",
        encoding="utf-8",
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--index-json",
            "--locator-space",
            "dual",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]
    file_entry = repo["files"][0]
    symbol_entry = repo["symbols"][0]

    assert repo["locator_space"] == "reconstructed"
    assert repo["secondary_locator_space"] == "markdown"
    assert set(file_entry["locators"]) >= {
        "mode",
        "source_anchor_available",
        "index_anchor_available",
        "part_line_ranges_available",
        "unsplit_line_ranges_available",
        "markdown",
        "reconstructed",
    }
    assert file_entry["locators"]["reconstructed"]["path"] == "a.py"
    assert symbol_entry["locators"]["reconstructed"]["lines"] == {"start": 1, "end": 3}
    assert symbol_entry["locators"]["reconstructed"]["body_lines"] == {
        "start": 3,
        "end": 3,
    }
    assert symbol_entry["locators"]["markdown"]["path"] == "context.md"


def test_pack_index_json_auto_locator_space_uses_reconstructed_with_unpacker(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--profile",
            "agent",
            "--emit-standalone-unpacker",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]

    assert payload["mode"] == "normalized"
    assert repo["locator_space"] == "reconstructed"
    assert "secondary_locator_space" not in repo
    assert repo["files"][0]["loc"]["r"] == [1, 3]
    assert repo["symbols"][0]["loc"]["r"]["l"] == [1, 2]


def test_pack_index_json_portable_with_unpacker_and_sidecar_uses_reconstructed_locators(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "context.md"),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
            "--index-json-mode",
            "minimal",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]

    assert repo["locator_space"] == "reconstructed"
    assert repo["files"][0]["locators"]["reconstructed"]["path"] == "a.py"


def test_pack_index_json_compact_without_lookup_shape(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--index-json-mode",
            "compact",
            "--no-index-json-lookup",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]

    assert repo["index_json_features"] == {
        "lookup": False,
        "symbol_index_lines": True,
    }
    assert "lookup" not in repo


def test_pack_index_json_compact_without_symbol_index_lines_shape(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--index-json-mode",
            "compact",
            "--no-index-json-symbol-index-lines",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo = payload["repositories"][0]
    symbol_entry = repo["symbols"][0]

    assert repo["index_json_features"] == {
        "lookup": True,
        "symbol_index_lines": False,
    }
    assert "index_markdown_lines" not in symbol_entry


def test_pack_index_json_compact_minimal_and_normalized_are_smaller_than_full(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text(
        "def alpha():\n    return 1\n\n"
        "def beta():\n    return 2\n\n"
        "def gamma():\n    return 3\n",
        encoding="utf-8",
    )

    main(["pack", str(tmp_path), "-o", str(tmp_path / "full.md"), "--index-json"])
    full_payload = json.loads(
        (tmp_path / "full.index.json").read_text(encoding="utf-8")
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "compact.md"),
            "--index-json-mode",
            "compact",
        ]
    )
    compact_payload = json.loads(
        (tmp_path / "compact.index.json").read_text(encoding="utf-8")
    )

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "minimal.md"),
            "--index-json-mode",
            "minimal",
        ]
    )
    minimal_payload = json.loads(
        (tmp_path / "minimal.index.json").read_text(encoding="utf-8")
    )
    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(tmp_path / "normalized.md"),
            "--index-json-mode",
            "normalized",
        ]
    )
    normalized_payload = json.loads(
        (tmp_path / "normalized.index.json").read_text(encoding="utf-8")
    )

    full_text = json.dumps(full_payload, sort_keys=True)
    compact_text = json.dumps(compact_payload, sort_keys=True)
    minimal_text = json.dumps(minimal_payload, sort_keys=True)
    normalized_text = json.dumps(normalized_payload, sort_keys=True)

    assert len(compact_text) < len(full_text)
    assert len(minimal_text) < len(compact_text)
    assert len(normalized_text) < len(minimal_text)


def test_pack_profile_agent_normalized_sidecar_stays_below_markdown_ratio(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text(
        "# Demo\\n\\n" + ("Readme context line.\\n" * 400),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "guide.rst").write_text(
        "Guide\\n=====\\n\\n" + ("Guide context line.\\n" * 500),
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "a.py").write_text(
        _make_ratio_guardrail_module("alpha", symbol_count=8, filler_lines=220),
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "b.py").write_text(
        _make_ratio_guardrail_module("beta", symbol_count=8, filler_lines=220),
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_pkg.py").write_text(
        "".join(
            f"def test_case_{i}() -> None:\\n    assert {i} == {i}\\n\\n"
            for i in range(40)
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--profile",
            "agent",
            "--include-preset",
            "everything",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    markdown_bytes = len(out_path.read_bytes())
    index_json_bytes = len((tmp_path / "context.index.json").read_bytes())

    assert payload["mode"] == "normalized"
    assert index_json_bytes * 100 <= markdown_bytes * 60


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
