from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .manifest import to_manifest
from .model import ClassRef, FilePack, PackResult
from .parse import parse_symbols


def _anchor_for(defn_id: str, module: str, qualname: str) -> str:
    # Anchors should be stable under dedupe: multiple defs can share the same
    # canonical id, so we anchor by id only.
    base = f"func-{defn_id}".lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in base)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def _file_anchor(rel_path: str) -> str:
    base = f"file-{rel_path}".lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in base)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def _file_src_anchor(rel_path: str) -> str:
    # Separate anchor namespace from _file_anchor(): index vs file content.
    base = f"src-{rel_path}".lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in base)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def _file_range(line_count: int) -> str:
    return "(empty)" if line_count == 0 else f"(L1-{line_count})"


def _ensure_nl(s: str) -> str:
    return s if (not s or s.endswith("\n")) else (s + "\n")


def _fence_lang_for(rel_path: str) -> str:
    ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
    return {
        "py": "python",
        "toml": "toml",
        "rst": "rst",
        "md": "markdown",
        "txt": "text",
        "ini": "ini",
        "cfg": "ini",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
    }.get(ext, "text")


def _range_token(kind: str, key: str) -> str:
    return f"<<CC:{kind}:{key}>>"


def _format_range(start: int | None, end: int | None) -> str:
    if start is None or end is None or start > end:
        return "(empty)"
    return f"(L{start}-{end})"


def _extract_rel_path(line: str) -> str | None:
    if not line.startswith("### `"):
        return None
    start = line.find("`") + 1
    end = line.find("`", start)
    if start <= 0 or end <= start:
        return None
    return line[start:end]


def _next_non_empty_line_idx(lines: list[str], start: int) -> int | None:
    for idx in range(start, len(lines)):
        if lines[idx].strip():
            return idx
    return None


def _is_file_block_end(lines: list[str], fence_end_idx: int) -> bool:
    next_idx = _next_non_empty_line_idx(lines, fence_end_idx + 1)
    if next_idx is None:
        return True
    next_line = lines[next_idx]
    return (
        next_line.startswith("### `")
        or next_line.startswith("**Symbols**")
        or next_line.startswith("# Repository:")
    )


def _is_function_block_end(lines: list[str], fence_end_idx: int) -> bool:
    next_idx = _next_non_empty_line_idx(lines, fence_end_idx + 1)
    if next_idx is None:
        return True
    next_line = lines[next_idx]
    return (
        next_line.startswith('<a id="func-')
        or next_line.startswith("### ")
        or next_line.startswith("## Files")
        or next_line.startswith("# Repository:")
    )


def _scan_file_blocks(lines: list[str]) -> dict[str, tuple[int, int] | None]:
    ranges: dict[str, tuple[int, int] | None] = {}
    in_files = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "## Files":
            in_files = True
            i += 1
            continue
        if in_files and line.startswith("## ") and line.strip() != "## Files":
            break
        if in_files and line.startswith("### `"):
            rel = _extract_rel_path(line)
            if rel is None:
                i += 1
                continue
            j = i + 1
            while j < len(lines) and not (
                lines[j].strip().startswith("```") and lines[j].strip() != "```"
            ):
                j += 1
            if j >= len(lines):
                ranges[rel] = None
                i = j
                continue
            start_line = j + 2
            k = j + 1
            while k < len(lines):
                if lines[k].strip() == "```" and _is_file_block_end(lines, k):
                    break
                k += 1
            end_line = k
            if start_line > end_line:
                ranges[rel] = None
            else:
                ranges[rel] = (start_line, end_line)
            i = k + 1
            continue
        i += 1
    return ranges


def _scan_function_library(lines: list[str]) -> dict[str, tuple[int, int] | None]:
    ranges: dict[str, tuple[int, int] | None] = {}
    in_lib = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "## Function Library":
            in_lib = True
            i += 1
            continue
        if in_lib and line.startswith("## ") and line.strip() != "## Function Library":
            break
        if in_lib and line.startswith("### "):
            defn_id = line.replace("###", "").strip()
            j = i + 1
            while j < len(lines) and lines[j].strip() != "```python":
                j += 1
            if j >= len(lines):
                i += 1
                continue
            start_line = j + 2
            k = j + 1
            while k < len(lines):
                if lines[k].strip() == "```" and _is_function_block_end(lines, k):
                    break
                k += 1
            end_line = k
            if start_line > end_line:
                ranges[defn_id] = None
            else:
                ranges[defn_id] = (start_line, end_line)
            i = k + 1
            continue
        i += 1
    return ranges


def _apply_context_line_numbers(
    text: str,
    def_line_map: dict[str, tuple[int, int]],
    class_line_map: dict[str, tuple[int, int]],
    def_to_canon: dict[str, str],
    def_to_file: dict[str, str],
    class_to_file: dict[str, str],
    use_stubs: bool,
) -> str:
    lines = text.splitlines()
    file_ranges = _scan_file_blocks(lines)
    func_ranges = _scan_function_library(lines) if use_stubs else {}

    replacements: dict[str, str] = {}
    for rel, rng in file_ranges.items():
        token = _range_token("FILE", rel)
        if rng is None:
            replacements[token] = "(empty)"
        else:
            replacements[token] = _format_range(rng[0], rng[1])

    for class_id, loc in class_line_map.items():
        rel_path = class_to_file.get(class_id)
        token = _range_token("CLASS", class_id)
        file_range = file_ranges.get(rel_path) if rel_path else None
        if file_range is None:
            replacements[token] = _format_range(None, None)
            continue
        start = file_range[0] + loc[0] - 1
        end = file_range[0] + loc[1] - 1
        replacements[token] = _format_range(start, end)

    for local_id, loc in def_line_map.items():
        token = _range_token("DEF", local_id)
        if use_stubs:
            canon_id = def_to_canon.get(local_id)
            canon_range = func_ranges.get(canon_id) if canon_id else None
            if canon_range is not None:
                replacements[token] = _format_range(canon_range[0], canon_range[1])
                continue
        rel_path = def_to_file.get(local_id)
        file_range = file_ranges.get(rel_path) if rel_path else None
        if file_range is None:
            replacements[token] = _format_range(None, None)
            continue
        start = file_range[0] + loc[0] - 1
        end = file_range[0] + loc[1] - 1
        replacements[token] = _format_range(start, end)

    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def _has_dedupe_effect(pack: PackResult) -> bool:
    """
    True iff at least one definition has local_id != id (meaning dedupe actually
    collapsed identical bodies and rewrote canonical ids).
    """
    for fp in pack.files:
        for d in fp.defs:
            local_id = getattr(d, "local_id", d.id)
            if local_id != d.id:
                return True
    return False


def _read_full_text(fp: FilePack) -> str:
    """Return the packed file contents."""
    return fp.original_text


def _render_tree(paths: list[str]) -> str:
    root: dict[str, Any] = {}
    for p in paths:
        cur = root
        parts = [x for x in p.split("/") if x]
        for part in parts[:-1]:
            child = cur.setdefault(part, {})
            cur = child if isinstance(child, dict) else {}
        cur.setdefault(parts[-1], None)

    def walk(node: dict[str, Any], prefix: str = "") -> list[str]:
        items = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower()))
        out: list[str] = []
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            branch = "└─ " if last else "├─ "
            out.append(prefix + branch + name)
            if isinstance(child, dict):
                ext = "   " if last else "│  "
                out.extend(walk(child, prefix + ext))
        return out

    return "\n".join(walk(root))


def render_markdown(  # noqa: C901
    pack: PackResult,
    canonical_sources: dict[str, str],
    layout: str = "auto",
    *,
    include_manifest: bool = True,
) -> str:
    lines: list[str] = []
    lines.append("# Codecrate Context Pack\n\n")
    # Do not leak absolute local paths; keep the header root stable + relative.
    lines.append("Root: `.`\n\n")
    layout_norm = (layout or "auto").strip().lower()
    if layout_norm not in {"auto", "stubs", "full"}:
        layout_norm = "auto"
    use_stubs = layout_norm == "stubs" or (
        layout_norm == "auto" and _has_dedupe_effect(pack)
    )
    resolved_layout = "stubs" if use_stubs else "full"
    lines.append(f"Layout: `{resolved_layout}`\n\n")

    def_line_map: dict[str, tuple[int, int]] = {}
    class_line_map: dict[str, tuple[int, int]] = {}
    def_to_canon: dict[str, str] = {}
    def_to_file: dict[str, str] = {}
    class_to_file: dict[str, str] = {}

    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        for d in fp.defs:
            def_line_map[d.local_id] = (d.def_line, d.end_line)
            def_to_canon[d.local_id] = d.id
            def_to_file[d.local_id] = rel
        for c in fp.classes:
            class_to_file[c.id] = rel

    if use_stubs:
        for fp in pack.files:
            by_qualname: dict[str, list[ClassRef]] = defaultdict(list)
            try:
                parsed_classes, _ = parse_symbols(
                    path=fp.path, root=pack.root, text=fp.stubbed_text
                )
            except SyntaxError:
                parsed_classes = []
            for c in parsed_classes:
                by_qualname[c.qualname].append(c)
            for c in sorted(fp.classes, key=lambda x: (x.class_line, x.qualname)):
                matches = by_qualname.get(c.qualname)
                if matches:
                    match = matches.pop(0)
                    class_line_map[c.id] = (match.class_line, match.end_line)
                else:
                    class_line_map[c.id] = (c.class_line, c.end_line)
    else:
        for fp in pack.files:
            for c in fp.classes:
                class_line_map[c.id] = (c.class_line, c.end_line)

    lines.append("## How to Use This Pack\n\n")
    if use_stubs:
        lines.append(
            "This Markdown is a self-contained *context pack* for an LLM. It\n"
            "contains the repository structure, a symbol index, full canonical\n"
            "definitions, and compact file stubs. Use it like this:\n\n"
            "**Suggested read order**\n"
            "1. **Directory Tree**: get a mental map of the project.\n"
            "2. **Symbol Index**: find the file / symbol you care about (with\n"
            "   jump links).\n"
            "3. **Function Library**: read the full implementation of a\n"
            "   function by ID.\n"
            "4. **Files**: read file-level context; function bodies may be\n"
            "   stubbed.\n\n"
            "**Stubs and markers**\n"
            "- In the **Files** section, function bodies may be replaced with\n"
            "  a compact placeholder line like `...  # ↪ FUNC:XXXXXXXX`.\n"
            "- The 8-hex value after `FUNC:` is the function's **local_id**\n"
            "  (unique per occurrence in the repo).\n\n"
            "**IDs (important for dedupe)**\n"
            "- `id` is the **canonical** ID for a function body (deduped when\n"
            "  configured).\n"
            "- `local_id` is unique per definition occurrence. Multiple defs\n"
            "  can share the same `id` but must have different `local_id`.\n\n"
            "**When proposing changes**\n"
            "- Reference changes by **file path** plus **function ID** (and\n"
            "  local_id if shown).\n"
            "- Prefer emitting a unified diff patch (`--- a/...` / `+++ b/...`).\n\n"
            "**Line numbers**\n"
            "- All `Lx-y` ranges refer to line numbers in this markdown file.\n"
            "- File ranges/classes point into **Files**; function ranges point\n"
            "  into **Function Library**.\n\n"
        )
    else:
        lines.append(
            "This Markdown is a self-contained *context pack* for an LLM.\n\n"
            "**Suggested read order**\n"
            "1. **Directory Tree**\n"
            "2. **Symbol Index** (jump to file contents)\n"
            "3. **Files** (full contents)\n\n"
            "**When proposing changes**\n"
            "- Prefer unified diffs (`--- a/...` / `+++ b/...`).\n\n"
            "**Line numbers**\n"
            "- `Lx-y` ranges refer to line numbers in this markdown file (the\n"
            "  code blocks under **Files**).\n\n"
        )

    if include_manifest:
        lines.append("## Manifest\n\n")
        lines.append("```codecrate-manifest\n")
        lines.append(
            json.dumps(
                to_manifest(pack, minimal=not use_stubs), indent=2, sort_keys=False
            )
            + "\n"
        )
        lines.append("```\n\n")

    rel_paths = [f.path.relative_to(pack.root).as_posix() for f in pack.files]
    lines.append("## Directory Tree\n\n")
    lines.append("```text\n")
    lines.append(_render_tree(rel_paths) + "\n")
    lines.append("```\n\n")

    lines.append("## Symbol Index\n\n")

    for fp in sorted(pack.files, key=lambda x: x.path.as_posix()):
        rel = fp.path.relative_to(pack.root).as_posix()
        fa = _file_anchor(rel)
        sa = _file_src_anchor(rel)
        file_range = _range_token("FILE", rel)
        # Always provide a jump target to the file contents.
        lines.append(f"### `{rel}` {file_range} — [jump](#{sa})\n")
        lines.append(f'<a id="{fa}"></a>\n')

        for c in sorted(fp.classes, key=lambda x: (x.class_line, x.qualname)):
            class_loc = _range_token("CLASS", c.id)
            lines.append(f"- `class {c.qualname}` {class_loc}\n")

        for d in sorted(fp.defs, key=lambda d: (d.def_line, d.qualname)):
            loc = _range_token("DEF", d.local_id)
            link = "\n"
            if use_stubs:
                anchor = _anchor_for(d.id, d.module, d.qualname)
                link = f" — [jump](#{anchor})\n"
                id_display = f"**{d.id}**"
                if getattr(d, "local_id", d.id) != d.id:
                    id_display += f" (local **{d.local_id}**)"
                lines.append(f"- `{d.qualname}` → {id_display} {loc}{link}")
            else:
                lines.append(f"- `{d.qualname}` → {loc}\n")
        lines.append("\n")

    if use_stubs:
        lines.append("## Function Library\n\n")
        for defn_id, code in canonical_sources.items():
            lines.append(f'<a id="{_anchor_for(defn_id, "", "")}"></a>\n')
            lines.append(f"### {defn_id}\n")
            lines.append("```python\n")
            lines.append(_ensure_nl(code))
            lines.append("```\n\n")

    lines.append("## Files\n\n")
    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        fa = _file_anchor(rel)
        sa = _file_src_anchor(rel)
        file_range = _range_token("FILE", rel)
        lines.append(f"### `{rel}` {file_range}\n")
        lines.append(f'<a id="{sa}"></a>\n')
        lines.append(f"[jump to index](#{fa})\n\n")

        # Compact stubs are not line-count aligned, so render as a single block.

        lines.append(f"```{_fence_lang_for(rel)}\n")
        if use_stubs:
            lines.append(_ensure_nl(fp.stubbed_text))
        else:
            lines.append(_ensure_nl(_read_full_text(fp)))
        lines.append("```\n\n")
        # Only emit the Symbols block when there are actually symbols.
        if use_stubs and fp.defs:
            lines.append("**Symbols**\n\n")
            if fp.module:
                lines.append(f"_Module_: `{fp.module}`\n\n")
            for d in sorted(fp.defs, key=lambda x: (x.def_line, x.qualname)):
                anchor = _anchor_for(d.id, d.module, d.qualname)
                loc = _range_token("DEF", d.local_id)
                link = f" — [jump](#{anchor})\n"
                id_display = f"**{d.id}**"
                if getattr(d, "local_id", d.id) != d.id:
                    id_display += f" (local **{d.local_id}**)"
                lines.append(f"- `{d.qualname}` → {id_display} {loc}{link}")
            lines.append("\n")
    text = "".join(lines)
    return _apply_context_line_numbers(
        text,
        def_line_map=def_line_map,
        class_line_map=class_line_map,
        def_to_canon=def_to_canon,
        def_to_file=def_to_file,
        class_to_file=class_to_file,
        use_stubs=use_stubs,
    )
