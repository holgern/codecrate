from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..analysis_metadata import (
    build_architecture_map,
    build_file_relationships,
    build_file_summaries,
    build_repository_guide,
    import_edges_payload,
    test_links_payload,
)
from ..formats import (
    INDEX_JSON_FORMAT_VERSION_V1,
    INDEX_JSON_FORMAT_VERSION_V2,
    INDEX_JSON_FORMAT_VERSION_V3,
    PACK_FORMAT_VERSION,
)
from ..ids import (
    ID_FORMAT_VERSION,
    MACHINE_ID_FORMAT_VERSION,
    SEMANTIC_ID_FORMAT_VERSION,
)
from ..output_model import PackRun
from ..token_budget import Part
from .common import _imports_by_source, _role_hints_by_path, _sort_rel_paths
from .compact_payloads import (
    _compact_file_payload,
    _compact_lookup_indexes,
    _compact_symbol_payload,
    _v2_feature_payload,
)
from .full_payloads import (
    _class_payload,
    _full_file_payload,
    _full_lookup_indexes,
    _full_symbol_payload,
)
from .locators import _repo_reconstructed_root, _unsplit_markdown_metadata
from .normalized_payloads import _normalized_repository_payload
from .parts import _part_metadata
from .repository import _repository_common_payload


def build_index_payload(
    *,
    codecrate_version: str,
    index_output_path: Path,
    pack_runs: list[PackRun],
    repo_output_parts: dict[str, list[Part]],
    is_split: bool,
    index_json_mode: str,
) -> dict[str, Any]:
    base_dir = index_output_path.parent.resolve()

    repositories: list[dict[str, Any]] = []
    all_output_files: list[str] = []
    for run in pack_runs:
        include_repository_analysis = any(
            (
                run.options.index_json_include_graph,
                run.options.index_json_include_test_links,
                run.options.index_json_include_guide,
            )
        )
        include_file_analysis = any(
            (
                run.options.analysis_metadata,
                run.options.index_json_include_file_imports,
                run.options.index_json_include_exports,
                run.options.index_json_include_module_docstrings,
                run.options.index_json_include_file_summaries,
                run.options.index_json_include_relationships,
            )
        )
        include_symbol_analysis = any(
            (
                run.options.analysis_metadata,
                run.options.index_json_include_classes,
                run.options.index_json_include_semantic,
                run.options.index_json_include_purpose_text,
            )
        )
        parts_input = repo_output_parts.get(run.slug, [])
        reconstructed_root = _repo_reconstructed_root(run, repo_count=len(pack_runs))
        (
            markdown_path,
            file_markdown_ranges,
            symbol_index_ranges,
            canonical_markdown_ranges,
        ) = _unsplit_markdown_metadata(
            run,
            repo_output_parts=parts_input,
            base_dir=base_dir,
        )
        parts, file_to_part, file_index_to_part, func_to_part = _part_metadata(
            run,
            repo_output_parts=parts_input,
            base_dir=base_dir,
        )
        import_edges = (
            import_edges_payload(run.pack_result)
            if run.options.index_json_include_graph
            else []
        )
        test_links = (
            test_links_payload(run.pack_result)
            if run.options.index_json_include_test_links
            else []
        )
        guide = (
            build_repository_guide(
                root=run.root,
                pack=run.pack_result,
                file_bytes=run.file_bytes,
            )
            if run.options.index_json_include_guide
            else {}
        )
        architecture = (
            build_architecture_map(root=run.root, pack=run.pack_result)
            if run.options.index_json_include_guide
            else {}
        )
        imports_by_source = (
            _imports_by_source(run)
            if run.options.index_json_include_file_imports
            else {}
        )
        role_hints = _role_hints_by_path(run) if include_file_analysis else {}
        relationship_summaries = (
            build_file_relationships(root=run.root, pack=run.pack_result)
            if run.options.index_json_include_relationships
            else {}
        )
        if relationship_summaries and not run.options.index_json_include_test_links:
            for relationship in relationship_summaries.values():
                relationship["related_tests"] = []
        file_summaries = (
            build_file_summaries(pack=run.pack_result)
            if run.options.index_json_include_file_summaries
            else {}
        )
        all_output_files.extend(part["path"] for part in parts)
        repo_markdown_path = parts[0]["path"] if len(parts) == 1 else None
        if index_json_mode == "full":
            files_payload = _full_file_payload(
                run,
                file_to_part=file_to_part,
                file_index_to_part=file_index_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                reconstructed_root=reconstructed_root,
                imports_by_source=imports_by_source,
                role_hints=role_hints,
                relationship_summaries=relationship_summaries,
                file_summaries=file_summaries,
                analysis_metadata=include_file_analysis,
            )
            classes_payload = (
                _class_payload(
                    run,
                    file_to_part=file_to_part,
                    markdown_path=markdown_path,
                    file_markdown_ranges=file_markdown_ranges,
                    include_display_ids=True,
                    include_purpose_text=run.options.index_json_include_purpose_text,
                )
                if run.options.index_json_include_classes
                else []
            )
            symbols_payload = _full_symbol_payload(
                run,
                file_to_part=file_to_part,
                func_to_part=func_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                symbol_index_ranges=symbol_index_ranges,
                canonical_markdown_ranges=canonical_markdown_ranges,
                reconstructed_root=reconstructed_root,
                analysis_metadata=include_symbol_analysis,
            )
            repository = {
                **_repository_common_payload(
                    run,
                    repo_markdown_path=repo_markdown_path,
                    repo_count=len(pack_runs),
                    parts=parts,
                    import_edges=import_edges,
                    test_links=test_links,
                    guide=guide,
                    architecture=architecture,
                    analysis_metadata=include_repository_analysis,
                ),
                "effective_layout": run.effective_layout,
                "contains_manifest": run.options.include_manifest,
                "files": files_payload,
                "symbols": symbols_payload,
                "lookup": _full_lookup_indexes(files_payload, symbols_payload),
            }
            if run.options.index_json_include_classes:
                repository["classes"] = classes_payload
        elif index_json_mode == "normalized":
            repository = _normalized_repository_payload(
                run,
                repo_markdown_path=repo_markdown_path,
                repo_count=len(pack_runs),
                parts=parts,
                file_to_part=file_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                symbol_index_ranges=symbol_index_ranges,
                canonical_markdown_ranges=canonical_markdown_ranges,
                reconstructed_root=reconstructed_root,
                import_edges=import_edges,
                test_links=test_links,
                guide=guide,
                architecture=architecture,
                imports_by_source=imports_by_source,
                role_hints=role_hints,
                relationship_summaries=relationship_summaries,
                file_summaries=file_summaries,
                file_analysis_metadata=include_file_analysis,
                symbol_analysis_metadata=include_symbol_analysis,
                repository_analysis_metadata=include_repository_analysis,
            )
        else:
            features = _v2_feature_payload(run, index_json_mode=index_json_mode)
            files_payload = _compact_file_payload(
                run,
                file_to_part=file_to_part,
                file_index_to_part=file_index_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                reconstructed_root=reconstructed_root,
                index_json_mode=index_json_mode,
                imports_by_source=imports_by_source,
                role_hints=role_hints,
                relationship_summaries=relationship_summaries,
                file_summaries=file_summaries,
                analysis_metadata=include_file_analysis,
            )
            classes_payload = (
                _class_payload(
                    run,
                    file_to_part=file_to_part,
                    markdown_path=markdown_path,
                    file_markdown_ranges=file_markdown_ranges,
                    include_display_ids=index_json_mode == "compact",
                    include_purpose_text=run.options.index_json_include_purpose_text,
                )
                if run.options.index_json_include_classes
                else []
            )
            symbols_payload = _compact_symbol_payload(
                run,
                file_to_part=file_to_part,
                func_to_part=func_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                symbol_index_ranges=symbol_index_ranges,
                canonical_markdown_ranges=canonical_markdown_ranges,
                reconstructed_root=reconstructed_root,
                index_json_mode=index_json_mode,
                include_symbol_index_lines=features["symbol_index_lines"],
                analysis_metadata=include_symbol_analysis,
            )
            repository = {
                **_repository_common_payload(
                    run,
                    repo_markdown_path=repo_markdown_path,
                    repo_count=len(pack_runs),
                    parts=parts,
                    import_edges=import_edges,
                    test_links=test_links,
                    guide=guide,
                    architecture=architecture,
                    analysis_metadata=include_repository_analysis,
                ),
                "index_json_features": features,
                "files": files_payload,
                "symbols": symbols_payload,
            }
            if run.options.index_json_include_classes:
                repository["classes"] = classes_payload
            if features["lookup"]:
                repository["lookup"] = _compact_lookup_indexes(
                    files_payload,
                    symbols_payload,
                    index_json_mode=index_json_mode,
                )
        repositories.append(repository)

    return {
        "format": (
            INDEX_JSON_FORMAT_VERSION_V1
            if index_json_mode == "full"
            else (
                INDEX_JSON_FORMAT_VERSION_V3
                if index_json_mode == "normalized"
                else INDEX_JSON_FORMAT_VERSION_V2
            )
        ),
        "mode": index_json_mode,
        "generated_by": {
            "tool": "codecrate",
            "version": codecrate_version,
        },
        "pack": {
            "format": PACK_FORMAT_VERSION,
            "root": ".",
            "is_split": is_split,
            "index_json_mode": index_json_mode,
            "repository_count": len(pack_runs),
            "display_id_format_version": ID_FORMAT_VERSION,
            "canonical_id_format_version": MACHINE_ID_FORMAT_VERSION,
            "semantic_id_format_version": SEMANTIC_ID_FORMAT_VERSION,
            "profiles": sorted({run.options.profile for run in pack_runs}),
            "output_files": _sort_rel_paths(all_output_files),
            "capabilities": {
                "has_manifest": all(run.options.include_manifest for run in pack_runs),
                "has_machine_header": all(
                    run.options.include_manifest for run in pack_runs
                ),
                "supports_unpack": all(
                    run.options.include_manifest for run in pack_runs
                ),
                "supports_patch": all(
                    run.options.include_manifest for run in pack_runs
                ),
                "supports_validate": all(
                    run.options.include_manifest for run in pack_runs
                ),
                "has_unsplit_line_ranges": not is_split,
                "has_split_line_ranges": False,
            },
            "authority": {
                "full_layout_source": "files",
                "stub_layout_source": "files+function-library+manifest",
                "patch_source": "unified-diff",
            },
        },
        "repositories": repositories,
    }


def write_index_json(
    path: Path, payload: dict[str, Any], *, pretty: bool = True
) -> Path:
    path.write_text(
        (
            json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False)
            if pretty
            else json.dumps(
                payload,
                separators=(",", ":"),
                sort_keys=False,
                ensure_ascii=False,
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return path
