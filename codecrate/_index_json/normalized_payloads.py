from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..analysis_metadata import build_class_purpose_text, build_symbol_purpose_text
from ..markdown import _fence_lang_for
from .common import (
    _class_id_maps,
    _file_reference_payload,
    _focus_inclusion_payload,
    _locator_line_range_from_markdown,
    _should_include_canonical_ids,
    _strong_id_maps,
    _symbol_reference_payload,
)
from .ir import RepositoryIR
from .locators import _includes_locator_space
from .repository import _repository_common_payload


def _table_index(
    value: str | None,
    *,
    table: list[str],
    lookup: dict[str, int],
) -> int | None:
    if not value:
        return None
    existing = lookup.get(value)
    if existing is not None:
        return existing
    index = len(table)
    table.append(value)
    lookup[value] = index
    return index


def _normalized_line_range(range_: tuple[int, int] | None) -> list[int] | None:
    if range_ is None:
        return None
    return [range_[0], range_[1]]


def _normalized_import_entry(
    import_entry: dict[str, Any],
    *,
    path_table: list[str],
    path_lookup: dict[str, int],
    string_table: list[str],
    string_lookup: dict[str, int],
) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    kind = _table_index(
        str(import_entry.get("kind") or ""),
        table=string_table,
        lookup=string_lookup,
    )
    if kind is not None:
        entry["k"] = kind
    module = _table_index(
        str(import_entry.get("module") or ""),
        table=string_table,
        lookup=string_lookup,
    )
    if module is not None:
        entry["m"] = module
    resolved_module = _table_index(
        str(import_entry.get("resolved_module") or ""),
        table=string_table,
        lookup=string_lookup,
    )
    if resolved_module is not None:
        entry["r"] = resolved_module
    imported_name = _table_index(
        str(import_entry.get("imported_name") or ""),
        table=string_table,
        lookup=string_lookup,
    )
    if imported_name is not None:
        entry["n"] = imported_name
    alias = _table_index(
        str(import_entry.get("alias") or ""),
        table=string_table,
        lookup=string_lookup,
    )
    if alias is not None:
        entry["a"] = alias
    line = import_entry.get("line")
    if isinstance(line, int):
        entry["l"] = line
    target_path = _table_index(
        str(import_entry.get("target_path") or ""),
        table=path_table,
        lookup=path_lookup,
    )
    if target_path is not None:
        entry["t"] = target_path
    return entry


def _normalized_analysis_payload(
    import_edges: list[dict[str, Any]],
    test_links: list[dict[str, Any]],
    guide: dict[str, list[str]],
    architecture: dict[str, list[str]],
    *,
    path_table: list[str],
    path_lookup: dict[str, int],
    string_table: list[str],
    string_lookup: dict[str, int],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if import_edges:
        payload["graph"] = {
            "import_edges": [
                {
                    key: value
                    for key, value in {
                        "s": _table_index(
                            str(edge.get("source_path") or ""),
                            table=path_table,
                            lookup=path_lookup,
                        ),
                        "t": _table_index(
                            str(edge.get("target_path") or ""),
                            table=path_table,
                            lookup=path_lookup,
                        ),
                        "m": _table_index(
                            str(edge.get("import_module") or ""),
                            table=string_table,
                            lookup=string_lookup,
                        ),
                        "r": _table_index(
                            str(edge.get("resolved_module") or ""),
                            table=string_table,
                            lookup=string_lookup,
                        ),
                        "n": _table_index(
                            str(edge.get("imported_name") or ""),
                            table=string_table,
                            lookup=string_lookup,
                        ),
                        "a": _table_index(
                            str(edge.get("alias") or ""),
                            table=string_table,
                            lookup=string_lookup,
                        ),
                        "k": _table_index(
                            str(edge.get("kind") or ""),
                            table=string_table,
                            lookup=string_lookup,
                        ),
                        "l": edge.get("line")
                        if isinstance(edge.get("line"), int)
                        else None,
                    }.items()
                    if value is not None
                }
                for edge in import_edges
            ]
        }
    if test_links:
        payload["test_links"] = [
            {
                key: value
                for key, value in {
                    "s": _table_index(
                        str(link.get("source_path") or ""),
                        table=path_table,
                        lookup=path_lookup,
                    ),
                    "t": _table_index(
                        str(link.get("test_path") or ""),
                        table=path_table,
                        lookup=path_lookup,
                    ),
                    "r": _table_index(
                        str(link.get("match_reason") or ""),
                        table=string_table,
                        lookup=string_lookup,
                    ),
                    "k": _table_index(
                        str(link.get("link_kind") or ""),
                        table=string_table,
                        lookup=string_lookup,
                    ),
                    "score": link.get("score")
                    if isinstance(link.get("score"), int)
                    else None,
                }.items()
                if value is not None
            }
            for link in test_links
        ]
    if guide:
        guide_payload: dict[str, list[int]] = {}
        for key, values in guide.items():
            if key == "main_workflows":
                indexed = _indexed_values(
                    values,
                    table=string_table,
                    lookup=string_lookup,
                )
            else:
                indexed = _indexed_values(
                    values,
                    table=path_table,
                    lookup=path_lookup,
                )
            if indexed:
                guide_payload[key] = indexed
        if guide_payload:
            payload["guide"] = guide_payload
    if architecture:
        architecture_payload: dict[str, list[int]] = {}
        for key, values in architecture.items():
            indexed = _indexed_values(
                values,
                table=path_table,
                lookup=path_lookup,
            )
            if indexed:
                architecture_payload[key] = indexed
        if architecture_payload:
            payload["architecture"] = architecture_payload
    return payload


def _indexed_values(
    values: Iterable[str],
    *,
    table: list[str],
    lookup: dict[str, int],
) -> list[int]:
    indexed: list[int] = []
    for value in values:
        index = _table_index(value, table=table, lookup=lookup)
        if index is not None:
            indexed.append(index)
    return indexed


def _normalized_parameters_payload(
    parameters: list[Any],
    *,
    string_table: list[str],
    string_lookup: dict[str, int],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for parameter in parameters:
        entry: dict[str, Any] = {
            "n": _table_index(parameter.name, table=string_table, lookup=string_lookup),
            "k": _table_index(parameter.kind, table=string_table, lookup=string_lookup),
            "d": parameter.has_default,
        }
        annotation = _table_index(
            parameter.annotation,
            table=string_table,
            lookup=string_lookup,
        )
        if annotation is not None:
            entry["a"] = annotation
        payload.append(
            {key: value for key, value in entry.items() if value is not None}
        )
    return payload


def _normalized_summary_payload(
    summary: dict[str, Any] | None,
    *,
    qualname_table: list[str],
    qualname_lookup: dict[str, int],
    string_table: list[str],
    string_lookup: dict[str, int],
) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    payload: dict[str, Any] = {}
    role = _table_index(summary.get("role"), table=string_table, lookup=string_lookup)
    if role is not None:
        payload["r"] = role
    primary_symbols = _indexed_values(
        [str(value) for value in summary.get("primary_symbols", [])],
        table=qualname_table,
        lookup=qualname_lookup,
    )
    if primary_symbols:
        payload["p"] = primary_symbols
    for key, compact_key in (
        ("imports_local", "il"),
        ("imports_external", "ie"),
    ):
        value = summary.get(key)
        if isinstance(value, int):
            payload[compact_key] = value
    exports = _indexed_values(
        [str(value) for value in summary.get("exports", [])],
        table=string_table,
        lookup=string_lookup,
    )
    if exports:
        payload["e"] = exports
    summary_text = _table_index(
        summary.get("summary_text"),
        table=string_table,
        lookup=string_lookup,
    )
    if summary_text is not None:
        payload["st"] = summary_text
    if summary.get("touches_io"):
        payload["io"] = True
    if summary.get("is_test"):
        payload["t"] = True
    return payload or None


def _normalized_relationships_payload(
    relationships: dict[str, list[str]] | None,
    *,
    path_table: list[str],
    path_lookup: dict[str, int],
) -> dict[str, Any] | None:
    if not isinstance(relationships, dict):
        return None
    payload: dict[str, Any] = {}
    for key, compact_key in (
        ("depends_on", "d"),
        ("used_by", "u"),
        ("related_tests", "t"),
        ("same_package_neighbors", "n"),
        ("entrypoint_reachability", "e"),
    ):
        values = _indexed_values(
            [str(value) for value in relationships.get(key, [])],
            table=path_table,
            lookup=path_lookup,
        )
        if values:
            payload[compact_key] = values
    return payload or None


def _normalized_file_reference_payload(
    *,
    ir: RepositoryIR,
    rel: str,
    path_table: list[str],
    path_lookup: dict[str, int],
) -> dict[str, Any] | None:
    if not ir.run.options.index_json_include_symbol_references:
        return None
    reference_payload = _file_reference_payload(ir.reference_analysis, rel)
    if reference_payload is None:
        return None
    encoded: dict[str, Any] = {}
    if reference_payload.get("references_out"):
        encoded["o"] = _indexed_values(
            [str(value) for value in reference_payload["references_out"]],
            table=path_table,
            lookup=path_lookup,
        )
    if reference_payload.get("references_in"):
        encoded["i"] = _indexed_values(
            [str(value) for value in reference_payload["references_in"]],
            table=path_table,
            lookup=path_lookup,
        )
    encoded["u"] = int(reference_payload["unresolved_references_count"])
    return encoded


def _normalized_file_locators(
    *,
    ir: RepositoryIR,
    rel: str,
    line_count: int,
    part_table: list[str],
    part_lookup: dict[str, int],
) -> dict[str, Any] | None:
    normalized_locators: dict[str, Any] = {}
    if _includes_locator_space(ir.run.options.locator_space, "markdown"):
        markdown_lines = _locator_line_range_from_markdown(
            ir.file_markdown_ranges.get(rel)
        )
        if ir.markdown_path is not None and markdown_lines is not None:
            normalized_locators["m"] = [
                markdown_lines["start"],
                markdown_lines["end"],
            ]
    if _includes_locator_space(ir.run.options.locator_space, "reconstructed"):
        normalized_locators["r"] = [1, line_count]
    split_part = ir.split_file_ranges.get(rel)
    if isinstance(split_part, dict):
        split_lines = split_part.get("lines")
        split_path_index = _table_index(
            split_part.get("path"),
            table=part_table,
            lookup=part_lookup,
        )
        if split_path_index is not None and isinstance(split_lines, dict):
            normalized_locators["sp"] = {
                "part": split_path_index,
                "l": [
                    int(split_lines.get("start", 0) or 0),
                    int(split_lines.get("end", 0) or 0),
                ],
            }
    return normalized_locators or None


def _normalized_symbol_reference_entry(
    *,
    ir: RepositoryIR,
    local_id: str,
    local_machine_ids: dict[str, str],
) -> dict[str, Any] | None:
    if not ir.run.options.index_json_include_symbol_references:
        return None
    references = _symbol_reference_payload(
        ir.reference_analysis,
        local_id=local_id,
        local_machine_ids=local_machine_ids,
    )
    if references is None:
        return None
    return {
        "o": list(references.get("references_out", [])),
        "i": list(references.get("references_in", [])),
        "u": int(references.get("unresolved_references_count", 0)),
    }


def _normalized_symbol_locators(
    *,
    ir: RepositoryIR,
    rel: str,
    defn: Any,
    part_table: list[str],
    part_lookup: dict[str, int],
) -> dict[str, Any] | None:
    normalized_locators: dict[str, Any] = {}
    if (
        ir.run.options.index_json_include_symbol_locators
        and _includes_locator_space(ir.run.options.locator_space, "markdown")
        and ir.markdown_path
    ):
        markdown_locator: dict[str, Any] = {}
        file_lines = _locator_line_range_from_markdown(ir.file_markdown_ranges.get(rel))
        if file_lines is not None:
            markdown_locator["f"] = [file_lines["start"], file_lines["end"]]
        index_lines = _locator_line_range_from_markdown(
            ir.symbol_index_ranges.get(defn.local_id)
        )
        if index_lines is not None:
            markdown_locator["i"] = [index_lines["start"], index_lines["end"]]
        canonical_lines = _locator_line_range_from_markdown(
            ir.canonical_markdown_ranges.get(defn.id)
        )
        if canonical_lines is not None:
            markdown_locator["c"] = [canonical_lines["start"], canonical_lines["end"]]
        if markdown_locator:
            normalized_locators["m"] = markdown_locator
    if ir.run.options.index_json_include_symbol_locators and _includes_locator_space(
        ir.run.options.locator_space, "reconstructed"
    ):
        start_line = defn.decorator_start or defn.def_line
        normalized_locators["r"] = {
            "l": [start_line, defn.end_line],
            "b": [defn.body_start, defn.end_line],
        }
    split_part = ir.split_symbol_ranges.get(defn.local_id)
    if isinstance(split_part, dict):
        split_path_index = _table_index(
            split_part.get("path"),
            table=part_table,
            lookup=part_lookup,
        )
        if split_path_index is not None:
            split_locator: dict[str, Any] = {"part": split_path_index}
            for src_key, dst_key in (
                ("lines", "l"),
                ("body_lines", "b"),
                ("file_lines", "f"),
                ("symbol_index_lines", "i"),
                ("canonical_lines", "c"),
            ):
                line_range = split_part.get(src_key)
                if isinstance(line_range, dict):
                    split_locator[dst_key] = [
                        int(line_range.get("start", 0) or 0),
                        int(line_range.get("end", 0) or 0),
                    ]
            normalized_locators["sp"] = split_locator
    return normalized_locators or None


def _normalized_file_payload(
    ir: RepositoryIR,
    *,
    path_table: list[str],
    path_lookup: dict[str, int],
    part_table: list[str],
    part_lookup: dict[str, int],
    qualname_table: list[str],
    qualname_lookup: dict[str, int],
    string_table: list[str],
    string_lookup: dict[str, int],
) -> list[dict[str, Any]]:
    run = ir.run
    files_payload: list[dict[str, Any]] = []
    for file_pack in sorted(
        run.pack_result.files,
        key=lambda item: item.path.relative_to(run.pack_result.root).as_posix(),
    ):
        rel = file_pack.path.relative_to(run.pack_result.root).as_posix()
        file_entry: dict[str, Any] = {
            "p": _table_index(rel, table=path_table, lookup=path_lookup),
        }
        part_index = _table_index(
            ir.file_to_part.get(rel),
            table=part_table,
            lookup=part_lookup,
        )
        if part_index is not None:
            file_entry["part"] = part_index
        language = _table_index(
            file_pack.language_detected or _fence_lang_for(rel),
            table=string_table,
            lookup=string_lookup,
        )
        if language is not None:
            file_entry["lang"] = language
        module = _table_index(
            file_pack.module or None,
            table=string_table,
            lookup=string_lookup,
        )
        if module is not None:
            file_entry["mod"] = module
        if ir.file_analysis_metadata:
            if run.options.index_json_include_file_imports:
                imports = ir.imports_by_source.get(rel, [])
                if imports:
                    file_entry["imp"] = [
                        _normalized_import_entry(
                            item,
                            path_table=path_table,
                            path_lookup=path_lookup,
                            string_table=string_table,
                            string_lookup=string_lookup,
                        )
                        for item in imports
                    ]
            if run.options.index_json_include_exports and file_pack.exports:
                file_entry["exp"] = _indexed_values(
                    file_pack.exports,
                    table=string_table,
                    lookup=string_lookup,
                )
            if run.options.index_json_include_module_docstrings:
                module_docstring = _normalized_line_range(file_pack.module_docstring)
                if module_docstring is not None:
                    file_entry["doc"] = module_docstring
            role_hint = _table_index(
                ir.role_hints.get(rel),
                table=string_table,
                lookup=string_lookup,
            )
            if role_hint is not None:
                file_entry["role"] = role_hint
            if run.options.index_json_include_file_summaries:
                summary = dict(ir.file_summaries.get(rel) or {})
                if not run.options.index_json_include_exports:
                    summary["exports"] = []
                normalized_summary = _normalized_summary_payload(
                    summary,
                    qualname_table=qualname_table,
                    qualname_lookup=qualname_lookup,
                    string_table=string_table,
                    string_lookup=string_lookup,
                )
                if normalized_summary is not None:
                    file_entry["sum"] = normalized_summary
            if run.options.index_json_include_relationships:
                normalized_relationships = _normalized_relationships_payload(
                    ir.relationship_summaries.get(rel),
                    path_table=path_table,
                    path_lookup=path_lookup,
                )
                if normalized_relationships is not None:
                    file_entry["rel"] = normalized_relationships
        inclusion_reason = _focus_inclusion_payload(run, rel)
        if inclusion_reason is not None:
            file_entry["inc"] = inclusion_reason
        reference_payload = _normalized_file_reference_payload(
            ir=ir,
            rel=rel,
            path_table=path_table,
            path_lookup=path_lookup,
        )
        if reference_payload is not None:
            file_entry["ref"] = reference_payload
        normalized_locators = _normalized_file_locators(
            ir=ir,
            rel=rel,
            line_count=file_pack.line_count,
            part_table=part_table,
            part_lookup=part_lookup,
        )
        if normalized_locators:
            file_entry["loc"] = normalized_locators
        files_payload.append(file_entry)
    return files_payload


def _normalized_class_payload(
    ir: RepositoryIR,
    *,
    path_table: list[str],
    path_lookup: dict[str, int],
    part_table: list[str],
    part_lookup: dict[str, int],
    qualname_table: list[str],
    qualname_lookup: dict[str, int],
    string_table: list[str],
    string_lookup: dict[str, int],
    include_purpose_text: bool,
) -> list[dict[str, Any]]:
    run = ir.run
    class_machine_ids, _ = _class_id_maps(run)
    classes_payload: list[dict[str, Any]] = []
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
            "i": class_machine_ids[class_ref.id],
            "sid": class_ref.semantic_id or None,
            "p": _table_index(rel, table=path_table, lookup=path_lookup),
            "q": _table_index(
                class_ref.qualname,
                table=qualname_table,
                lookup=qualname_lookup,
            ),
            "l1": class_ref.class_line,
            "l2": class_ref.end_line,
        }
        part_index = _table_index(
            ir.file_to_part.get(rel),
            table=part_table,
            lookup=part_lookup,
        )
        if part_index is not None:
            entry["part"] = part_index
        if class_ref.base_classes:
            entry["b"] = _indexed_values(
                class_ref.base_classes,
                table=string_table,
                lookup=string_lookup,
            )
        if class_ref.decorators:
            entry["d"] = _indexed_values(
                class_ref.decorators,
                table=string_table,
                lookup=string_lookup,
            )
        if include_purpose_text:
            purpose_text = _table_index(
                build_class_purpose_text(class_ref),
                table=string_table,
                lookup=string_lookup,
            )
            if purpose_text is not None:
                entry["pt"] = purpose_text
        if class_ref.is_public:
            entry["pub"] = True
        classes_payload.append(entry)
    return classes_payload


def _normalized_symbol_payload(
    ir: RepositoryIR,
    *,
    class_ids_by_path_qualname: dict[tuple[str, str], dict[str, str]],
    include_canonical_ids: bool,
    path_table: list[str],
    path_lookup: dict[str, int],
    part_table: list[str],
    part_lookup: dict[str, int],
    qualname_table: list[str],
    qualname_lookup: dict[str, int],
    string_table: list[str],
    string_lookup: dict[str, int],
) -> list[dict[str, Any]]:
    run = ir.run
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)
    symbols_payload: list[dict[str, Any]] = []
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
        entry: dict[str, Any] = {
            "i": local_machine_ids[defn.local_id],
            "sid": defn.semantic_id or None,
            "p": _table_index(rel, table=path_table, lookup=path_lookup),
            "q": _table_index(
                defn.qualname,
                table=qualname_table,
                lookup=qualname_lookup,
            ),
            "k": _table_index(
                defn.kind,
                table=string_table,
                lookup=string_lookup,
            ),
            "l1": defn.def_line,
            "l2": defn.end_line,
        }
        part_index = _table_index(
            ir.file_to_part.get(rel),
            table=part_table,
            lookup=part_lookup,
        )
        if part_index is not None:
            entry["part"] = part_index
        if include_canonical_ids:
            entry["c"] = canonical_machine_ids[defn.id]
        if ir.symbol_analysis_metadata:
            owner_class = (
                class_ids_by_path_qualname.get((rel, defn.owner_class), {}).get(
                    "local_id"
                )
                if defn.owner_class
                else None
            )
            if owner_class is not None:
                entry["o"] = owner_class
            if defn.decorators:
                entry["d"] = _indexed_values(
                    defn.decorators,
                    table=string_table,
                    lookup=string_lookup,
                )
            if run.options.index_json_include_semantic:
                signature = _table_index(
                    defn.signature_text,
                    table=string_table,
                    lookup=string_lookup,
                )
                if signature is not None:
                    entry["sig"] = signature
                return_annotation = _table_index(
                    defn.return_annotation,
                    table=string_table,
                    lookup=string_lookup,
                )
                if return_annotation is not None:
                    entry["ret"] = return_annotation
                parameters = _normalized_parameters_payload(
                    defn.parameters,
                    string_table=string_table,
                    string_lookup=string_lookup,
                )
                if parameters:
                    entry["params"] = parameters
                for key, enabled in (
                    ("meth", defn.is_method),
                    ("prop", defn.is_property),
                    ("cls", defn.is_classmethod),
                    ("stat", defn.is_staticmethod),
                    ("gen", defn.is_generator),
                    ("co", defn.is_coroutine),
                    ("pub", defn.is_public),
                    ("ovl", defn.is_overload),
                    ("abs", defn.is_abstractmethod),
                ):
                    if enabled:
                        entry[key] = True
            if run.options.index_json_include_purpose_text:
                purpose_text = _table_index(
                    build_symbol_purpose_text(defn),
                    table=string_table,
                    lookup=string_lookup,
                )
                if purpose_text is not None:
                    entry["pt"] = purpose_text
        references = _normalized_symbol_reference_entry(
            ir=ir,
            local_id=defn.local_id,
            local_machine_ids=local_machine_ids,
        )
        if references is not None:
            entry["ref"] = references
        normalized_locators = _normalized_symbol_locators(
            ir=ir,
            rel=rel,
            defn=defn,
            part_table=part_table,
            part_lookup=part_lookup,
        )
        if normalized_locators:
            entry["loc"] = normalized_locators
        symbols_payload.append(entry)
    return symbols_payload


def _normalized_repository_payload(
    ir: RepositoryIR,
) -> dict[str, Any]:
    run = ir.run
    path_table: list[str] = []
    path_lookup: dict[str, int] = {}
    part_table: list[str] = []
    part_lookup: dict[str, int] = {}
    qualname_table: list[str] = []
    qualname_lookup: dict[str, int] = {}
    string_table: list[str] = []
    string_lookup: dict[str, int] = {}
    for part in ir.parts:
        _table_index(
            str(part.get("path") or ""),
            table=part_table,
            lookup=part_lookup,
        )

    _, class_ids_by_path_qualname = _class_id_maps(run)
    include_canonical_ids = _should_include_canonical_ids(run)
    files_payload = _normalized_file_payload(
        ir,
        path_table=path_table,
        path_lookup=path_lookup,
        part_table=part_table,
        part_lookup=part_lookup,
        qualname_table=qualname_table,
        qualname_lookup=qualname_lookup,
        string_table=string_table,
        string_lookup=string_lookup,
    )
    classes_payload = (
        _normalized_class_payload(
            ir,
            path_table=path_table,
            path_lookup=path_lookup,
            part_table=part_table,
            part_lookup=part_lookup,
            qualname_table=qualname_table,
            qualname_lookup=qualname_lookup,
            string_table=string_table,
            string_lookup=string_lookup,
            include_purpose_text=run.options.index_json_include_purpose_text,
        )
        if run.options.index_json_include_classes
        else []
    )
    symbols_payload = _normalized_symbol_payload(
        ir,
        class_ids_by_path_qualname=class_ids_by_path_qualname,
        include_canonical_ids=include_canonical_ids,
        path_table=path_table,
        path_lookup=path_lookup,
        part_table=part_table,
        part_lookup=part_lookup,
        qualname_table=qualname_table,
        qualname_lookup=qualname_lookup,
        string_table=string_table,
        string_lookup=string_lookup,
    )

    repository = {
        **_repository_common_payload(ir),
        "tables": {
            "paths": path_table,
            "parts": part_table,
            "qualnames": qualname_table,
            "strings": string_table,
        },
        "files": files_payload,
        "symbols": symbols_payload,
    }
    if run.options.index_json_include_classes:
        repository["classes"] = classes_payload
    if ir.repository_analysis_metadata:
        repository.update(
            _normalized_analysis_payload(
                ir.import_edges,
                ir.test_links,
                ir.guide,
                ir.architecture,
                path_table=path_table,
                path_lookup=path_lookup,
                string_table=string_table,
                string_lookup=string_lookup,
            )
        )
    return repository
