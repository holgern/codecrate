from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from .fences import is_fence_close, parse_fence_open
from .formats import FENCE_MACHINE_HEADER, FENCE_MANIFEST, MISSING_MANIFEST_ERROR
from .udiff import normalize_newlines


@dataclass(frozen=True)
class PackedMarkdown:
    manifest: dict
    machine_header: dict | None
    canonical_sources: dict[str, str]  # id -> python code
    # NOTE: we don't strictly need stubbed files for unpack, but helpful for debugging
    stubbed_files: dict[str, str]  # rel path -> code


def _iter_fenced_blocks(lines: list[str]) -> Iterator[tuple[str, str]]:
    i = 0
    while i < len(lines):
        opened = parse_fence_open(lines[i])
        if opened is None:
            i += 1
            continue
        fence, lang = opened
        i += 1
        buf: list[str] = []
        while i < len(lines) and not is_fence_close(lines[i], fence):
            buf.append(lines[i])
            i += 1
        if i < len(lines) and is_fence_close(lines[i], fence):
            i += 1
        yield lang, "".join(buf)


def _section_bounds(title: str, text_lines: list[str]) -> tuple[int, int]:
    start = None
    for i, ln in enumerate(text_lines):
        if ln.strip() == title:
            start = i + 1
            break
    if start is None:
        return (0, len(text_lines))
    end = len(text_lines)
    for j in range(start, len(text_lines)):
        if text_lines[j].startswith("## ") and text_lines[j].strip() != title:
            end = j
            break
    return (start, end)


def _parse_function_library(text_lines: list[str]) -> dict[str, str]:
    canonical_sources: dict[str, str] = {}
    fl_start, fl_end = _section_bounds("## Function Library", text_lines)
    for idx in range(fl_start, fl_end):
        line = text_lines[idx]
        if not line.startswith("### "):
            continue

        # Support both header styles:
        # - v4 current: "### <ID>"
        # - older:      "### <ID> — <extra metadata>"
        title = line.replace("###", "", 1).strip()
        maybe_id = title.split(" — ", 1)[0].strip()
        if not maybe_id:
            continue

        j = idx + 1
        fence = ""
        while j < fl_end:
            opened = parse_fence_open(text_lines[j])
            if opened is not None and opened[1] == "python":
                fence = opened[0]
                break
            j += 1
        if j < fl_end and fence:
            k = j + 1
            buf: list[str] = []
            while k < fl_end and not is_fence_close(text_lines[k], fence):
                buf.append(text_lines[k])
                k += 1
            if buf:
                chunk = normalize_newlines("".join(buf))
                if not chunk.endswith("\n"):
                    chunk += "\n"
                canonical_sources[maybe_id] = chunk
    return canonical_sources


def _parse_stubbed_files(text_lines: list[str]) -> dict[str, str]:
    stubbed_files: dict[str, str] = {}
    fs_start, fs_end = _section_bounds("## Files", text_lines)
    i = fs_start
    while i < fs_end:
        line = text_lines[i]
        if line.startswith("### `") and "`" in line:
            start = line.find("`") + 1
            end = line.find("`", start)
            rel = line[start:end]
            parts: list[str] = []
            j = i + 1
            while j < fs_end and not (
                text_lines[j].startswith("### `") and "`" in text_lines[j]
            ):
                opened = parse_fence_open(text_lines[j])
                if opened is not None:
                    fence = opened[0]
                    k = j + 1
                    buf: list[str] = []
                    while k < fs_end and not is_fence_close(text_lines[k], fence):
                        buf.append(text_lines[k])
                        k += 1
                    if buf:
                        chunk = normalize_newlines("".join(buf))
                        if not chunk.endswith("\n"):
                            chunk += "\n"
                        parts.append(chunk)
                    j = k + 1
                    continue
                j += 1
            if parts:
                stubbed_files[rel] = "".join(parts)
            else:
                stubbed_files[rel] = ""
            i = j
            continue
        i += 1
    return stubbed_files


def parse_packed_markdown(text: str) -> PackedMarkdown:
    text_norm = normalize_newlines(text)
    lines = text_norm.splitlines(keepends=True)
    manifest = None
    machine_header: dict | None = None
    for lang, body in _iter_fenced_blocks(lines):
        if lang == FENCE_MACHINE_HEADER and machine_header is None:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                machine_header = parsed
        if lang == FENCE_MANIFEST:
            manifest = json.loads(body)
            break
    if manifest is None:
        raise ValueError(MISSING_MANIFEST_ERROR)

    text_lines = text_norm.splitlines(keepends=True)
    canonical_sources = _parse_function_library(text_lines)
    stubbed_files = _parse_stubbed_files(text_lines)

    return PackedMarkdown(
        manifest=manifest,
        machine_header=machine_header,
        canonical_sources=canonical_sources,
        stubbed_files=stubbed_files,
    )
