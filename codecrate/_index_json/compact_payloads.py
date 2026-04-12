from __future__ import annotations

from typing import Any

from ..analysis_metadata import build_symbol_purpose_text
from ..locators import (
    anchor_for_file_index,
    anchor_for_file_source,
    anchor_for_symbol,
    href,
)
from ..markdown import _fence_lang_for
from ..output_model import PackRun
from .common import (
    _class_id_maps,
    _file_reference_payload,
    _focus_inclusion_payload,
    _line_range,
    _semantic_symbol_payload,
    _should_include_canonical_ids,
    _strong_id_maps,
    _symbol_reference_payload,
)
from .ir import RepositoryIR
from .locators import _file_locator_payload, _symbol_locator_payload


def _compact_file_payload(
    ir: RepositoryIR,
    *,
    index_json_mode: str,
) -> list[dict[str, Any]]:
    run = ir.run
    payload: list[dict[str, Any]] = []
    for file_pack in sorted(
        run.pack_result.files,
        key=lambda item: item.path.relative_to(run.pack_result.root).as_posix(),
    ):
        rel = file_pack.path.relative_to(run.pack_result.root).as_posix()
        hrefs = {
            "source": href(ir.file_to_part.get(rel), anchor_for_file_source(rel)),
        }
        index_href = href(ir.file_index_to_part.get(rel), anchor_for_file_index(rel))
        if index_href is not None:
            hrefs["index"] = index_href
        file_entry: dict[str, Any] = {
            "path": rel,
            "part_path": ir.file_to_part.get(rel),
            "hrefs": hrefs,
            "language": _fence_lang_for(rel),
            "language_detected": file_pack.language_detected,
            "symbol_backend_requested": file_pack.symbol_backend_requested,
            "symbol_backend_used": file_pack.symbol_backend_used,
            "symbol_extraction_status": file_pack.symbol_extraction_status,
        }
        if ir.file_analysis_metadata:
            file_entry["module"] = file_pack.module or None
            file_entry["role_hint"] = ir.role_hints.get(rel)
            if run.options.index_json_include_file_summaries:
                summary = dict(ir.file_summaries.get(rel) or {})
                if not run.options.index_json_include_exports:
                    summary["exports"] = []
                file_entry["summary"] = summary or None
            if run.options.index_json_include_relationships:
                file_entry["relationships"] = ir.relationship_summaries.get(rel)
            if run.options.index_json_include_file_imports:
                file_entry["imports"] = ir.imports_by_source.get(rel, [])
            if run.options.index_json_include_exports:
                file_entry["exports"] = list(file_pack.exports)
            if run.options.index_json_include_module_docstrings:
                file_entry["module_docstring_lines"] = (
                    _line_range(*file_pack.module_docstring)
                    if file_pack.module_docstring is not None
                    else None
                )
        if index_json_mode == "compact":
            file_entry["language_family"] = (
                file_pack.language_detected or _fence_lang_for(rel)
            )
        if ir.markdown_path is not None and rel in ir.file_markdown_ranges:
            file_entry["markdown_lines"] = ir.file_markdown_ranges[rel]
        locators = _file_locator_payload(
            run,
            rel_path=rel,
            line_count=file_pack.line_count,
            markdown_path=ir.markdown_path,
            file_markdown_ranges=ir.file_markdown_ranges,
            reconstructed_root=ir.reconstructed_root,
            split_file_ranges=ir.split_file_ranges,
        )
        if locators:
            file_entry["locators"] = locators
        inclusion_reason = _focus_inclusion_payload(run, rel)
        if inclusion_reason is not None:
            file_entry["inclusion_reason"] = inclusion_reason
        if run.options.index_json_include_symbol_references:
            file_entry.update(_file_reference_payload(ir.reference_analysis, rel) or {})
        payload.append(file_entry)
    return payload


def _compact_symbol_payload(
    ir: RepositoryIR,
    *,
    index_json_mode: str,
    include_symbol_index_lines: bool,
) -> list[dict[str, Any]]:
    run = ir.run
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)
    _class_machine_ids, class_ids_by_path_qualname = _class_id_maps(run)
    include_canonical_ids = _should_include_canonical_ids(run)
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
        symbol_entry: dict[str, Any] = {
            "local_id": local_machine_ids[defn.local_id],
            "semantic_id": defn.semantic_id or None,
            "path": rel,
            "qualname": defn.qualname,
            "kind": defn.kind,
            "def_line": defn.def_line,
            "end_line": defn.end_line,
            "file_part": ir.file_to_part.get(rel),
            "file_href": href(ir.file_to_part.get(rel), anchor_for_file_source(rel)),
        }
        if ir.symbol_analysis_metadata:
            symbol_entry["owner_class"] = (
                class_ids_by_path_qualname.get(
                    (rel, defn.owner_class),
                    {},
                ).get("local_id")
                if defn.owner_class
                else None
            )
            symbol_entry["decorators"] = list(defn.decorators)
            if run.options.index_json_include_semantic:
                symbol_entry["semantic"] = _semantic_symbol_payload(defn)
            if run.options.index_json_include_purpose_text:
                symbol_entry["purpose_text"] = build_symbol_purpose_text(defn)
        if include_canonical_ids:
            symbol_entry["canonical_id"] = canonical_machine_ids[defn.id]
        if run.options.index_json_include_symbol_locators:
            locators = _symbol_locator_payload(
                run,
                rel_path=rel,
                def_line=defn.def_line,
                decorator_start=defn.decorator_start,
                body_start=defn.body_start,
                end_line=defn.end_line,
                local_id=defn.local_id,
                canonical_id=defn.id,
                markdown_path=ir.markdown_path,
                file_markdown_ranges=ir.file_markdown_ranges,
                symbol_index_ranges=ir.symbol_index_ranges,
                canonical_markdown_ranges=ir.canonical_markdown_ranges,
                reconstructed_root=ir.reconstructed_root,
                split_symbol_ranges=ir.split_symbol_ranges,
            )
            if locators:
                symbol_entry["locators"] = locators
        if (
            index_json_mode == "compact"
            and include_symbol_index_lines
            and ir.markdown_path is not None
        ):
            if defn.local_id in ir.symbol_index_ranges:
                symbol_entry["index_markdown_lines"] = ir.symbol_index_ranges[
                    defn.local_id
                ]
        if run.options.index_json_include_symbol_references:
            symbol_entry.update(
                _symbol_reference_payload(
                    ir.reference_analysis,
                    local_id=defn.local_id,
                    local_machine_ids=local_machine_ids,
                )
                or {}
            )
        if run.effective_layout == "stubs" and defn.id in run.canonical_sources:
            symbol_entry["canonical_part"] = ir.func_to_part.get(
                canonical_machine_ids[defn.id]
            )
            symbol_entry["canonical_href"] = href(
                ir.func_to_part.get(canonical_machine_ids[defn.id]),
                anchor_for_symbol(defn.id),
            )
            if (
                index_json_mode == "compact"
                and ir.markdown_path is not None
                and defn.id in ir.canonical_markdown_ranges
            ):
                symbol_entry["canonical_markdown_lines"] = ir.canonical_markdown_ranges[
                    defn.id
                ]
        symbols.append(symbol_entry)
    return symbols


def _compact_lookup_indexes(
    files_payload: list[dict[str, Any]],
    symbols_payload: list[dict[str, Any]],
    *,
    index_json_mode: str,
) -> dict[str, Any]:
    file_by_path: dict[str, dict[str, Any]] = {}
    part_by_file: dict[str, str | None] = {}
    file_by_symbol: dict[str, str] = {}
    symbol_by_local_id: dict[str, dict[str, Any]] = {}

    for file_entry in files_payload:
        path = str(file_entry.get("path") or "")
        if not path:
            continue
        hrefs = file_entry.get("hrefs") or {}
        lookup_entry: dict[str, Any] = {
            "part_path": file_entry.get("part_path"),
            "source_href": hrefs.get("source"),
        }
        if index_json_mode == "compact":
            lookup_entry["path"] = path
            lookup_entry["index_href"] = hrefs.get("index")
        file_by_path[path] = lookup_entry
        if index_json_mode == "compact":
            part_by_file[path] = file_entry.get("part_path")

    for symbol_entry in symbols_payload:
        path = str(symbol_entry.get("path") or "")
        local_id = str(symbol_entry.get("local_id") or "")
        if not path or not local_id:
            continue
        pointer = {
            "path": path,
            "qualname": symbol_entry.get("qualname"),
            "kind": symbol_entry.get("kind"),
            "file_part": symbol_entry.get("file_part"),
            "file_href": symbol_entry.get("file_href"),
        }
        if "canonical_id" in symbol_entry:
            pointer["canonical_id"] = symbol_entry.get("canonical_id")
        if "canonical_part" in symbol_entry:
            pointer["canonical_part"] = symbol_entry.get("canonical_part")
        if "canonical_href" in symbol_entry:
            pointer["canonical_href"] = symbol_entry.get("canonical_href")
        symbol_by_local_id[local_id] = pointer
        if index_json_mode == "compact":
            file_by_symbol[local_id] = path

    lookup: dict[str, Any] = {
        "file_by_path": file_by_path,
        "symbol_by_local_id": symbol_by_local_id,
    }
    if index_json_mode == "compact":
        lookup["part_by_file"] = part_by_file
        lookup["file_by_symbol"] = file_by_symbol
    return lookup


def _v2_feature_payload(run: PackRun, *, index_json_mode: str) -> dict[str, bool]:
    return {
        "lookup": bool(run.options.index_json_include_lookup),
        "symbol_index_lines": bool(
            index_json_mode == "compact"
            and run.options.index_json_include_symbol_index_lines
        ),
    }
