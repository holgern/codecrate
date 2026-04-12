from __future__ import annotations

from typing import Any

from ..locators import (
    anchor_for_file_index,
    anchor_for_file_source,
    anchor_for_symbol,
    href,
)
from ..markdown import _fence_lang_for
from ..output_model import PackRun
from ..tokens import approx_token_count
from .common import (
    _class_id_maps,
    _line_range,
    _manifest_defs_by_local_id,
    _manifest_files_by_path,
    _safety_flags_by_path,
    _semantic_symbol_payload,
    _strong_id_maps,
)
from .locators import _file_locator_payload, _symbol_locator_payload


def _full_file_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    file_index_to_part: dict[str, str],
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
    reconstructed_root: str | None,
    imports_by_source: dict[str, list[dict[str, Any]]],
    role_hints: dict[str, str | None],
    relationship_summaries: dict[str, dict[str, list[str]]],
    file_summaries: dict[str, dict[str, Any]],
    analysis_metadata: bool,
) -> list[dict[str, Any]]:
    manifest_by_path = _manifest_files_by_path(run)
    safety_by_path = _safety_flags_by_path(run)
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)

    payload: list[dict[str, Any]] = []
    for file_pack in sorted(
        run.pack_result.files,
        key=lambda item: item.path.relative_to(run.pack_result.root).as_posix(),
    ):
        rel = file_pack.path.relative_to(run.pack_result.root).as_posix()
        manifest_entry = manifest_by_path.get(rel, {})
        safety_flags = safety_by_path.get(
            rel,
            {
                "is_redacted": False,
                "is_binary_skipped": False,
                "is_safety_skipped": False,
            },
        )
        file_entry: dict[str, Any] = {
            "path": rel,
            "language": _fence_lang_for(rel),
            "fence_language": _fence_lang_for(rel),
            "language_detected": file_pack.language_detected,
            "language_family": file_pack.language_detected or _fence_lang_for(rel),
            "module": file_pack.module or None,
            "line_count": file_pack.line_count,
            "sha256_original": manifest_entry.get("sha256_original"),
            "sha256_effective": (
                manifest_entry.get("sha256_stubbed")
                if run.effective_layout == "stubs"
                else manifest_entry.get("sha256_original")
            ),
            "is_stubbed": run.effective_layout == "stubs",
            "is_redacted": safety_flags["is_redacted"],
            "is_binary_skipped": safety_flags["is_binary_skipped"],
            "is_safety_skipped": safety_flags["is_safety_skipped"],
            "symbol_backend_requested": file_pack.symbol_backend_requested,
            "symbol_backend_used": file_pack.symbol_backend_used,
            "symbol_extraction_status": file_pack.symbol_extraction_status,
            "part_path": file_to_part.get(rel),
            "hrefs": {
                "index": href(file_index_to_part.get(rel), anchor_for_file_index(rel)),
                "source": href(file_to_part.get(rel), anchor_for_file_source(rel)),
            },
            "anchors": {
                "index": anchor_for_file_index(rel),
                "source": anchor_for_file_source(rel),
            },
            "locators": {
                "mode": (
                    "anchors+line-ranges" if markdown_path is not None else "anchors"
                ),
                "source_anchor_available": True,
                "index_anchor_available": True,
                "part_line_ranges_available": False,
                "unsplit_line_ranges_available": markdown_path is not None,
                **_file_locator_payload(
                    run,
                    rel_path=rel,
                    line_count=file_pack.line_count,
                    markdown_path=markdown_path,
                    file_markdown_ranges=file_markdown_ranges,
                    reconstructed_root=reconstructed_root,
                ),
            },
            "sizes": {
                "original": {
                    "chars": len(file_pack.original_text),
                    "bytes": len(file_pack.original_text.encode("utf-8")),
                    "token_estimate": approx_token_count(file_pack.original_text),
                },
                "effective": {
                    "chars": len(
                        file_pack.stubbed_text
                        if run.effective_layout == "stubs"
                        else file_pack.original_text
                    ),
                    "bytes": len(
                        (
                            file_pack.stubbed_text
                            if run.effective_layout == "stubs"
                            else file_pack.original_text
                        ).encode("utf-8")
                    ),
                    "token_estimate": approx_token_count(
                        file_pack.stubbed_text
                        if run.effective_layout == "stubs"
                        else file_pack.original_text
                    ),
                },
            },
            "symbol_ids": [
                local_machine_ids[defn.local_id]
                for defn in sorted(
                    file_pack.defs,
                    key=lambda item: (item.def_line, item.qualname, item.local_id),
                )
            ],
            "display_symbol_ids": [
                defn.local_id
                for defn in sorted(
                    file_pack.defs,
                    key=lambda item: (item.def_line, item.qualname, item.local_id),
                )
            ],
            "symbol_canonical_ids": [
                canonical_machine_ids[defn.id]
                for defn in sorted(
                    file_pack.defs,
                    key=lambda item: (item.def_line, item.qualname, item.local_id),
                )
            ],
        }
        if analysis_metadata:
            file_entry["role_hint"] = role_hints.get(rel)
            summary = dict(file_summaries.get(rel) or {})
            if not run.options.index_json_include_exports:
                summary["exports"] = []
            file_entry["summary"] = summary or None
            file_entry["relationships"] = relationship_summaries.get(rel)
            if run.options.index_json_include_file_imports:
                file_entry["imports"] = imports_by_source.get(rel, [])
            if run.options.index_json_include_exports:
                file_entry["exports"] = list(file_pack.exports)
            if run.options.index_json_include_module_docstrings:
                file_entry["module_docstring_lines"] = (
                    _line_range(*file_pack.module_docstring)
                    if file_pack.module_docstring is not None
                    else None
                )
        if markdown_path is not None and rel in file_markdown_ranges:
            file_entry["markdown_path"] = markdown_path
            file_entry["markdown_lines"] = file_markdown_ranges[rel]
        sha256_stubbed = manifest_entry.get("sha256_stubbed")
        if isinstance(sha256_stubbed, str) and sha256_stubbed:
            file_entry["sha256_stubbed"] = sha256_stubbed
        payload.append(file_entry)
    return payload


def _class_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
    include_display_ids: bool,
) -> list[dict[str, Any]]:
    class_machine_ids, _ = _class_id_maps(run)
    payload: list[dict[str, Any]] = []
    for class_ref in sorted(
        run.pack_result.classes,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.class_line,
            item.qualname,
        ),
    ):
        rel = class_ref.path.relative_to(run.pack_result.root).as_posix()
        entry: dict[str, Any] = {
            "local_id": class_machine_ids[class_ref.id],
            "semantic_id": class_ref.semantic_id or None,
            "path": rel,
            "module": class_ref.module or None,
            "qualname": class_ref.qualname,
            "class_line": class_ref.class_line,
            "end_line": class_ref.end_line,
            "base_classes": list(class_ref.base_classes),
            "decorators": list(class_ref.decorators),
            "is_public": class_ref.is_public,
            "file_part": file_to_part.get(rel),
            "file_href": href(file_to_part.get(rel), anchor_for_file_source(rel)),
        }
        if include_display_ids:
            entry["display_local_id"] = class_ref.id
        if markdown_path is not None and rel in file_markdown_ranges:
            entry["file_markdown_path"] = markdown_path
            entry["file_markdown_lines"] = file_markdown_ranges[rel]
        payload.append(entry)
    return payload


def _full_symbol_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    func_to_part: dict[str, str],
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
    symbol_index_ranges: dict[str, dict[str, int]],
    canonical_markdown_ranges: dict[str, dict[str, int]],
    reconstructed_root: str | None,
    analysis_metadata: bool,
) -> list[dict[str, Any]]:
    manifest_defs_by_local_id = _manifest_defs_by_local_id(run)
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)
    _class_machine_ids, class_ids_by_path_qualname = _class_id_maps(run)
    occurrence_counts: dict[str, int] = {}
    for defn in run.pack_result.defs:
        machine_canonical_id = canonical_machine_ids[defn.id]
        occurrence_counts[machine_canonical_id] = (
            occurrence_counts.get(machine_canonical_id, 0) + 1
        )

    symbols: list[dict[str, Any]] = []
    for defn in sorted(
        run.pack_result.defs,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.def_line,
            item.qualname,
            item.local_id,
        ),
    ):
        rel = defn.path.relative_to(run.pack_result.root).as_posix()
        manifest_def = manifest_defs_by_local_id.get(defn.local_id, {})
        symbol_entry: dict[str, Any] = {
            "display_id": defn.id,
            "canonical_id": canonical_machine_ids[defn.id],
            "display_local_id": defn.local_id,
            "local_id": local_machine_ids[defn.local_id],
            "semantic_id": defn.semantic_id or None,
            "ids": {
                "display_canonical_id": defn.id,
                "display_occurrence_id": defn.local_id,
                "machine_canonical_id": canonical_machine_ids[defn.id],
                "machine_occurrence_id": local_machine_ids[defn.local_id],
                "semantic_id": defn.semantic_id or None,
            },
            "qualname": defn.qualname,
            "kind": defn.kind,
            "path": rel,
            "module": defn.module or None,
            "def_line": defn.def_line,
            "end_line": defn.end_line,
            "body_start": defn.body_start,
            "has_marker": bool(manifest_def.get("has_marker", False)),
            "is_deduped": defn.id != defn.local_id,
            "occurrence_count_for_canonical_id": occurrence_counts[
                canonical_machine_ids[defn.id]
            ],
            "file_part": file_to_part.get(rel),
            "file_href": href(file_to_part.get(rel), anchor_for_file_source(rel)),
            "file_anchor": anchor_for_file_source(rel),
            "locators": {
                "mode": (
                    "anchors+line-ranges" if markdown_path is not None else "anchors"
                ),
                "source_anchor_available": True,
                "index_anchor_available": defn.local_id in symbol_index_ranges,
                "part_line_ranges_available": False,
                "unsplit_line_ranges_available": markdown_path is not None,
                **_symbol_locator_payload(
                    run,
                    rel_path=rel,
                    def_line=defn.def_line,
                    decorator_start=defn.decorator_start,
                    body_start=defn.body_start,
                    end_line=defn.end_line,
                    local_id=defn.local_id,
                    canonical_id=defn.id,
                    markdown_path=markdown_path,
                    file_markdown_ranges=file_markdown_ranges,
                    symbol_index_ranges=symbol_index_ranges,
                    canonical_markdown_ranges=canonical_markdown_ranges,
                    reconstructed_root=reconstructed_root,
                ),
            },
        }
        if analysis_metadata:
            symbol_entry["owner_class"] = (
                class_ids_by_path_qualname.get(
                    (rel, defn.owner_class),
                    {},
                ).get("local_id")
                if defn.owner_class
                else None
            )
            symbol_entry["decorators"] = list(defn.decorators)
            symbol_entry["semantic"] = _semantic_symbol_payload(defn)
        if markdown_path is not None:
            if defn.local_id in symbol_index_ranges:
                symbol_entry["index_markdown_path"] = markdown_path
                symbol_entry["index_markdown_lines"] = symbol_index_ranges[
                    defn.local_id
                ]
            if rel in file_markdown_ranges:
                symbol_entry["file_markdown_path"] = markdown_path
                symbol_entry["file_markdown_lines"] = file_markdown_ranges[rel]
        if run.effective_layout == "stubs" and defn.id in run.canonical_sources:
            symbol_entry["canonical_part"] = func_to_part.get(
                canonical_machine_ids[defn.id]
            )
            symbol_entry["canonical_anchor"] = anchor_for_symbol(defn.id)
            symbol_entry["canonical_href"] = href(
                func_to_part.get(canonical_machine_ids[defn.id]),
                anchor_for_symbol(defn.id),
            )
            if markdown_path is not None and defn.id in canonical_markdown_ranges:
                symbol_entry["canonical_markdown_path"] = markdown_path
                symbol_entry["canonical_markdown_lines"] = canonical_markdown_ranges[
                    defn.id
                ]
        symbols.append(symbol_entry)
    return symbols


def _full_lookup_indexes(
    files_payload: list[dict[str, Any]],
    symbols_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    symbols_by_file: dict[str, list[str]] = {}
    display_symbols_by_file: dict[str, list[str]] = {}
    file_by_symbol: dict[str, str] = {}
    file_by_display_symbol: dict[str, str] = {}
    file_by_path: dict[str, dict[str, Any]] = {}
    part_by_file: dict[str, str | None] = {}
    symbol_by_local_id: dict[str, dict[str, Any]] = {}
    symbol_by_display_local_id: dict[str, dict[str, Any]] = {}
    symbols_by_canonical_id: dict[str, list[dict[str, Any]]] = {}
    symbols_by_display_id: dict[str, list[dict[str, Any]]] = {}

    for file_entry in files_payload:
        path = str(file_entry.get("path") or "")
        if not path:
            continue
        symbols_by_file[path] = list(file_entry.get("symbol_ids") or [])
        display_symbols_by_file[path] = list(file_entry.get("display_symbol_ids") or [])
        file_by_path[path] = {
            "path": path,
            "part_path": file_entry.get("part_path"),
            "index_href": file_entry.get("hrefs", {}).get("index"),
            "source_href": file_entry.get("hrefs", {}).get("source"),
        }
        part_by_file[path] = file_entry.get("part_path")

    for symbol_entry in symbols_payload:
        path = str(symbol_entry.get("path") or "")
        local_id = str(symbol_entry.get("local_id") or "")
        display_local_id = str(symbol_entry.get("display_local_id") or "")
        canonical_id = str(symbol_entry.get("canonical_id") or "")
        display_id = str(symbol_entry.get("display_id") or "")
        pointer = {
            "local_id": local_id,
            "display_local_id": display_local_id,
            "canonical_id": canonical_id,
            "display_id": display_id,
            "path": path,
            "qualname": symbol_entry.get("qualname"),
            "file_part": symbol_entry.get("file_part"),
            "file_href": symbol_entry.get("file_href"),
            "canonical_part": symbol_entry.get("canonical_part"),
            "canonical_href": symbol_entry.get("canonical_href"),
        }
        if path and local_id:
            file_by_symbol[local_id] = path
            symbol_by_local_id[local_id] = pointer
        if path and display_local_id:
            file_by_display_symbol[display_local_id] = path
            symbol_by_display_local_id[display_local_id] = pointer
        if canonical_id:
            symbols_by_canonical_id.setdefault(canonical_id, []).append(pointer)
        if display_id:
            symbols_by_display_id.setdefault(display_id, []).append(pointer)

    return {
        "symbols_by_file": symbols_by_file,
        "display_symbols_by_file": display_symbols_by_file,
        "file_by_symbol": file_by_symbol,
        "file_by_display_symbol": file_by_display_symbol,
        "file_by_path": file_by_path,
        "part_by_file": part_by_file,
        "symbol_by_local_id": symbol_by_local_id,
        "symbol_by_display_local_id": symbol_by_display_local_id,
        "symbols_by_canonical_id": symbols_by_canonical_id,
        "symbols_by_display_id": symbols_by_display_id,
    }
