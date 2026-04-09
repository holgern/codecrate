from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .fences import is_fence_close, parse_fence_open


@dataclass(frozen=True)
class Part:
    path: Path
    content: str
    kind: Literal["pack", "index", "part"] = "pack"
    files: tuple[str, ...] = ()
    canonical_ids: tuple[str, ...] = ()
    section_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Block:
    content: str
    files: tuple[str, ...] = ()
    canonical_ids: tuple[str, ...] = ()
    section_types: tuple[str, ...] = ()


def split_by_max_chars(
    markdown: str,
    out_path: Path,
    max_chars: int,
    *,
    strict: bool = False,
    allow_cut_files: bool = False,
) -> list[Part]:
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
    - Oversized logical blocks remain intact by default. ``strict=True`` turns that
      case into an error. ``allow_cut_files=True`` can cut oversized file blocks in
      Codecrate packs across multiple parts.
    """
    if max_chars <= 0 or len(markdown) <= max_chars:
        return [_single_part(markdown, out_path)]

    if _looks_like_codecrate_pack(markdown):
        return _split_codecrate_pack(
            markdown,
            out_path,
            max_chars,
            strict=strict,
            allow_cut_files=allow_cut_files,
        )

    return _split_paragraphs(markdown, out_path, max_chars, strict=strict)


def _single_part(markdown: str, out_path: Path) -> Part:
    if not _looks_like_codecrate_pack(markdown):
        return Part(path=out_path, content=markdown)
    return Part(
        path=out_path,
        content=markdown,
        kind="pack",
        files=tuple(_scan_pack_file_paths(markdown)),
        canonical_ids=tuple(_scan_pack_function_ids(markdown)),
        section_types=("Pack",),
    )


def _split_paragraphs(
    markdown: str,
    out_path: Path,
    max_chars: int,
    *,
    strict: bool = False,
) -> list[Part]:
    parts: list[Part] = []
    chunk: list[str] = []
    chunk_len = 0
    idx = 1

    for block in markdown.split("\n\n"):
        add = block + "\n\n"
        if strict and len(add) > max_chars:
            raise ValueError(
                "split_strict: paragraph block exceeds split_max_chars "
                f"({len(add)} > {max_chars})"
            )
        if chunk_len + len(add) > max_chars and chunk:
            part_path = out_path.with_name(
                f"{out_path.stem}.part{idx}{out_path.suffix}"
            )
            parts.append(
                Part(
                    path=part_path, content="".join(chunk).rstrip() + "\n", kind="part"
                )
            )
            idx += 1
            chunk = []
            chunk_len = 0
        chunk.append(add)
        chunk_len += len(add)

    if chunk:
        part_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
        parts.append(
            Part(path=part_path, content="".join(chunk).rstrip() + "\n", kind="part")
        )

    return parts


_FUNC_ANCHOR_RE = re.compile(r'^<a id="func-([0-9a-f]{8})"></a>\s*$')
_FILE_HEADING_RE = re.compile(r"^### `([^`]+)`")
_FILE_CUT_REWRITE_MARGIN = 64


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


def _scan_section_lines(markdown_text: str, section_title: str) -> list[str]:
    lines = markdown_text.splitlines()
    fence: str | None = None
    start: int | None = None

    for i, line in enumerate(lines):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            if line.strip() == section_title:
                start = i + 1
                break
        elif is_fence_close(line, fence):
            fence = None

    if start is None:
        return []

    fence = None
    end = len(lines)
    for j in range(start, len(lines)):
        line = lines[j]
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            if line.startswith("## ") and line.strip() != section_title:
                end = j
                break
        elif is_fence_close(line, fence):
            fence = None

    return lines[start:end]


def _scan_pack_file_paths(markdown_text: str) -> list[str]:
    paths: list[str] = []
    fence: str | None = None
    for line in _scan_section_lines(markdown_text, "## Files"):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
        else:
            if is_fence_close(line, fence):
                fence = None
            continue

        match = _FILE_HEADING_RE.match(line)
        if match:
            paths.append(match.group(1))
    return sorted(set(paths), key=lambda item: (item.lower(), item))


def _scan_pack_function_ids(markdown_text: str) -> list[str]:
    ids: list[str] = []
    fence: str | None = None
    for line in _scan_section_lines(markdown_text, "## Function Library"):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
        else:
            if is_fence_close(line, fence):
                fence = None
            continue

        if line.startswith("### "):
            title = line.replace("###", "", 1).strip()
            if title:
                ids.append(title.split(" — ", 1)[0].strip())
    return sorted(set(ids))


def _scan_top_level_headings(markdown_text: str) -> tuple[str, ...]:
    headings: list[str] = []
    fence: str | None = None
    for line in markdown_text.splitlines():
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            if line.startswith("## "):
                title = line[3:].strip()
                if title and title != "Manifest":
                    headings.append(title)
        elif is_fence_close(line, fence):
            fence = None
    return tuple(dict.fromkeys(headings))


def _block_from_content(block: str) -> _Block:
    first = block.lstrip().splitlines()[0].strip() if block.strip() else ""
    if first.startswith("## Files"):
        return _Block(content=block, section_types=("Files",))
    if first.startswith("## Function Library"):
        return _Block(content=block, section_types=("Function Library",))
    file_match = _FILE_HEADING_RE.match(first)
    if file_match:
        return _Block(
            content=block, files=(file_match.group(1),), section_types=("Files",)
        )
    func_match = _FUNC_ANCHOR_RE.match(first)
    if func_match:
        return _Block(
            content=block,
            canonical_ids=(func_match.group(1).upper(),),
            section_types=("Function Library",),
        )
    return _Block(content=block)


def _split_codecrate_pack(  # noqa: C901
    markdown: str,
    out_path: Path,
    max_chars: int,
    *,
    strict: bool = False,
    allow_cut_files: bool = False,
) -> list[Part]:
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

    blocks: list[_Block] = []
    for a, b in zip(breakpoints, breakpoints[1:], strict=False):
        if a == b:
            continue
        blocks.append(_block_from_content("".join(content_lines[a:b])))

    if allow_cut_files:
        cut_blocks: list[_Block] = []
        for block in blocks:
            if len(block.content) > max_chars and _is_file_block(block.content):
                cut_blocks.extend(_split_codecrate_file_block(block, max_chars))
            else:
                cut_blocks.append(block)
        blocks = cut_blocks

    if strict:
        for block in blocks:
            if len(block.content) <= max_chars:
                continue
            raise ValueError(
                "split_strict: logical block exceeds split_max_chars "
                f"for {_describe_codecrate_block(block.content)} "
                f"({len(block.content)} > {max_chars})"
            )

    parts: list[Part] = []
    idx = 1
    part1_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
    parts.append(
        Part(
            path=part1_path,
            content=prefix,
            kind="index",
            section_types=_scan_top_level_headings(prefix),
        )
    )
    idx += 1

    chunk: list[_Block] = []
    chunk_len = 0
    for block in blocks:
        if chunk and chunk_len + len(block.content) > max_chars:
            part_path = out_path.with_name(
                f"{out_path.stem}.part{idx}{out_path.suffix}"
            )
            parts.append(_part_from_blocks(part_path, chunk))
            idx += 1
            chunk = []
            chunk_len = 0
        chunk.append(block)
        chunk_len += len(block.content)

    if chunk:
        part_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
        parts.append(_part_from_blocks(part_path, chunk))

    file_to_part: dict[str, str] = {}
    func_to_part: dict[str, str] = {}
    for part in parts[1:]:
        for rel in part.files:
            file_to_part.setdefault(rel, part.path.name)
        for canonical_id in part.canonical_ids:
            func_to_part.setdefault(canonical_id, part.path.name)

    index_name = parts[0].path.name
    parts[0] = Part(
        path=parts[0].path,
        content=_rewrite_part1(parts[0].content, file_to_part, func_to_part),
        kind=parts[0].kind,
        files=parts[0].files,
        canonical_ids=parts[0].canonical_ids,
        section_types=parts[0].section_types,
    )

    rewritten_parts: list[Part] = [parts[0]]
    for part in parts[1:]:
        text = part.content
        text = _strip_markdown_line_ranges(text)
        text = _rewrite_jump_to_index(text, index_name)
        text = _rewrite_func_links(text, func_to_part)
        rewritten_parts.append(
            Part(
                path=part.path,
                content=text,
                kind=part.kind,
                files=part.files,
                canonical_ids=part.canonical_ids,
                section_types=part.section_types,
            )
        )

    return rewritten_parts


def _is_file_block(block: str) -> bool:
    first = block.lstrip().splitlines()[0] if block.strip() else ""
    return bool(_FILE_HEADING_RE.match(first))


def _describe_codecrate_block(block: str) -> str:
    if not block.strip():
        return "empty block"
    first = block.lstrip().splitlines()[0].strip()
    file_match = _FILE_HEADING_RE.match(first)
    if file_match:
        return f"file '{file_match.group(1)}'"
    func_match = _FUNC_ANCHOR_RE.match(first)
    if func_match:
        return f"function '{func_match.group(1).upper()}'"
    if first.startswith("## "):
        return first[3:].strip() or "section heading"
    return "logical block"


def _continued_file_heading(block: str) -> str:
    first = block.lstrip().splitlines()[0] if block.strip() else "### (continued)"
    match = _FILE_HEADING_RE.match(first)
    if match:
        return f"### `{match.group(1)}` (continued)\n\n"
    return "### (continued)\n\n"


def _split_lines_by_limit(lines: list[str], max_chars: int) -> list[list[str]]:
    if max_chars <= 0:
        return [lines]

    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        if current and current_len + len(line) > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append(current)
    return chunks


def _part_from_blocks(path: Path, blocks: list[_Block]) -> Part:
    files: list[str] = []
    canonical_ids: list[str] = []
    section_types: list[str] = []
    for block in blocks:
        files.extend(block.files)
        canonical_ids.extend(block.canonical_ids)
        section_types.extend(block.section_types)
    return Part(
        path=path,
        content="".join(block.content for block in blocks).rstrip() + "\n",
        kind="part",
        files=tuple(dict.fromkeys(files)),
        canonical_ids=tuple(dict.fromkeys(canonical_ids)),
        section_types=tuple(dict.fromkeys(section_types)),
    )


def _split_codecrate_file_block(block: _Block, max_chars: int) -> list[_Block]:
    lines = block.content.splitlines(keepends=True)
    open_idx: int | None = None
    close_idx: int | None = None
    fence: str | None = None

    for idx, line in enumerate(lines):
        if open_idx is None:
            opened = parse_fence_open(line)
            if opened is None:
                continue
            open_idx = idx
            fence = opened[0]
            continue
        if fence is not None and is_fence_close(line, fence):
            close_idx = idx
            break

    if open_idx is None or close_idx is None or close_idx <= open_idx + 1:
        return [block]

    prefix_lines = lines[:open_idx]
    fence_open = lines[open_idx]
    code_lines = lines[open_idx + 1 : close_idx]
    fence_close = lines[close_idx]
    suffix_lines = lines[close_idx + 1 :]

    first_prefix = "".join(prefix_lines) + fence_open
    continued_prefix = _continued_file_heading(block.content) + fence_open
    middle_suffix = fence_close
    last_suffix = fence_close + "".join(suffix_lines)
    available = min(
        max_chars - len(first_prefix) - len(middle_suffix),
        max_chars - len(continued_prefix) - len(last_suffix),
    )
    available -= _FILE_CUT_REWRITE_MARGIN
    if available <= 0:
        return [block]

    code_chunks = _split_lines_by_limit(code_lines, available)
    if len(code_chunks) <= 1:
        return [block]

    split_blocks: list[_Block] = []
    last_chunk_index = len(code_chunks) - 1
    for idx, chunk in enumerate(code_chunks):
        if idx == 0:
            prefix = first_prefix
        else:
            prefix = continued_prefix
        suffix = last_suffix if idx == last_chunk_index else middle_suffix
        split_blocks.append(
            _Block(
                content=prefix + "".join(chunk) + suffix,
                files=block.files,
                canonical_ids=block.canonical_ids,
                section_types=block.section_types,
            )
        )
    return split_blocks


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
