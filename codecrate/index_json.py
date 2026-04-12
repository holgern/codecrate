from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .formats import (
    INDEX_JSON_FORMAT_VERSION_V1,
    INDEX_JSON_FORMAT_VERSION_V2,
    PACK_FORMAT_VERSION,
)
from .ids import (
    ID_FORMAT_VERSION,
    MACHINE_ID_FORMAT_VERSION,
    stable_machine_location_id,
)
from .locators import (
    anchor_for_file_index,
    anchor_for_file_source,
    anchor_for_symbol,
    href,
)
from .markdown import _fence_lang_for
from .output_model import PackRun, RenderMetadata
from .token_budget import Part
from .tokens import approx_token_count

_FILE_HEADING_RE = re.compile(r"^### `([^`]+)`")
_FUNCTION_LIBRARY_HEADING_RE = re.compile(r"^### ([0-9A-F]{8})\s*$")
_FUNC_ANCHOR_RE = re.compile(r'^<a id="func-([0-9a-f]{8})"></a>\s*$')


def _relative_output_path(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def _sort_rel_paths(paths: Iterable[str]) -> list[str]:
    return sorted(set(paths), key=lambda item: (item.lower(), item))


def _line_range(start_line: int, end_line: int) -> dict[str, int]:
    return {
        "start_line": start_line,
        "end_line": end_line,
    }


def _line_ranges_from_metadata(ranges: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        key: _line_range(value.start_line, value.end_line)
        for key, value in ranges.items()
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sorted_unique_parts(parts: list[Part]) -> list[Part]:
    def _kind_rank(part: Part) -> tuple[int, int, str]:
        stem = part.path.stem
        if part.kind == "index" or ".index" in stem:
            return (0, 0, part.path.name)
        part_number = 0
        part_match = part.path.stem.rsplit(".part", 1)
        if len(part_match) == 2:
            try:
                part_number = int(part_match[1])
            except ValueError:
                part_number = 0
        if part.kind == "part":
            return (1, part_number, part.path.name)
        return (2, 0, part.path.name)

    seen: set[str] = set()
    unique: list[Part] = []
    for part in sorted(parts, key=_kind_rank):
        key = part.path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return unique


def _manifest_files_by_path(run: PackRun) -> dict[str, dict[str, Any]]:
    manifest_files = run.manifest.get("files")
    if not isinstance(manifest_files, list):
        return {}
    by_path: dict[str, dict[str, Any]] = {}
    for item in manifest_files:
        if not isinstance(item, dict):
            continue
        rel = item.get("path")
        if isinstance(rel, str) and rel:
            by_path[rel] = item
    return by_path


def _manifest_defs_by_local_id(run: PackRun) -> dict[str, dict[str, Any]]:
    defs_by_local_id: dict[str, dict[str, Any]] = {}
    for file_entry in _manifest_files_by_path(run).values():
        defs = file_entry.get("defs")
        if not isinstance(defs, list):
            continue
        for item in defs:
            if not isinstance(item, dict):
                continue
            local_id = item.get("local_id")
            if isinstance(local_id, str) and local_id:
                defs_by_local_id[local_id] = item
    return defs_by_local_id


def _strong_id_maps(run: PackRun) -> tuple[dict[str, str], dict[str, str]]:
    local_machine_ids: dict[str, str] = {}
    canonical_machine_ids: dict[str, str] = {}

    for defn in sorted(
        run.pack_result.defs,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.def_line,
            item.qualname,
            item.local_id,
        ),
    ):
        rel = defn.path.relative_to(run.pack_result.root)
        machine_id = stable_machine_location_id(rel, defn.qualname, defn.def_line)
        local_machine_ids[defn.local_id] = machine_id
        if defn.local_id == defn.id:
            canonical_machine_ids.setdefault(defn.id, machine_id)

    for defn in run.pack_result.defs:
        canonical_machine_ids.setdefault(
            defn.id,
            local_machine_ids.get(defn.local_id)
            or stable_machine_location_id(
                defn.path.relative_to(run.pack_result.root),
                defn.qualname,
                defn.def_line,
            ),
        )

    return local_machine_ids, canonical_machine_ids


def _repo_scope(markdown_text: str, label: str) -> tuple[list[str], int, int]:
    lines = markdown_text.splitlines()
    header = f"# Repository: {label}"
    start_idx: int | None = None
    next_start_idx: int | None = None

    for idx, line in enumerate(lines):
        if line == header:
            start_idx = idx + 1
            continue
        if start_idx is not None and line.startswith("# Repository:"):
            next_start_idx = idx
            break

    if start_idx is None:
        return lines, 0, len(lines)

    while start_idx < len(lines) and not lines[start_idx].strip():
        start_idx += 1
    return (
        lines,
        start_idx,
        next_start_idx if next_start_idx is not None else len(lines),
    )


def _section_bounds(
    lines: list[str],
    *,
    scope_start: int,
    scope_end: int,
    heading: str,
) -> tuple[int, int] | None:
    section_start: int | None = None
    for idx in range(scope_start, scope_end):
        if lines[idx] == heading:
            section_start = idx
            break
    if section_start is None:
        return None

    section_end = scope_end
    for idx in range(section_start + 1, scope_end):
        if lines[idx].startswith("## "):
            section_end = idx
            break
    return section_start, section_end


def _file_markdown_ranges(
    lines: list[str], *, scope_start: int, scope_end: int
) -> dict[str, dict[str, int]]:
    bounds = _section_bounds(
        lines,
        scope_start=scope_start,
        scope_end=scope_end,
        heading="## Files",
    )
    if bounds is None:
        return {}

    start, end = bounds
    ranges: dict[str, dict[str, int]] = {}
    current_file: str | None = None
    current_start: int | None = None
    for idx in range(start + 1, end):
        match = _FILE_HEADING_RE.match(lines[idx])
        if not match:
            continue
        if current_file is not None and current_start is not None:
            ranges[current_file] = _line_range(current_start, idx)
        current_file = match.group(1)
        current_start = idx + 1

    if current_file is not None and current_start is not None:
        ranges[current_file] = _line_range(current_start, end)
    return ranges


def _canonical_markdown_ranges(
    lines: list[str], *, scope_start: int, scope_end: int
) -> dict[str, dict[str, int]]:
    bounds = _section_bounds(
        lines,
        scope_start=scope_start,
        scope_end=scope_end,
        heading="## Function Library",
    )
    if bounds is None:
        return {}

    start, end = bounds
    ranges: dict[str, dict[str, int]] = {}
    pending_anchor_start: int | None = None
    current_display_id: str | None = None
    current_start: int | None = None
    for idx in range(start + 1, end):
        anchor_match = _FUNC_ANCHOR_RE.match(lines[idx])
        if anchor_match:
            pending_anchor_start = idx + 1
            continue
        heading_match = _FUNCTION_LIBRARY_HEADING_RE.match(lines[idx])
        if not heading_match:
            continue
        if current_display_id is not None and current_start is not None:
            ranges[current_display_id] = _line_range(current_start, idx)
        current_display_id = heading_match.group(1)
        current_start = pending_anchor_start or idx + 1
        pending_anchor_start = None

    if current_display_id is not None and current_start is not None:
        ranges[current_display_id] = _line_range(current_start, end)
    return ranges


def _symbol_index_ranges(
    run: PackRun,
    lines: list[str],
    *,
    scope_start: int,
    scope_end: int,
) -> dict[str, dict[str, int]]:
    bounds = _section_bounds(
        lines,
        scope_start=scope_start,
        scope_end=scope_end,
        heading="## Symbol Index",
    )
    if bounds is None:
        return {}

    defs_by_file: dict[str, list[str]] = {}
    for file_pack in sorted(
        run.pack_result.files,
        key=lambda item: item.path.relative_to(run.pack_result.root).as_posix(),
    ):
        rel = file_pack.path.relative_to(run.pack_result.root).as_posix()
        defs_by_file[rel] = [
            defn.local_id
            for defn in sorted(
                file_pack.defs,
                key=lambda item: (item.def_line, item.qualname, item.local_id),
            )
        ]

    start, end = bounds
    current_file: str | None = None
    current_index = 0
    ranges: dict[str, dict[str, int]] = {}
    for idx in range(start + 1, end):
        file_match = _FILE_HEADING_RE.match(lines[idx])
        if file_match:
            current_file = file_match.group(1)
            current_index = 0
            continue
        if current_file is None or not lines[idx].startswith("- `"):
            continue
        if lines[idx].startswith("- `class "):
            continue
        defs = defs_by_file.get(current_file, [])
        if current_index >= len(defs):
            continue
        ranges[defs[current_index]] = _line_range(idx + 1, idx + 1)
        current_index += 1

    return ranges


def _unsplit_markdown_metadata(
    run: PackRun,
    *,
    repo_output_parts: list[Part],
    base_dir: Path,
) -> tuple[
    str | None,
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
]:
    parts_in = _sorted_unique_parts(repo_output_parts)
    if len(parts_in) != 1 or parts_in[0].kind != "pack":
        return None, {}, {}, {}

    part = parts_in[0]
    markdown_path = _relative_output_path(part.path, base_dir=base_dir)
    if part.content == run.markdown:
        metadata: RenderMetadata = run.render_metadata
        return (
            markdown_path,
            _line_ranges_from_metadata(metadata.file_ranges),
            _line_ranges_from_metadata(metadata.symbol_index_ranges),
            _line_ranges_from_metadata(metadata.canonical_ranges),
        )
    lines, scope_start, scope_end = _repo_scope(part.content, run.label)
    return (
        markdown_path,
        _file_markdown_ranges(lines, scope_start=scope_start, scope_end=scope_end),
        _symbol_index_ranges(
            run,
            lines,
            scope_start=scope_start,
            scope_end=scope_end,
        ),
        _canonical_markdown_ranges(lines, scope_start=scope_start, scope_end=scope_end),
    )


def _safety_payload(run: PackRun) -> dict[str, Any]:
    findings = sorted(
        run.safety_findings,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.action,
            item.reason,
        ),
    )
    return {
        "skipped_count": run.skipped_for_safety_count,
        "redacted_count": run.redacted_for_safety_count,
        "findings": [
            {
                "path": item.path.relative_to(run.pack_result.root).as_posix(),
                "reason": item.reason,
                "action": item.action,
            }
            for item in findings
        ],
    }


def _split_policy(run: PackRun) -> str:
    if run.options.split_allow_cut_files:
        return "cut-files"
    if run.options.split_strict:
        return "strict"
    return "preserve"


def _part_id(*, slug: str, kind: str, part_number: int | None) -> str:
    if kind == "pack":
        return f"{slug}:pack"
    if kind == "index":
        return f"{slug}:index"
    if part_number is None:
        return f"{slug}:part"
    return f"{slug}:part{part_number}"


def _all_repo_file_paths(run: PackRun) -> list[str]:
    return _sort_rel_paths(
        file_pack.path.relative_to(run.pack_result.root).as_posix()
        for file_pack in run.pack_result.files
    )


def _all_repo_canonical_ids(run: PackRun) -> list[str]:
    if run.effective_layout != "stubs":
        return []
    _, canonical_machine_ids = _strong_id_maps(run)
    return sorted(canonical_machine_ids[cid] for cid in sorted(run.canonical_sources))


def _all_repo_display_canonical_ids(run: PackRun) -> list[str]:
    if run.effective_layout != "stubs":
        return []
    return sorted(run.canonical_sources)


def _part_metadata(
    run: PackRun,
    *,
    repo_output_parts: list[Part],
    base_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str], dict[str, str]]:
    parts_in = _sorted_unique_parts(repo_output_parts)
    _, canonical_machine_ids = _strong_id_maps(run)
    if len(parts_in) == 1 and parts_in[0].kind == "pack":
        part = parts_in[0]
        rel_path = _relative_output_path(part.path, base_dir=base_dir)
        part_entry = {
            "part_id": _part_id(slug=run.slug, kind="pack", part_number=None),
            "path": rel_path,
            "kind": "pack",
            "repo_slug": run.slug,
            "char_count": len(part.content),
            "line_count": len(part.content.splitlines()),
            "sha256_content": _sha256_text(part.content),
            "token_estimate": approx_token_count(part.content),
            "is_oversized": False,
            "contains": {
                "files": list(part.files) or _all_repo_file_paths(run),
                "canonical_ids": list(part.canonical_ids)
                or _all_repo_canonical_ids(run),
                "display_canonical_ids": _all_repo_display_canonical_ids(run),
                "section_types": list(part.section_types) or ["Pack"],
            },
        }
        single_file_to_part = {
            rel: rel_path for rel in (list(part.files) or _all_repo_file_paths(run))
        }
        single_file_index_to_part = {
            rel: rel_path for rel in (list(part.files) or _all_repo_file_paths(run))
        }
        single_func_to_part = {
            canonical_id: rel_path
            for canonical_id in (
                list(part.canonical_ids) or _all_repo_canonical_ids(run)
            )
        }
        return (
            [part_entry],
            single_file_to_part,
            single_file_index_to_part,
            single_func_to_part,
        )

    parts: list[dict[str, Any]] = []
    file_to_part: dict[str, str] = {}
    file_index_to_part: dict[str, str] = {}
    func_to_part: dict[str, str] = {}
    part_number = 0

    for part in parts_in:
        kind = part.kind
        if kind == "part":
            part_number += 1
            current_part_number = part_number
        else:
            current_part_number = None
        rel_path = _relative_output_path(part.path, base_dir=base_dir)
        files = list(part.files)
        canonical_ids = [
            canonical_machine_ids.get(display_id, display_id)
            for display_id in part.canonical_ids
        ]
        section_types = list(part.section_types)
        display_canonical_ids = list(part.canonical_ids)
        parts.append(
            {
                "part_id": _part_id(
                    slug=run.slug,
                    kind=kind,
                    part_number=current_part_number,
                ),
                "path": rel_path,
                "kind": kind,
                "repo_slug": run.slug,
                "char_count": len(part.content),
                "line_count": len(part.content.splitlines()),
                "sha256_content": _sha256_text(part.content),
                "token_estimate": approx_token_count(part.content),
                "is_oversized": (
                    run.options.split_max_chars > 0
                    and kind != "index"
                    and len(part.content) > run.options.split_max_chars
                ),
                "contains": {
                    "files": files,
                    "canonical_ids": canonical_ids,
                    "display_canonical_ids": display_canonical_ids,
                    "section_types": section_types,
                },
            }
        )
        for rel in files:
            file_to_part.setdefault(rel, rel_path)
        for rel in _all_repo_file_paths(run):
            if anchor_for_file_index(rel) in part.content:
                file_index_to_part.setdefault(rel, rel_path)
        for canonical_id in canonical_ids:
            func_to_part.setdefault(canonical_id, rel_path)

    return parts, file_to_part, file_index_to_part, func_to_part


def _safety_flags_by_path(run: PackRun) -> dict[str, dict[str, bool]]:
    flags: dict[str, dict[str, bool]] = {}
    for item in run.safety_findings:
        rel = item.path.relative_to(run.pack_result.root).as_posix()
        entry = flags.setdefault(
            rel,
            {
                "is_redacted": False,
                "is_binary_skipped": False,
                "is_safety_skipped": False,
            },
        )
        if item.action == "redacted":
            entry["is_redacted"] = True
        else:
            if item.reason == "binary":
                entry["is_binary_skipped"] = True
            else:
                entry["is_safety_skipped"] = True
    return flags


def _full_file_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    file_index_to_part: dict[str, str],
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
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
        if markdown_path is not None and rel in file_markdown_ranges:
            file_entry["markdown_path"] = markdown_path
            file_entry["markdown_lines"] = file_markdown_ranges[rel]
        sha256_stubbed = manifest_entry.get("sha256_stubbed")
        if isinstance(sha256_stubbed, str) and sha256_stubbed:
            file_entry["sha256_stubbed"] = sha256_stubbed
        payload.append(file_entry)
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
) -> list[dict[str, Any]]:
    manifest_defs_by_local_id = _manifest_defs_by_local_id(run)
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)
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
            "ids": {
                "display_canonical_id": defn.id,
                "display_occurrence_id": defn.local_id,
                "machine_canonical_id": canonical_machine_ids[defn.id],
                "machine_occurrence_id": local_machine_ids[defn.local_id],
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
            },
        }
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


def _should_include_canonical_ids(run: PackRun) -> bool:
    return run.effective_layout == "stubs" or any(
        defn.id != defn.local_id for defn in run.pack_result.defs
    )


def _compact_file_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    file_index_to_part: dict[str, str],
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
    index_json_mode: str,
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for file_pack in sorted(
        run.pack_result.files,
        key=lambda item: item.path.relative_to(run.pack_result.root).as_posix(),
    ):
        rel = file_pack.path.relative_to(run.pack_result.root).as_posix()
        hrefs = {
            "source": href(file_to_part.get(rel), anchor_for_file_source(rel)),
        }
        index_href = href(file_index_to_part.get(rel), anchor_for_file_index(rel))
        if index_href is not None:
            hrefs["index"] = index_href
        file_entry: dict[str, Any] = {
            "path": rel,
            "part_path": file_to_part.get(rel),
            "hrefs": hrefs,
            "language": _fence_lang_for(rel),
            "language_detected": file_pack.language_detected,
            "symbol_backend_requested": file_pack.symbol_backend_requested,
            "symbol_backend_used": file_pack.symbol_backend_used,
            "symbol_extraction_status": file_pack.symbol_extraction_status,
        }
        if index_json_mode == "compact":
            file_entry["language_family"] = (
                file_pack.language_detected or _fence_lang_for(rel)
            )
        if markdown_path is not None and rel in file_markdown_ranges:
            file_entry["markdown_lines"] = file_markdown_ranges[rel]
        payload.append(file_entry)
    return payload


def _compact_symbol_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    func_to_part: dict[str, str],
    markdown_path: str | None,
    symbol_index_ranges: dict[str, dict[str, int]],
    canonical_markdown_ranges: dict[str, dict[str, int]],
    index_json_mode: str,
    include_symbol_index_lines: bool,
) -> list[dict[str, Any]]:
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)
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
            "path": rel,
            "qualname": defn.qualname,
            "kind": defn.kind,
            "def_line": defn.def_line,
            "end_line": defn.end_line,
            "file_part": file_to_part.get(rel),
            "file_href": href(file_to_part.get(rel), anchor_for_file_source(rel)),
        }
        if include_canonical_ids:
            symbol_entry["canonical_id"] = canonical_machine_ids[defn.id]
        if (
            index_json_mode == "compact"
            and include_symbol_index_lines
            and markdown_path is not None
        ):
            if defn.local_id in symbol_index_ranges:
                symbol_entry["index_markdown_lines"] = symbol_index_ranges[
                    defn.local_id
                ]
        if run.effective_layout == "stubs" and defn.id in run.canonical_sources:
            symbol_entry["canonical_part"] = func_to_part.get(
                canonical_machine_ids[defn.id]
            )
            symbol_entry["canonical_href"] = href(
                func_to_part.get(canonical_machine_ids[defn.id]),
                anchor_for_symbol(defn.id),
            )
            if (
                index_json_mode == "compact"
                and markdown_path is not None
                and defn.id in canonical_markdown_ranges
            ):
                symbol_entry["canonical_markdown_lines"] = canonical_markdown_ranges[
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


def _repository_common_payload(
    run: PackRun,
    *,
    repo_markdown_path: str | None,
    parts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "label": run.label,
        "slug": run.slug,
        "profile": run.options.profile,
        "split_policy": _split_policy(run),
        "layout": run.effective_layout,
        "nav_mode": run.effective_nav_mode,
        "locator_mode": (
            "anchors+line-ranges" if repo_markdown_path is not None else "anchors"
        ),
        "has_manifest": run.options.include_manifest,
        "has_machine_header": run.options.include_manifest,
        "manifest_sha256": run.manifest_sha256,
        "markdown_path": repo_markdown_path,
        "parts": parts,
        "safety": _safety_payload(run),
    }


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
        parts_input = repo_output_parts.get(run.slug, [])
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
        all_output_files.extend(part["path"] for part in parts)
        repo_markdown_path = parts[0]["path"] if len(parts) == 1 else None
        if index_json_mode == "full":
            files_payload = _full_file_payload(
                run,
                file_to_part=file_to_part,
                file_index_to_part=file_index_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
            )
            symbols_payload = _full_symbol_payload(
                run,
                file_to_part=file_to_part,
                func_to_part=func_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                symbol_index_ranges=symbol_index_ranges,
                canonical_markdown_ranges=canonical_markdown_ranges,
            )
            repository = {
                **_repository_common_payload(
                    run,
                    repo_markdown_path=repo_markdown_path,
                    parts=parts,
                ),
                "effective_layout": run.effective_layout,
                "contains_manifest": run.options.include_manifest,
                "files": files_payload,
                "symbols": symbols_payload,
                "lookup": _full_lookup_indexes(files_payload, symbols_payload),
            }
        else:
            features = _v2_feature_payload(run, index_json_mode=index_json_mode)
            files_payload = _compact_file_payload(
                run,
                file_to_part=file_to_part,
                file_index_to_part=file_index_to_part,
                markdown_path=markdown_path,
                file_markdown_ranges=file_markdown_ranges,
                index_json_mode=index_json_mode,
            )
            symbols_payload = _compact_symbol_payload(
                run,
                file_to_part=file_to_part,
                func_to_part=func_to_part,
                markdown_path=markdown_path,
                symbol_index_ranges=symbol_index_ranges,
                canonical_markdown_ranges=canonical_markdown_ranges,
                index_json_mode=index_json_mode,
                include_symbol_index_lines=features["symbol_index_lines"],
            )
            repository = {
                **_repository_common_payload(
                    run,
                    repo_markdown_path=repo_markdown_path,
                    parts=parts,
                ),
                "index_json_features": features,
                "files": files_payload,
                "symbols": symbols_payload,
            }
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
            else INDEX_JSON_FORMAT_VERSION_V2
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


def write_index_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
