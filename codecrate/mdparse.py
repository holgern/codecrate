from __future__ import annotations

import json
import re
from dataclasses import dataclass

_CODE_FENCE_RE = re.compile(r"^```([a-zA-Z0-9_-]+)\s*$")
_FENCE_END_RE = re.compile(r"^```\s*$")


@dataclass(frozen=True)
class PackedMarkdown:
    manifest: dict
    canonical_sources: dict[str, str]  # id -> python code
    # NOTE: we don't strictly need stubbed files for unpack, but helpful for debugging
    stubbed_files: dict[str, str]  # rel path -> code


def _iter_fenced_blocks(lines: list[str]):
    i = 0
    while i < len(lines):
        m = _CODE_FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        lang = m.group(1)
        i += 1
        buf = []
        while i < len(lines) and not _FENCE_END_RE.match(lines[i]):
            buf.append(lines[i])
            i += 1
        if i < len(lines) and _FENCE_END_RE.match(lines[i]):
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
        while j < fl_end and text_lines[j].strip() != "```python":
            j += 1
        if j < fl_end and text_lines[j].strip() == "```python":
            k = j + 1
            buf: list[str] = []
            while k < fl_end and text_lines[k].strip() != "```":
                buf.append(text_lines[k])
                k += 1
            if buf:
                canonical_sources[maybe_id] = "\n".join(buf).rstrip() + "\n"
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
                fence = text_lines[j].strip()
                if fence.startswith("```") and fence != "```":
                    k = j + 1
                    buf: list[str] = []
                    while k < fs_end and text_lines[k].strip() != "```":
                        buf.append(text_lines[k])
                        k += 1
                    if buf:
                        chunk = "\n".join(buf)
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
    lines = text.splitlines(keepends=True)
    manifest = None
    for lang, body in _iter_fenced_blocks(lines):
        if lang == "codecrate-manifest":
            manifest = json.loads(body)
            break
    if manifest is None:
        raise ValueError(
            "No codecrate-manifest block found. This pack cannot be used for "
            "unpack/patch/validate-pack; re-run `codecrate pack` with --manifest "
            "(or omit --no-manifest)."
        )

    text_lines = text.splitlines()
    canonical_sources = _parse_function_library(text_lines)
    stubbed_files = _parse_stubbed_files(text_lines)

    return PackedMarkdown(
        manifest=manifest,
        canonical_sources=canonical_sources,
        stubbed_files=stubbed_files,
    )
