from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..output_model import PackRun, RenderMetadata
from ..token_budget import Part
from .common import (
    _line_range,
    _line_ranges_from_metadata,
    _locator_line_range,
    _locator_line_range_from_markdown,
    _relative_output_path,
    _sorted_unique_parts,
)

_FILE_HEADING_RE = re.compile(r"^### `([^`]+)`")

_FUNCTION_LIBRARY_HEADING_RE = re.compile(r"^### ([0-9A-F]{8})\s*$")

_FUNC_ANCHOR_RE = re.compile(r'^<a id="func-([0-9a-f]{8})"></a>\s*$')


def _locator_space_order(locator_space: str) -> tuple[str, str | None]:
    if locator_space == "dual":
        return "reconstructed", "markdown"
    if locator_space == "reconstructed":
        return "reconstructed", None
    return "markdown", None


def _includes_locator_space(locator_space: str, space: str) -> bool:
    if locator_space == "dual":
        return space in {"markdown", "reconstructed"}
    return locator_space == space


def _repo_reconstructed_root(run: PackRun, *, repo_count: int) -> str | None:
    if repo_count <= 1:
        return None
    if not _includes_locator_space(run.options.locator_space, "reconstructed"):
        return None
    return run.slug


def _reconstructed_locator_path(
    rel_path: str, *, reconstructed_root: str | None
) -> str:
    if not reconstructed_root:
        return rel_path
    return Path(reconstructed_root, rel_path).as_posix()


def _file_locator_payload(
    run: PackRun,
    *,
    rel_path: str,
    line_count: int,
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
    reconstructed_root: str | None,
) -> dict[str, Any]:
    locators: dict[str, Any] = {}
    if _includes_locator_space(run.options.locator_space, "markdown"):
        markdown_lines = _locator_line_range_from_markdown(
            file_markdown_ranges.get(rel_path)
        )
        if markdown_path is not None and markdown_lines is not None:
            locators["markdown"] = {
                "path": markdown_path,
                "lines": markdown_lines,
            }
    if _includes_locator_space(run.options.locator_space, "reconstructed"):
        locators["reconstructed"] = {
            "path": _reconstructed_locator_path(
                rel_path, reconstructed_root=reconstructed_root
            ),
            "lines": _locator_line_range(1, line_count),
        }
    return locators


def _symbol_locator_payload(
    run: PackRun,
    *,
    rel_path: str,
    def_line: int,
    decorator_start: int,
    body_start: int,
    end_line: int,
    local_id: str,
    canonical_id: str,
    markdown_path: str | None,
    file_markdown_ranges: dict[str, dict[str, int]],
    symbol_index_ranges: dict[str, dict[str, int]],
    canonical_markdown_ranges: dict[str, dict[str, int]],
    reconstructed_root: str | None,
) -> dict[str, Any]:
    locators: dict[str, Any] = {}
    if _includes_locator_space(run.options.locator_space, "markdown") and markdown_path:
        markdown_locator: dict[str, Any] = {
            "path": markdown_path,
        }
        file_lines = _locator_line_range_from_markdown(
            file_markdown_ranges.get(rel_path)
        )
        if file_lines is not None:
            markdown_locator["file_lines"] = file_lines
        index_lines = _locator_line_range_from_markdown(
            symbol_index_ranges.get(local_id)
        )
        if index_lines is not None:
            markdown_locator["symbol_index_lines"] = index_lines
        canonical_lines = _locator_line_range_from_markdown(
            canonical_markdown_ranges.get(canonical_id)
        )
        if canonical_lines is not None:
            markdown_locator["canonical_lines"] = canonical_lines
        if len(markdown_locator) > 1:
            locators["markdown"] = markdown_locator
    if _includes_locator_space(run.options.locator_space, "reconstructed"):
        start_line = decorator_start or def_line
        locators["reconstructed"] = {
            "path": _reconstructed_locator_path(
                rel_path, reconstructed_root=reconstructed_root
            ),
            "lines": _locator_line_range(start_line, end_line),
            "body_lines": _locator_line_range(body_start, end_line),
        }
    return locators


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
