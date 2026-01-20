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
        # skip closing fence
        if i < len(lines) and _FENCE_END_RE.match(lines[i]):
            i += 1
        yield lang, "".join(buf)


def parse_packed_markdown(text: str) -> PackedMarkdown:
    lines = text.splitlines(keepends=True)
    manifest = None
    canonical_sources: dict[str, str] = {}
    stubbed_files: dict[str, str] = {}

    # 1) find manifest
    for lang, body in _iter_fenced_blocks(lines):
        if lang == "codecrate-manifest":
            manifest = json.loads(body)
            break
    if manifest is None:
        raise ValueError("No codecrate-manifest block found")

    # 2) parse canonical library blocks by scanning headings "### <ID> —"
    # We use a simple heuristic: in the Function Library section, python fenced blocks appear
    # and the immediately preceding heading contains the ID at the start.
    text_lines = text.splitlines()
    for idx, line in enumerate(text_lines):
        if line.startswith("### ") and " — " in line:
            # Try to extract the leading token as ID
            maybe_id = line.split(" — ", 1)[0].replace("###", "").strip()
            # look ahead for a python fence (may have blank lines or other content in between)
            j = idx + 1
            while j < len(text_lines) and text_lines[j].strip() != "```python":
                j += 1
            if j < len(text_lines) and text_lines[j].strip() == "```python":
                # collect until closing fence
                k = j + 1
                buf = []
                while k < len(text_lines) and text_lines[k].strip() != "```":
                    buf.append(text_lines[k])
                    k += 1
                if buf:
                    canonical_sources[maybe_id] = "\n".join(buf).rstrip() + "\n"

    # 3) parse stubbed files in Files section:
    # We look for headings "### `<path>`" then the next python fence, store it.
    i = 0
    while i < len(text_lines):
        line = text_lines[i]
        if line.startswith("### `") and "`" in line:
            # extract between backticks (first one is the path)
            start = line.find("`") + 1
            end = line.find("`", start)
            rel = line[start:end]
            # find next ```python (may have blank lines or other content in between)
            j = i + 1
            while j < len(text_lines) and text_lines[j].strip() != "```python":
                j += 1
            if j < len(text_lines) and text_lines[j].strip() == "```python":
                k = j + 1
                buf = []
                while k < len(text_lines) and text_lines[k].strip() != "```":
                    buf.append(text_lines[k])
                    k += 1
                stubbed_files[rel] = "\n".join(buf).rstrip() + "\n"
                i = k + 1
                continue
        i += 1

    return PackedMarkdown(
        manifest=manifest,
        canonical_sources=canonical_sources,
        stubbed_files=stubbed_files,
    )
