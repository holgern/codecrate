from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from .formats import (
    INDEX_JSON_FORMAT_VERSION_V1,
    INDEX_JSON_FORMAT_VERSION_V2,
    INDEX_JSON_FORMAT_VERSION_V3,
)

_ANCHOR_RE = re.compile(r'<a id="([^"]+)"></a>')


def _append_error(errors: list[str], repo_label: str, detail: str) -> None:
    errors.append(f"{repo_label}: {detail}")


def _read_anchors(base_dir: Path, rel_path: str) -> set[str]:
    text = (base_dir / rel_path).read_text(encoding="utf-8")
    return set(_ANCHOR_RE.findall(text))


def _validate_href(
    errors: list[str],
    *,
    repo_label: str,
    output_files: set[str],
    anchors_by_path: dict[str, set[str]],
    href: str,
    detail: str,
    check_anchors: bool,
) -> None:
    if "#" not in href:
        _append_error(errors, repo_label, f"malformed {detail}: {href}")
        return
    rel_path, anchor = href.split("#", 1)
    if rel_path not in output_files:
        _append_error(
            errors,
            repo_label,
            f"{detail} points to unknown output file: {href}",
        )
        return
    if check_anchors and anchor not in anchors_by_path.get(rel_path, set()):
        _append_error(errors, repo_label, f"{detail} points to missing anchor: {href}")


def _validate_line_range(
    errors: list[str],
    *,
    repo_label: str,
    line_range: dict[str, Any] | None,
    detail: str,
) -> None:
    if line_range is None:
        return
    start_line = int(line_range.get("start_line", 0) or 0)
    end_line = int(line_range.get("end_line", 0) or 0)
    if start_line <= 0 or end_line < start_line:
        _append_error(errors, repo_label, f"invalid {detail}")


def _validate_locator_line_range(
    errors: list[str],
    *,
    repo_label: str,
    line_range: Any,
    detail: str,
) -> None:
    if line_range is None:
        return
    if not isinstance(line_range, dict):
        _append_error(errors, repo_label, f"invalid {detail}")
        return
    start_line = int(line_range.get("start", 0) or 0)
    end_line = int(line_range.get("end", 0) or 0)
    if start_line <= 0 or end_line < start_line:
        _append_error(errors, repo_label, f"invalid {detail}")


def _validate_normalized_locator_line_range(
    errors: list[str],
    *,
    repo_label: str,
    line_range: Any,
    detail: str,
) -> None:
    if line_range is None:
        return
    if (
        not isinstance(line_range, list)
        or len(line_range) != 2
        or not all(isinstance(item, int) for item in line_range)
        or line_range[0] <= 0
        or line_range[1] < line_range[0]
    ):
        _append_error(errors, repo_label, f"invalid {detail}")


def _is_normalized_relative_path(path: str) -> bool:
    normalized = Path(path).as_posix()
    if not path or normalized != path or Path(path).is_absolute():
        return False
    return all(part not in {"", ".", ".."} for part in Path(path).parts)


def _reconstructed_locator_path(repo: dict[str, Any], rel_path: str) -> str:
    reconstructed_root = repo.get("reconstructed_root")
    if isinstance(reconstructed_root, str) and reconstructed_root:
        return Path(reconstructed_root, rel_path).as_posix()
    return rel_path


def _validate_repository_locator_metadata(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
) -> None:
    locator_space = repo.get("locator_space")
    secondary_locator_space = repo.get("secondary_locator_space")
    reconstructed_root = repo.get("reconstructed_root")
    if locator_space is not None and locator_space not in {
        "markdown",
        "reconstructed",
        "dual",
    }:
        _append_error(errors, repo_label, "invalid locator_space")
    if secondary_locator_space is not None:
        if secondary_locator_space not in {"markdown", "reconstructed"}:
            _append_error(errors, repo_label, "invalid secondary_locator_space")
        elif secondary_locator_space == locator_space:
            _append_error(
                errors,
                repo_label,
                "secondary_locator_space must differ from locator_space",
            )
    if reconstructed_root is not None:
        if not isinstance(reconstructed_root, str) or not _is_normalized_relative_path(
            reconstructed_root
        ):
            _append_error(errors, repo_label, "invalid reconstructed_root")


def _validate_string_list(
    errors: list[str],
    *,
    repo_label: str,
    values: Any,
    detail: str,
) -> None:
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        _append_error(errors, repo_label, f"invalid {detail}")


def _validate_parameter_payload(
    errors: list[str],
    *,
    repo_label: str,
    parameters: Any,
    detail: str,
) -> None:
    if not isinstance(parameters, list):
        _append_error(errors, repo_label, f"invalid {detail}")
        return
    for parameter in parameters:
        if not isinstance(parameter, dict):
            _append_error(errors, repo_label, f"invalid {detail}")
            return
        if not isinstance(parameter.get("name"), str) or not isinstance(
            parameter.get("kind"), str
        ):
            _append_error(errors, repo_label, f"invalid {detail}")
            return


def _validate_file_summary(
    errors: list[str],
    *,
    repo_label: str,
    summary: Any,
    detail: str,
) -> None:
    if summary is None:
        return
    if not isinstance(summary, dict):
        _append_error(errors, repo_label, f"invalid {detail}")
        return
    primary_symbols = summary.get("primary_symbols")
    if primary_symbols is not None:
        _validate_string_list(
            errors,
            repo_label=repo_label,
            values=primary_symbols,
            detail=f"{detail} primary_symbols",
        )
    exports = summary.get("exports")
    if exports is not None:
        _validate_string_list(
            errors,
            repo_label=repo_label,
            values=exports,
            detail=f"{detail} exports",
        )
    for key in ("imports_local", "imports_external"):
        value = summary.get(key)
        if value is not None and (not isinstance(value, int) or value < 0):
            _append_error(errors, repo_label, f"invalid {detail} {key}")


def _validate_relationships(
    errors: list[str],
    *,
    repo_label: str,
    relationships: Any,
    detail: str,
) -> None:
    if relationships is None:
        return
    if not isinstance(relationships, dict):
        _append_error(errors, repo_label, f"invalid {detail}")
        return
    for key in (
        "depends_on",
        "used_by",
        "related_tests",
        "same_package_neighbors",
        "entrypoint_reachability",
    ):
        values = relationships.get(key)
        if values is not None:
            _validate_string_list(
                errors,
                repo_label=repo_label,
                values=values,
                detail=f"{detail} {key}",
            )


def _validate_semantic_symbol_payload(
    errors: list[str],
    *,
    repo_label: str,
    semantic: Any,
    detail: str,
) -> None:
    if semantic is None:
        return
    if not isinstance(semantic, dict):
        _append_error(errors, repo_label, f"invalid {detail}")
        return
    if semantic.get("parameters") is not None:
        _validate_parameter_payload(
            errors,
            repo_label=repo_label,
            parameters=semantic.get("parameters"),
            detail=f"{detail} parameters",
        )


def _validate_normalized_summary_payload(
    errors: list[str],
    *,
    repo_label: str,
    summary: Any,
    qualnames: list[Any],
    strings: list[Any],
) -> None:
    if summary is None:
        return
    if not isinstance(summary, dict):
        _append_error(errors, repo_label, "invalid normalized file summary")
        return
    if summary.get("r") is not None:
        _validate_table_index(
            errors,
            repo_label=repo_label,
            index=summary.get("r"),
            table_name="strings",
            table_size=len(strings),
            detail="normalized file summary role",
        )
    for qualname_index in summary.get("p", []):
        _validate_table_index(
            errors,
            repo_label=repo_label,
            index=qualname_index,
            table_name="qualnames",
            table_size=len(qualnames),
            detail="normalized file summary primary symbol",
        )
    for string_index in summary.get("e", []):
        _validate_table_index(
            errors,
            repo_label=repo_label,
            index=string_index,
            table_name="strings",
            table_size=len(strings),
            detail="normalized file summary export",
        )


def _validate_normalized_relationships_payload(
    errors: list[str],
    *,
    repo_label: str,
    relationships: Any,
    paths: list[Any],
) -> None:
    if relationships is None:
        return
    if not isinstance(relationships, dict):
        _append_error(errors, repo_label, "invalid normalized file relationships")
        return
    for key in ("d", "u", "t", "n", "e"):
        for path_index in relationships.get(key, []):
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=path_index,
                table_name="paths",
                table_size=len(paths),
                detail=f"normalized file relationships {key}",
            )


def _validate_parts(
    errors: list[str],
    *,
    repo_label: str,
    output_files: set[str],
    parts: list[dict[str, Any]],
    files_by_path: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    parts_by_path: dict[str, dict[str, Any]] = {}
    for entry in parts:
        path = entry.get("path")
        if isinstance(path, str):
            parts_by_path[path] = entry
    for part in parts:
        part_path = part.get("path")
        if part_path not in output_files:
            _append_error(
                errors,
                repo_label,
                f"part path missing from pack.output_files: {part_path}",
            )
        contains = part.get("contains", {})
        for rel_path in contains.get("files", []):
            if rel_path not in files_by_path:
                _append_error(
                    errors,
                    repo_label,
                    f"part references unknown file path: {rel_path}",
                )
    return parts_by_path


def _validate_files(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
    output_files: set[str],
    anchors_by_path: dict[str, set[str]],
    check_anchors: bool,
    files: list[dict[str, Any]],
    parts_by_path: dict[str, dict[str, Any]],
    symbols_by_local_id: dict[str, dict[str, Any]],
    check_symbol_membership: bool,
) -> None:
    for file_entry in files:
        path = file_entry.get("path")
        part_path = file_entry.get("part_path")
        if part_path is not None and part_path not in parts_by_path:
            _append_error(
                errors,
                repo_label,
                f"file part_path missing from parts: {part_path}",
            )
        _validate_line_range(
            errors,
            repo_label=repo_label,
            line_range=file_entry.get("markdown_lines"),
            detail=f"file markdown_lines for {path}",
        )
        for href in (file_entry.get("hrefs") or {}).values():
            if href is None:
                continue
            _validate_href(
                errors,
                repo_label=repo_label,
                output_files=output_files,
                anchors_by_path=anchors_by_path,
                href=href,
                detail=f"file href for {path}",
                check_anchors=check_anchors,
            )
        if check_symbol_membership:
            for symbol_id in file_entry.get("symbol_ids", []):
                if symbol_id not in symbols_by_local_id:
                    _append_error(
                        errors,
                        repo_label,
                        f"file references unknown symbol id: {symbol_id}",
                    )
        locators = file_entry.get("locators")
        if not isinstance(locators, dict):
            _validate_file_summary(
                errors,
                repo_label=repo_label,
                summary=file_entry.get("summary"),
                detail=f"file summary for {path}",
            )
            _validate_relationships(
                errors,
                repo_label=repo_label,
                relationships=file_entry.get("relationships"),
                detail=f"file relationships for {path}",
            )
            continue
        markdown_locator = locators.get("markdown")
        if markdown_locator is not None:
            if not isinstance(markdown_locator, dict):
                _append_error(
                    errors, repo_label, f"invalid file markdown locator for {path}"
                )
            else:
                markdown_path = markdown_locator.get("path")
                if (
                    not isinstance(markdown_path, str)
                    or markdown_path not in output_files
                    or markdown_path != repo.get("markdown_path")
                ):
                    _append_error(
                        errors,
                        repo_label,
                        f"invalid file markdown locator path for {path}",
                    )
                _validate_locator_line_range(
                    errors,
                    repo_label=repo_label,
                    line_range=markdown_locator.get("lines"),
                    detail=f"file markdown locator lines for {path}",
                )
        reconstructed_locator = locators.get("reconstructed")
        if reconstructed_locator is not None:
            if not isinstance(reconstructed_locator, dict):
                _append_error(
                    errors,
                    repo_label,
                    f"invalid file reconstructed locator for {path}",
                )
            else:
                reconstructed_path = reconstructed_locator.get("path")
                expected_path = _reconstructed_locator_path(repo, str(path or ""))
                if (
                    not isinstance(reconstructed_path, str)
                    or not _is_normalized_relative_path(reconstructed_path)
                    or reconstructed_path != expected_path
                ):
                    _append_error(
                        errors,
                        repo_label,
                        f"invalid file reconstructed locator path for {path}",
                    )
                _validate_locator_line_range(
                    errors,
                    repo_label=repo_label,
                    line_range=reconstructed_locator.get("lines"),
                    detail=f"file reconstructed locator lines for {path}",
                )
                lines = reconstructed_locator.get("lines")
                line_count = file_entry.get("line_count")
                if isinstance(lines, dict) and isinstance(line_count, int):
                    end_line = int(lines.get("end", 0) or 0)
                    if end_line > line_count:
                        _append_error(
                            errors,
                            repo_label,
                            f"file reconstructed locator exceeds line count for {path}",
                        )
        _validate_file_summary(
            errors,
            repo_label=repo_label,
            summary=file_entry.get("summary"),
            detail=f"file summary for {path}",
        )
        _validate_relationships(
            errors,
            repo_label=repo_label,
            relationships=file_entry.get("relationships"),
            detail=f"file relationships for {path}",
        )


def _validate_symbols(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
    output_files: set[str],
    anchors_by_path: dict[str, set[str]],
    check_anchors: bool,
    symbols: list[dict[str, Any]],
    files_by_path: dict[str, dict[str, Any]],
    parts_by_path: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    symbols_by_local_id: dict[str, dict[str, Any]] = {}
    for entry in symbols:
        local_id = entry.get("local_id")
        if isinstance(local_id, str):
            symbols_by_local_id[local_id] = entry
    for symbol_entry in symbols:
        path = symbol_entry.get("path")
        if path not in files_by_path:
            _append_error(
                errors,
                repo_label,
                f"symbol path missing from files array: {path}",
            )
        file_part = symbol_entry.get("file_part")
        if file_part is not None and file_part not in parts_by_path:
            _append_error(
                errors,
                repo_label,
                f"symbol file_part missing from parts: {file_part}",
            )
        canonical_part = symbol_entry.get("canonical_part")
        if canonical_part is not None and canonical_part not in parts_by_path:
            _append_error(
                errors,
                repo_label,
                f"symbol canonical_part missing from parts: {canonical_part}",
            )
        for key in (
            "index_markdown_lines",
            "file_markdown_lines",
            "canonical_markdown_lines",
        ):
            _validate_line_range(
                errors,
                repo_label=repo_label,
                line_range=symbol_entry.get(key),
                detail=f"{key} for symbol {symbol_entry.get('local_id')}",
            )
        for href_key in ("file_href", "canonical_href"):
            href = symbol_entry.get(href_key)
            if href is None:
                continue
            _validate_href(
                errors,
                repo_label=repo_label,
                output_files=output_files,
                anchors_by_path=anchors_by_path,
                href=href,
                detail=f"{href_key} for {symbol_entry.get('local_id')}",
                check_anchors=check_anchors,
            )
        locators = symbol_entry.get("locators")
        semantic_id = symbol_entry.get("semantic_id")
        if semantic_id is not None and not isinstance(semantic_id, str):
            _append_error(
                errors,
                repo_label,
                f"invalid semantic_id for {symbol_entry.get('local_id')}",
            )
        _validate_semantic_symbol_payload(
            errors,
            repo_label=repo_label,
            semantic=symbol_entry.get("semantic"),
            detail=f"symbol semantic payload for {symbol_entry.get('local_id')}",
        )
        if not isinstance(locators, dict):
            continue
        markdown_locator = locators.get("markdown")
        if markdown_locator is not None:
            if not isinstance(markdown_locator, dict):
                _append_error(
                    errors,
                    repo_label,
                    "invalid symbol markdown locator for "
                    f"{symbol_entry.get('local_id')}",
                )
            else:
                markdown_path = markdown_locator.get("path")
                if (
                    not isinstance(markdown_path, str)
                    or markdown_path not in output_files
                    or markdown_path != repo.get("markdown_path")
                ):
                    _append_error(
                        errors,
                        repo_label,
                        "invalid symbol markdown locator path for "
                        f"{symbol_entry.get('local_id')}",
                    )
                for key in ("file_lines", "symbol_index_lines", "canonical_lines"):
                    _validate_locator_line_range(
                        errors,
                        repo_label=repo_label,
                        line_range=markdown_locator.get(key),
                        detail=f"{key} for symbol {symbol_entry.get('local_id')}",
                    )
        reconstructed_locator = locators.get("reconstructed")
        if reconstructed_locator is not None:
            if not isinstance(reconstructed_locator, dict):
                _append_error(
                    errors,
                    repo_label,
                    "invalid symbol reconstructed locator for "
                    f"{symbol_entry.get('local_id')}",
                )
            else:
                reconstructed_path = reconstructed_locator.get("path")
                expected_path = _reconstructed_locator_path(
                    repo, str(symbol_entry.get("path") or "")
                )
                if (
                    not isinstance(reconstructed_path, str)
                    or not _is_normalized_relative_path(reconstructed_path)
                    or reconstructed_path != expected_path
                ):
                    _append_error(
                        errors,
                        repo_label,
                        "invalid symbol reconstructed locator path "
                        f"for {symbol_entry.get('local_id')}",
                    )
                _validate_locator_line_range(
                    errors,
                    repo_label=repo_label,
                    line_range=reconstructed_locator.get("lines"),
                    detail=(
                        f"reconstructed lines for symbol {symbol_entry.get('local_id')}"
                    ),
                )
                _validate_locator_line_range(
                    errors,
                    repo_label=repo_label,
                    line_range=reconstructed_locator.get("body_lines"),
                    detail=(
                        "reconstructed body lines for symbol "
                        f"{symbol_entry.get('local_id')}"
                    ),
                )
                lines = reconstructed_locator.get("lines")
                body_lines = reconstructed_locator.get("body_lines")
                if isinstance(lines, dict) and isinstance(body_lines, dict):
                    line_start = int(lines.get("start", 0) or 0)
                    line_end = int(lines.get("end", 0) or 0)
                    body_start = int(body_lines.get("start", 0) or 0)
                    body_end = int(body_lines.get("end", 0) or 0)
                    if body_start < line_start or body_end > line_end:
                        _append_error(
                            errors,
                            repo_label,
                            "symbol reconstructed body lines must be within "
                            "reconstructed lines",
                        )
    return symbols_by_local_id


def _validate_lookup(
    errors: list[str],
    *,
    repo_label: str,
    lookup: dict[str, Any],
    files_by_path: dict[str, dict[str, Any]],
    symbols_by_local_id: dict[str, dict[str, Any]],
) -> None:
    for path, symbol_ids in lookup.get("symbols_by_file", {}).items():
        if path not in files_by_path:
            _append_error(
                errors,
                repo_label,
                f"lookup symbols_by_file references unknown path: {path}",
            )
        for symbol_id in symbol_ids:
            symbol_entry = symbols_by_local_id.get(symbol_id)
            if symbol_entry is None or symbol_entry.get("path") != path:
                _append_error(
                    errors,
                    repo_label,
                    f"lookup symbols_by_file inconsistent for {path}/{symbol_id}",
                )
    for symbol_id, path in lookup.get("file_by_symbol", {}).items():
        symbol_entry = symbols_by_local_id.get(symbol_id)
        if symbol_entry is None or symbol_entry.get("path") != path:
            _append_error(
                errors,
                repo_label,
                f"lookup file_by_symbol inconsistent for {symbol_id}",
            )
    for path, part_path in lookup.get("part_by_file", {}).items():
        file_entry = files_by_path.get(path)
        if file_entry is None or file_entry.get("part_path") != part_path:
            _append_error(
                errors,
                repo_label,
                f"lookup part_by_file inconsistent for {path}",
            )
    for path, file_pointer in lookup.get("file_by_path", {}).items():
        file_entry = files_by_path.get(path)
        if file_entry is None:
            _append_error(
                errors,
                repo_label,
                f"lookup file_by_path references unknown path: {path}",
            )
            continue
        if not isinstance(file_pointer, dict):
            _append_error(
                errors,
                repo_label,
                f"lookup file_by_path entry is not an object: {path}",
            )
            continue
        if file_pointer.get("part_path") is not None and file_pointer.get(
            "part_path"
        ) != file_entry.get("part_path"):
            _append_error(
                errors,
                repo_label,
                f"lookup file_by_path part mismatch for {path}",
            )
        hrefs = file_entry.get("hrefs") or {}
        if file_pointer.get("source_href") is not None and file_pointer.get(
            "source_href"
        ) != hrefs.get("source"):
            _append_error(
                errors,
                repo_label,
                f"lookup file_by_path source href mismatch for {path}",
            )
        if file_pointer.get("index_href") is not None and file_pointer.get(
            "index_href"
        ) != hrefs.get("index"):
            _append_error(
                errors,
                repo_label,
                f"lookup file_by_path index href mismatch for {path}",
            )
    for symbol_id, symbol_pointer in lookup.get("symbol_by_local_id", {}).items():
        symbol_entry = symbols_by_local_id.get(symbol_id)
        if symbol_entry is None:
            _append_error(
                errors,
                repo_label,
                f"lookup symbol_by_local_id references unknown symbol id: {symbol_id}",
            )
            continue
        if not isinstance(symbol_pointer, dict):
            _append_error(
                errors,
                repo_label,
                f"lookup symbol_by_local_id entry is not an object: {symbol_id}",
            )
            continue
        if symbol_pointer.get("path") != symbol_entry.get("path"):
            _append_error(
                errors,
                repo_label,
                f"lookup symbol_by_local_id path mismatch for {symbol_id}",
            )


def _v2_features(repo: dict[str, Any], *, mode: Any) -> dict[str, bool]:
    defaults = {
        "lookup": mode in {"compact", "minimal"},
        "symbol_index_lines": mode == "compact",
    }
    raw = repo.get("index_json_features")
    if not isinstance(raw, dict):
        return defaults
    return {
        key: bool(raw.get(key, defaults[key]))
        for key in ("lookup", "symbol_index_lines")
    }


def _validate_table_index(
    errors: list[str],
    *,
    repo_label: str,
    index: Any,
    table_name: str,
    table_size: int,
    detail: str,
) -> None:
    if not isinstance(index, int) or index < 0 or index >= table_size:
        _append_error(errors, repo_label, f"invalid {detail} index in {table_name}")


def _normalized_tables(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
) -> tuple[list[Any], list[Any], list[Any], list[Any]] | None:
    tables = repo.get("tables")
    if not isinstance(tables, dict):
        _append_error(errors, repo_label, "missing tables payload for normalized mode")
        return None
    paths = tables.get("paths")
    parts_table = tables.get("parts")
    qualnames = tables.get("qualnames")
    strings = tables.get("strings")
    if not all(
        isinstance(table, list) for table in (paths, parts_table, qualnames, strings)
    ):
        _append_error(errors, repo_label, "normalized tables must all be arrays")
        return None
    return (
        cast(list[Any], paths),
        cast(list[Any], parts_table),
        cast(list[Any], qualnames),
        cast(list[Any], strings),
    )


def _validate_normalized_file_entries(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
    files: list[dict[str, Any]],
    paths: list[Any],
    parts_table: list[Any],
    qualnames: list[Any],
    strings: list[Any],
) -> dict[str, dict[str, Any]]:
    files_by_path: dict[str, dict[str, Any]] = {}
    for file_entry in files:
        path_index = file_entry.get("p")
        _validate_table_index(
            errors,
            repo_label=repo_label,
            index=path_index,
            table_name="paths",
            table_size=len(paths),
            detail="file path",
        )
        if not isinstance(path_index, int) or not 0 <= path_index < len(paths):
            continue
        path = paths[path_index]
        if not isinstance(path, str):
            _append_error(errors, repo_label, "path table contains non-string entry")
            continue
        files_by_path[path] = file_entry
        if file_entry.get("part") is not None:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=file_entry.get("part"),
                table_name="parts",
                table_size=len(parts_table),
                detail="file part",
            )
        for key in ("lang", "mod", "role"):
            if file_entry.get(key) is not None:
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=file_entry.get(key),
                    table_name="strings",
                    table_size=len(strings),
                    detail=f"file {key}",
                )
        for import_entry in file_entry.get("imp", []):
            for key in ("k", "m", "r", "n", "a"):
                if import_entry.get(key) is not None:
                    _validate_table_index(
                        errors,
                        repo_label=repo_label,
                        index=import_entry.get(key),
                        table_name="strings",
                        table_size=len(strings),
                        detail=f"import {key}",
                    )
            if import_entry.get("t") is not None:
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=import_entry.get("t"),
                    table_name="paths",
                    table_size=len(paths),
                    detail="import target",
                )
        for export_index in file_entry.get("exp", []):
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=export_index,
                table_name="strings",
                table_size=len(strings),
                detail="file export",
            )
        locators = file_entry.get("loc")
        if isinstance(locators, dict):
            _validate_normalized_locator_line_range(
                errors,
                repo_label=repo_label,
                line_range=locators.get("m"),
                detail=f"normalized file markdown locator for {path}",
            )
            _validate_normalized_locator_line_range(
                errors,
                repo_label=repo_label,
                line_range=locators.get("r"),
                detail=f"normalized file reconstructed locator for {path}",
            )
        _validate_normalized_summary_payload(
            errors,
            repo_label=repo_label,
            summary=file_entry.get("sum"),
            qualnames=qualnames,
            strings=strings,
        )
        _validate_normalized_relationships_payload(
            errors,
            repo_label=repo_label,
            relationships=file_entry.get("rel"),
            paths=paths,
        )
    return files_by_path


def _validate_normalized_symbol_entries(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
    symbols: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    files_by_path: dict[str, dict[str, Any]],
    paths: list[Any],
    parts_table: list[Any],
    qualnames: list[Any],
    strings: list[Any],
) -> None:
    class_ids = {entry.get("i") for entry in classes if isinstance(entry, dict)}
    for symbol_entry in symbols:
        semantic_id = symbol_entry.get("sid")
        if semantic_id is not None and not isinstance(semantic_id, str):
            _append_error(errors, repo_label, "invalid normalized symbol semantic_id")
        for key, table_name, table_size, detail in (
            ("p", "paths", len(paths), "symbol path"),
            ("q", "qualnames", len(qualnames), "symbol qualname"),
            ("k", "strings", len(strings), "symbol kind"),
        ):
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=symbol_entry.get(key),
                table_name=table_name,
                table_size=table_size,
                detail=detail,
            )
        if symbol_entry.get("part") is not None:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=symbol_entry.get("part"),
                table_name="parts",
                table_size=len(parts_table),
                detail="symbol part",
            )
        owner_class = symbol_entry.get("o")
        if owner_class is not None and owner_class not in class_ids:
            _append_error(
                errors,
                repo_label,
                "symbol owner_class references unknown class",
            )
        for decorator_index in symbol_entry.get("d", []):
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=decorator_index,
                table_name="strings",
                table_size=len(strings),
                detail="symbol decorator",
            )
        if symbol_entry.get("sig") is not None:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=symbol_entry.get("sig"),
                table_name="strings",
                table_size=len(strings),
                detail="symbol signature",
            )
        if symbol_entry.get("ret") is not None:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=symbol_entry.get("ret"),
                table_name="strings",
                table_size=len(strings),
                detail="symbol return annotation",
            )
        for parameter in symbol_entry.get("params", []):
            if not isinstance(parameter, dict):
                _append_error(
                    errors,
                    repo_label,
                    "invalid normalized symbol parameters entry",
                )
                continue
            for key in ("n", "k", "a"):
                if parameter.get(key) is not None:
                    _validate_table_index(
                        errors,
                        repo_label=repo_label,
                        index=parameter.get(key),
                        table_name="strings",
                        table_size=len(strings),
                        detail=f"normalized symbol parameter {key}",
                    )
        path_index = symbol_entry.get("p")
        if isinstance(path_index, int) and 0 <= path_index < len(paths):
            if paths[path_index] not in files_by_path:
                _append_error(
                    errors,
                    repo_label,
                    "symbol path missing from files array",
                )
            path = paths[path_index]
        else:
            path = ""
        locators = symbol_entry.get("loc")
        if isinstance(locators, dict):
            markdown_locator = locators.get("m")
            if markdown_locator is not None:
                if not isinstance(markdown_locator, dict):
                    _append_error(
                        errors,
                        repo_label,
                        "invalid normalized symbol markdown locator",
                    )
                else:
                    for key in ("f", "i", "c"):
                        _validate_normalized_locator_line_range(
                            errors,
                            repo_label=repo_label,
                            line_range=markdown_locator.get(key),
                            detail=f"normalized symbol {key} locator",
                        )
            reconstructed_locator = locators.get("r")
            if reconstructed_locator is not None:
                if not isinstance(reconstructed_locator, dict):
                    _append_error(
                        errors,
                        repo_label,
                        "invalid normalized symbol reconstructed locator",
                    )
                else:
                    _validate_normalized_locator_line_range(
                        errors,
                        repo_label=repo_label,
                        line_range=reconstructed_locator.get("l"),
                        detail=f"normalized symbol reconstructed lines for {path}",
                    )
                    _validate_normalized_locator_line_range(
                        errors,
                        repo_label=repo_label,
                        line_range=reconstructed_locator.get("b"),
                        detail=f"normalized symbol reconstructed body lines for {path}",
                    )


def _validate_normalized_class_entries(
    errors: list[str],
    *,
    repo_label: str,
    classes: list[dict[str, Any]],
    paths: list[Any],
    parts_table: list[Any],
    qualnames: list[Any],
    strings: list[Any],
) -> None:
    for class_entry in classes:
        semantic_id = class_entry.get("sid")
        if semantic_id is not None and not isinstance(semantic_id, str):
            _append_error(errors, repo_label, "invalid normalized class semantic_id")
        _validate_table_index(
            errors,
            repo_label=repo_label,
            index=class_entry.get("p"),
            table_name="paths",
            table_size=len(paths),
            detail="class path",
        )
        _validate_table_index(
            errors,
            repo_label=repo_label,
            index=class_entry.get("q"),
            table_name="qualnames",
            table_size=len(qualnames),
            detail="class qualname",
        )
        if class_entry.get("part") is not None:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=class_entry.get("part"),
                table_name="parts",
                table_size=len(parts_table),
                detail="class part",
            )
        for key in ("b", "d"):
            for string_index in class_entry.get(key, []):
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=string_index,
                    table_name="strings",
                    table_size=len(strings),
                    detail=f"class {key}",
                )


def _validate_normalized_analysis_sections(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
    paths: list[Any],
    strings: list[Any],
) -> None:
    for edge in (repo.get("graph") or {}).get("import_edges", []):
        for key in ("s", "t"):
            if edge.get(key) is not None:
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=edge.get(key),
                    table_name="paths",
                    table_size=len(paths),
                    detail=f"graph {key}",
                )
        for key in ("m", "r", "n", "a", "k"):
            if edge.get(key) is not None:
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=edge.get(key),
                    table_name="strings",
                    table_size=len(strings),
                    detail=f"graph {key}",
                )

    for link in repo.get("test_links", []):
        for key in ("s", "t"):
            if link.get(key) is not None:
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=link.get(key),
                    table_name="paths",
                    table_size=len(paths),
                    detail=f"test link {key}",
                )
        for key in ("r", "k"):
            if link.get(key) is not None:
                _validate_table_index(
                    errors,
                    repo_label=repo_label,
                    index=link.get(key),
                    table_name="strings",
                    table_size=len(strings),
                    detail=f"test link {key}",
                )
        if link.get("score") is not None and not isinstance(link.get("score"), int):
            _append_error(errors, repo_label, "invalid normalized test link score")

    for key, values in (repo.get("guide") or {}).items():
        table_name = "strings" if key == "main_workflows" else "paths"
        table_size = len(strings) if key == "main_workflows" else len(paths)
        for value in values:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=value,
                table_name=table_name,
                table_size=table_size,
                detail=f"guide {key}",
            )

    for key, values in (repo.get("architecture") or {}).items():
        for value in values:
            _validate_table_index(
                errors,
                repo_label=repo_label,
                index=value,
                table_name="paths",
                table_size=len(paths),
                detail=f"architecture {key}",
            )


def _validate_normalized_repo(
    errors: list[str],
    *,
    repo: dict[str, Any],
    repo_label: str,
    output_files: set[str],
) -> None:
    normalized_tables = _normalized_tables(errors, repo=repo, repo_label=repo_label)
    if normalized_tables is None:
        return
    paths, parts_table, qualnames, strings = normalized_tables
    files = repo.get("files", [])
    symbols = repo.get("symbols", [])
    classes = repo.get("classes", [])
    parts = repo.get("parts", [])
    files_by_path = _validate_normalized_file_entries(
        errors,
        repo=repo,
        repo_label=repo_label,
        files=files,
        paths=paths,
        parts_table=parts_table,
        qualnames=qualnames,
        strings=strings,
    )

    parts_by_path = _validate_parts(
        errors,
        repo_label=repo_label,
        output_files=output_files,
        parts=parts,
        files_by_path=files_by_path,
    )
    part_paths = {entry.get("path") for entry in parts_by_path.values()}
    indexed_part_paths = {
        parts_table[index]
        for index in range(len(parts_table))
        if isinstance(parts_table[index], str)
    }
    if part_paths != indexed_part_paths:
        _append_error(
            errors,
            repo_label,
            "normalized parts table does not match parts payload paths",
        )

    _validate_normalized_symbol_entries(
        errors,
        repo=repo,
        repo_label=repo_label,
        symbols=symbols,
        classes=classes,
        files_by_path=files_by_path,
        paths=paths,
        parts_table=parts_table,
        qualnames=qualnames,
        strings=strings,
    )
    _validate_normalized_class_entries(
        errors,
        repo_label=repo_label,
        classes=classes,
        paths=paths,
        parts_table=parts_table,
        qualnames=qualnames,
        strings=strings,
    )
    _validate_normalized_analysis_sections(
        errors,
        repo=repo,
        repo_label=repo_label,
        paths=paths,
        strings=strings,
    )


def validate_index_payload(
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    format_version = str(payload.get("format") or "")
    mode = payload.get("mode")
    if format_version == INDEX_JSON_FORMAT_VERSION_V1:
        if mode not in (None, "full"):
            errors.append(f"invalid mode for {format_version}: {mode}")
    elif format_version == INDEX_JSON_FORMAT_VERSION_V2:
        if mode not in {"compact", "minimal"}:
            errors.append(f"invalid mode for {format_version}: {mode}")
    elif format_version == INDEX_JSON_FORMAT_VERSION_V3:
        if mode != "normalized":
            errors.append(f"invalid mode for {format_version}: {mode}")
    else:
        errors.append(f"unsupported index-json format: {format_version}")
    pack_mode = payload.get("pack", {}).get("index_json_mode")
    if pack_mode is not None and mode is not None and pack_mode != mode:
        errors.append(
            f"pack.index_json_mode does not match payload mode: {pack_mode} != {mode}"
        )

    output_files = set(payload.get("pack", {}).get("output_files", []))
    anchors_by_path: dict[str, set[str]] = {}
    check_anchors = base_dir is not None

    if base_dir is not None:
        for rel_path in output_files:
            try:
                anchors_by_path[rel_path] = _read_anchors(base_dir, rel_path)
            except FileNotFoundError:
                errors.append(f"missing output file: {rel_path}")

    for repo in payload.get("repositories", []):
        repo_label = str(repo.get("label") or repo.get("slug") or "repo")
        _validate_repository_locator_metadata(errors, repo=repo, repo_label=repo_label)
        if format_version == INDEX_JSON_FORMAT_VERSION_V3:
            _validate_normalized_repo(
                errors,
                repo=repo,
                repo_label=repo_label,
                output_files=output_files,
            )
            continue
        files = repo.get("files", [])
        symbols = repo.get("symbols", [])
        parts = repo.get("parts", [])
        files_by_path = {entry.get("path"): entry for entry in files}
        features = _v2_features(repo, mode=mode)

        if len(files_by_path) != len(files):
            _append_error(errors, repo_label, "duplicate file paths in files array")
        if format_version == INDEX_JSON_FORMAT_VERSION_V2 and not isinstance(
            repo.get("index_json_features"), dict
        ):
            _append_error(
                errors, repo_label, "missing index_json_features for v2 payload"
            )
        if features["lookup"] and not isinstance(repo.get("lookup"), dict):
            _append_error(
                errors,
                repo_label,
                "index_json_features.lookup=true but lookup payload is missing",
            )

        parts_by_path = _validate_parts(
            errors,
            repo_label=repo_label,
            output_files=output_files,
            parts=parts,
            files_by_path=files_by_path,
        )
        symbols_by_local_id = _validate_symbols(
            errors,
            repo=repo,
            repo_label=repo_label,
            output_files=output_files,
            anchors_by_path=anchors_by_path,
            check_anchors=check_anchors,
            symbols=symbols,
            files_by_path=files_by_path,
            parts_by_path=parts_by_path,
        )
        _validate_files(
            errors,
            repo=repo,
            repo_label=repo_label,
            output_files=output_files,
            anchors_by_path=anchors_by_path,
            check_anchors=check_anchors,
            files=files,
            parts_by_path=parts_by_path,
            symbols_by_local_id=symbols_by_local_id,
            check_symbol_membership=format_version == INDEX_JSON_FORMAT_VERSION_V1,
        )
        _validate_lookup(
            errors,
            repo_label=repo_label,
            lookup=repo.get("lookup", {}),
            files_by_path=files_by_path,
            symbols_by_local_id=symbols_by_local_id,
        )

    return errors
