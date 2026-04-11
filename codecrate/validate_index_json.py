from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .formats import INDEX_JSON_FORMAT_VERSION_V1, INDEX_JSON_FORMAT_VERSION_V2

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


def _validate_symbols(
    errors: list[str],
    *,
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
        files = repo.get("files", [])
        symbols = repo.get("symbols", [])
        parts = repo.get("parts", [])
        files_by_path = {entry.get("path"): entry for entry in files}

        if len(files_by_path) != len(files):
            _append_error(errors, repo_label, "duplicate file paths in files array")

        parts_by_path = _validate_parts(
            errors,
            repo_label=repo_label,
            output_files=output_files,
            parts=parts,
            files_by_path=files_by_path,
        )
        symbols_by_local_id = _validate_symbols(
            errors,
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
