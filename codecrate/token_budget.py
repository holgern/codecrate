from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .fences import is_fence_close, parse_fence_open


@dataclass(frozen=True)
class Part:
    path: Path
    content: str


def split_by_max_chars(markdown: str, out_path: Path, max_chars: int) -> list[Part]:
    """Split markdown into multiple files limited by *approximate* character count.

    For normal markdown, this splits on paragraph boundaries ("\n\n"). For Codecrate
    context packs, it performs a semantic split that avoids breaking code fences and
    rewrites intra-pack links so that an LLM can navigate across the generated parts.

    Notes:
    - The returned parts are intended for LLM consumption. The original,
      unsplit markdown should still be written to ``out_path``
      for machine parsing (unpack/validate).
    - When splitting a Codecrate pack, markdown line ranges like ``(L123-150)`` are
      removed because they are unstable across parts.
    """
    if max_chars <= 0 or len(markdown) <= max_chars:
        return [Part(path=out_path, content=markdown)]

    if _looks_like_codecrate_pack(markdown):
        return _split_codecrate_pack(markdown, out_path, max_chars)

    return _split_paragraphs(markdown, out_path, max_chars)


def _split_paragraphs(markdown: str, out_path: Path, max_chars: int) -> list[Part]:
    parts: list[Part] = []
    chunk: list[str] = []
    chunk_len = 0
    idx = 1

    for block in markdown.split("\n\n"):
        add = block + "\n\n"
        if chunk_len + len(add) > max_chars and chunk:
            part_path = out_path.with_name(
                f"{out_path.stem}.part{idx}{out_path.suffix}"
            )
            parts.append(Part(path=part_path, content="".join(chunk).rstrip() + "\n"))
            idx += 1
            chunk = []
            chunk_len = 0
        chunk.append(add)
        chunk_len += len(add)

    if chunk:
        part_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
        parts.append(Part(path=part_path, content="".join(chunk).rstrip() + "\n"))

    return parts


_FUNC_ANCHOR_RE = re.compile(r'^<a id="func-([0-9a-f]{8})"></a>\s*$')
_FILE_HEADING_RE = re.compile(r"^### `([^`]+)`")


def _enter_or_exit_fence(line: str, fence: str | None) -> str | None:
    if fence is None:
        opened = parse_fence_open(line)
        if opened is not None:
            return opened[0]
        return None
    if is_fence_close(line, fence):
        return None
    return fence


def _looks_like_codecrate_pack(markdown: str) -> bool:
    head = markdown.lstrip()[:200]
    return head.startswith("# Codecrate Context Pack") and "## Files" in markdown


def _find_heading_line_index(lines: list[str], heading: str) -> int | None:
    fence: str | None = None
    for i, line in enumerate(lines):
        fence = _enter_or_exit_fence(line, fence)
        if fence is None and line.startswith(heading):
            return i
    return None


def _drop_section(text: str, heading: str) -> str:
    """Drop a top-level '## ...' section from a Codecrate prefix (fence-safe)."""
    lines = text.splitlines(keepends=True)
    start = _find_heading_line_index(lines, heading)
    if start is None:
        return text

    fence: str | None = None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        fence = _enter_or_exit_fence(line, fence)
        if fence is not None:
            continue
        if line.startswith("## "):
            end = i
            break
    return "".join(lines[:start] + lines[end:])


def _split_codecrate_pack(markdown: str, out_path: Path, max_chars: int) -> list[Part]:
    """Semantic split for Codecrate packs.

    Strategy:
    - Keep the "index" prefix (everything before the first content section: Function
      Library or Files) in part1.
    - Split the remaining content only at safe boundaries:
        * function library entry anchors (<a id="func-..."></a>)
        * file blocks (### `path`) inside the Files section
        * section headings (## Function Library / ## Files)
      while never splitting inside a fenced code block.
    - Rewrite links across parts:
        * Symbol Index links target the part that contains the relevant anchor.
        * "jump to index" links in file blocks point back to part1.
        * func jump links inside file symbol lists point to the part containing the
          function library entry.
    - Strip markdown line-range decorations like (L10-20) because they don't survive
      splitting.
    """
    lines = markdown.splitlines(keepends=True)

    idx_files = _find_heading_line_index(lines, "## Files")
    idx_funcs = _find_heading_line_index(lines, "## Function Library")
    if idx_files is None and idx_funcs is None:
        return _split_paragraphs(markdown, out_path, max_chars)

    content_start = min(i for i in [idx_files, idx_funcs] if i is not None)

    # Parts are intended for LLM consumption; drop the Manifest to save tokens
    # while keeping the unsplit output (written by the CLI) fully machine-readable.
    prefix = "".join(lines[:content_start])
    prefix = _drop_section(prefix, "## Manifest")
    prefix = prefix.rstrip() + "\n"
    content_lines = lines[content_start:]

    breakpoints: list[int] = [0]
    fence: str | None = None
    in_files = False
    for i, line in enumerate(content_lines):
        fence = _enter_or_exit_fence(line, fence)
        if fence is not None:
            continue

        if line.startswith("## Files"):
            in_files = True
            breakpoints.append(i)
            continue
        if line.startswith("## Function Library"):
            breakpoints.append(i)
            continue

        if line.startswith('<a id="func-'):
            breakpoints.append(i)
            continue

        if in_files and line.startswith("### `"):
            breakpoints.append(i)

    breakpoints = sorted(set(bp for bp in breakpoints if 0 <= bp < len(content_lines)))
    if not breakpoints or breakpoints[0] != 0:
        breakpoints = [0] + breakpoints
    breakpoints.append(len(content_lines))

    blocks: list[str] = []
    for a, b in zip(breakpoints, breakpoints[1:], strict=False):
        if a == b:
            continue
        blocks.append("".join(content_lines[a:b]))

    parts: list[Part] = []
    idx = 1
    part1_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
    parts.append(Part(path=part1_path, content=prefix))
    idx += 1

    chunk: list[str] = []
    chunk_len = 0
    for block in blocks:
        if chunk and chunk_len + len(block) > max_chars:
            part_path = out_path.with_name(
                f"{out_path.stem}.part{idx}{out_path.suffix}"
            )
            parts.append(Part(path=part_path, content="".join(chunk).rstrip() + "\n"))
            idx += 1
            chunk = []
            chunk_len = 0
        chunk.append(block)
        chunk_len += len(block)

    if chunk:
        part_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
        parts.append(Part(path=part_path, content="".join(chunk).rstrip() + "\n"))

    file_to_part: dict[str, str] = {}
    func_to_part: dict[str, str] = {}
    for part in parts[1:]:
        _scan_part_for_anchors(part.content, part.path.name, file_to_part, func_to_part)

    index_name = parts[0].path.name
    parts[0] = Part(
        path=parts[0].path,
        content=_rewrite_part1(parts[0].content, file_to_part, func_to_part),
    )

    rewritten_parts: list[Part] = [parts[0]]
    for part in parts[1:]:
        text = part.content
        text = _strip_markdown_line_ranges(text)
        text = _rewrite_jump_to_index(text, index_name)
        text = _rewrite_func_links(text, func_to_part)
        rewritten_parts.append(Part(path=part.path, content=text))

    return rewritten_parts


def _scan_part_for_anchors(
    text: str,
    part_filename: str,
    file_to_part: dict[str, str],
    func_to_part: dict[str, str],
) -> None:
    fence: str | None = None
    for line in text.splitlines():
        fence = _enter_or_exit_fence(line, fence)
        if fence is not None:
            continue

        m = _FUNC_ANCHOR_RE.match(line.strip())
        if m:
            func_to_part[m.group(1).upper()] = part_filename
            continue

        m2 = _FILE_HEADING_RE.match(line)
        if m2:
            file_to_part[m2.group(1)] = part_filename


def _strip_markdown_line_ranges(text: str) -> str:
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        was_in_fence = fence is not None
        fence = _enter_or_exit_fence(line, fence)
        if was_in_fence or parse_fence_open(line) is not None:
            out.append(line)
            continue
        line = re.sub(r"\s*\(L\d+-\d+\)", "", line)
        out.append(line)
    return "".join(out)


def _rewrite_jump_to_index(text: str, index_filename: str) -> str:
    out: list[str] = []
    fence: str | None = None
    pat = re.compile(r"\[jump to index\]\(\#(file-[^)]+)\)")
    for line in text.splitlines(keepends=True):
        was_in_fence = fence is not None
        fence = _enter_or_exit_fence(line, fence)
        if was_in_fence or parse_fence_open(line) is not None:
            out.append(line)
            continue
        line = pat.sub(rf"[jump to index]({index_filename}#\1)", line)
        out.append(line)
    return "".join(out)


def _rewrite_func_links(text: str, func_to_part: dict[str, str]) -> str:
    out: list[str] = []
    fence: str | None = None
    pat = re.compile(r"\(\#(func-[0-9a-f]{8})\)")
    for line in text.splitlines(keepends=True):
        was_in_fence = fence is not None
        fence = _enter_or_exit_fence(line, fence)
        if was_in_fence or parse_fence_open(line) is not None:
            out.append(line)
            continue
        if "(#func-" in line:

            def repl(m: re.Match[str]) -> str:
                anchor = m.group(1)
                fid = anchor.split("-")[1].upper()
                part = func_to_part.get(fid)
                if not part:
                    return m.group(0)
                return f"({part}#{anchor})"

            line = pat.sub(repl, line)
        out.append(line)
    return "".join(out)


def _rewrite_part1(
    text: str, file_to_part: dict[str, str], func_to_part: dict[str, str]
) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    fence: str | None = None
    in_index = False
    current_file_part: str | None = None

    for line in lines:
        was_in_fence = fence is not None
        fence = _enter_or_exit_fence(line, fence)

        if not was_in_fence and fence is None and line.startswith("## Symbol Index"):
            in_index = True
            out.append(line)
            continue

        if (
            in_index
            and fence is None
            and line.startswith("## ")
            and not line.startswith("## Symbol Index")
        ):
            in_index = False
            current_file_part = None
            out.append(line)
            continue

        if not in_index or was_in_fence or fence is not None:
            out.append(line)
            continue

        m_file = _FILE_HEADING_RE.match(line)
        if m_file:
            rel = m_file.group(1)
            current_file_part = file_to_part.get(rel)
            empty = " (empty)" if "(empty)" in line else ""
            m_jump = re.search(r"\[jump\]\(\#([^)]+)\)", line)
            anchor = m_jump.group(1) if m_jump else None
            if current_file_part and anchor:
                out.append(
                    f"### `{rel}`{empty} (in {current_file_part}) — "
                    f"[jump]({current_file_part}#{anchor})\n"
                )
            else:
                out.append(re.sub(r"\s*\(L\d+-\d+\)", "", line))
            continue

        if line.lstrip().startswith("- "):
            ln = re.sub(r"\s*\(L\d+-\d+\)", "", line)
            m = re.search(r"\[jump\]\(\#func-([0-9a-f]{8})\)", ln)
            if m:
                fid = m.group(1).upper()
                part = func_to_part.get(fid) or current_file_part
                if part:
                    ln = ln.replace("— [jump]", f"(in {part}) — [jump]")
                    ln = re.sub(r"\(\#(func-[0-9a-f]{8})\)", rf"({part}#\1)", ln)
                out.append(ln)
                continue
            if current_file_part:
                ln = ln.rstrip("\n") + f" (in {current_file_part})\n"
            out.append(ln)
            continue

        out.append(re.sub(r"\s*\(L\d+-\d+\)", "", line))

    return _strip_markdown_line_ranges("".join(out))
