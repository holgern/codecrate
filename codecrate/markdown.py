from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from .analysis_metadata import build_repository_guide
from .fences import choose_backtick_fence, is_fence_close, parse_fence_open
from .focus import FocusSelectionResult
from .formats import (
    FENCE_AGENT_WORKFLOW,
    FENCE_MACHINE_HEADER,
    FENCE_MANIFEST,
    PACK_FORMAT_VERSION,
)
from .locators import (
    anchor_for_file_index,
    anchor_for_file_source,
    anchor_for_symbol,
)
from .manifest import machine_header, to_manifest
from .model import ClassRef, FilePack, PackResult
from .ordering import sort_paths
from .output_model import (
    LineRange,
    MarkdownUsageContext,
    RenderedMarkdown,
    RenderMetadata,
)
from .parse import parse_symbols
from .setup_metadata import detect_setup_metadata


def _file_range(line_count: int) -> str:
    return "(empty)" if line_count == 0 else f"(L1-{line_count})"


def _ensure_nl(s: str) -> str:
    return s if (not s or s.endswith("\n")) else (s + "\n")


def _append_fenced_block(lines: list[str], content: str, info: str) -> None:
    fence = choose_backtick_fence(content)
    lines.append(f"{fence}{info}\n")
    lines.append(_ensure_nl(content))
    lines.append(f"{fence}\n\n")


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


_SECTION_TITLES: tuple[str, ...] = (
    "Focus Selection",
    "Directory Tree",
    "Repository Guide",
    "Symbol Index",
    "Function Library",
    "Files",
)


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
            fence = ""
            while j < len(lines):
                opened = parse_fence_open(lines[j])
                if opened is not None:
                    fence = opened[0]
                    break
                j += 1
            if j >= len(lines):
                ranges[rel] = None
                i = j
                continue
            start_line = j + 2
            k = j + 1
            while k < len(lines):
                if is_fence_close(lines[k], fence) and _is_file_block_end(lines, k):
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
            fence = ""
            while j < len(lines):
                opened = parse_fence_open(lines[j])
                if opened is not None and opened[1] == "python":
                    fence = opened[0]
                    break
                j += 1
            if j >= len(lines):
                i += 1
                continue
            start_line = j + 2
            k = j + 1
            while k < len(lines):
                if is_fence_close(lines[k], fence) and _is_function_block_end(lines, k):
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


def _scan_section_ranges(lines: list[str]) -> dict[str, tuple[int, int] | None]:
    headings: list[tuple[str, int]] = []
    fence: str | None = None
    for idx, line in enumerate(lines, start=1):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
        else:
            if is_fence_close(line, fence):
                fence = None
            continue
        if line.startswith("## "):
            headings.append((line[3:].strip(), idx))

    ranges: dict[str, tuple[int, int] | None] = {}
    for i, (title, start_line) in enumerate(headings):
        if title not in _SECTION_TITLES:
            continue
        end_line = headings[i + 1][1] - 1 if i + 1 < len(headings) else len(lines)
        ranges[title] = (start_line, end_line) if start_line <= end_line else None
    return ranges


def _scan_symbol_index_ranges(
    lines: list[str],
    defs_by_file: dict[str, list[str]],
) -> dict[str, tuple[int, int] | None]:
    ranges: dict[str, tuple[int, int] | None] = {}
    in_index = False
    current_file: str | None = None
    current_index = 0
    for idx, line in enumerate(lines, start=1):
        if line.strip() == "## Symbol Index":
            in_index = True
            continue
        if in_index and line.startswith("## ") and line.strip() != "## Symbol Index":
            break
        if not in_index:
            continue
        rel_path = _extract_rel_path(line)
        if rel_path is not None:
            current_file = rel_path
            current_index = 0
            continue
        if (
            current_file is None
            or not line.startswith("- `")
            or line.startswith("- `class ")
        ):
            continue
        defs = defs_by_file.get(current_file, [])
        if current_index >= len(defs):
            continue
        ranges[defs[current_index]] = (idx, idx)
        current_index += 1
    return ranges


def _scan_anchor_ids(lines: list[str]) -> set[str]:
    anchors: set[str] = set()
    for line in lines:
        if line.startswith('<a id="') and line.endswith('"></a>'):
            anchors.add(line[len('<a id="') : -len('"></a>')])
    return anchors


def _to_line_ranges(
    ranges: dict[str, tuple[int, int] | None],
) -> dict[str, LineRange]:
    out: dict[str, LineRange] = {}
    for key, value in ranges.items():
        if value is None:
            continue
        out[key] = LineRange(start_line=value[0], end_line=value[1])
    return out


def _apply_context_line_numbers(
    text: str,
    def_line_map: dict[str, tuple[int, int]],
    class_line_map: dict[str, tuple[int, int]],
    def_to_canon: dict[str, str],
    def_to_file: dict[str, str],
    class_to_file: dict[str, str],
    defs_by_file: dict[str, list[str]],
    use_stubs: bool,
) -> RenderedMarkdown:
    lines = text.splitlines()
    section_ranges = _scan_section_ranges(lines)
    file_ranges = _scan_file_blocks(lines)
    func_ranges = _scan_function_library(lines) if use_stubs else {}
    symbol_index_ranges = _scan_symbol_index_ranges(lines, defs_by_file)
    anchors_present = _scan_anchor_ids(lines)

    replacements: dict[str, str] = {}
    for title in _SECTION_TITLES:
        token = _range_token("SECTION", title)
        rng = section_ranges.get(title)
        if rng is None:
            replacements[token] = _format_range(None, None)
        else:
            replacements[token] = _format_range(rng[0], rng[1])

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
    metadata = RenderMetadata(
        section_ranges=_to_line_ranges(section_ranges),
        file_ranges=_to_line_ranges(file_ranges),
        symbol_index_ranges=_to_line_ranges(symbol_index_ranges),
        canonical_ranges=_to_line_ranges(func_ranges),
        anchors_present=frozenset(anchors_present),
    )
    return RenderedMarkdown(markdown=text, metadata=metadata)


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


def _render_how_to_use_section(
    *,
    use_stubs: bool,
    include_repository_guide: bool,
    include_directory_tree: bool,
    include_symbol_index: bool,
    usage_context: MarkdownUsageContext | None = None,
) -> str:
    lines: list[str] = []
    lines.append("## How to Use This Pack\n\n")
    lines.append(
        "This pack is a read-only repository snapshot for analysis and patch "
        "proposals.\n\n"
    )
    if usage_context and usage_context.standalone_unpacker_filename:
        command = _reconstruct_command(usage_context)
        command_text = " ".join(command)
        lines.append("**Machine reconstruction**\n\n")
        lines.append(
            "This pack includes a generated standalone unpacker. Prefer "
            "reconstructing the repo before analysis:\n\n"
        )
        _append_fenced_block(lines, command_text + "\n", "bash")
        lines.append(
            "If `python3` is not available, try `/usr/bin/python3`, `python3`, "
            "or `python -S`. The standalone unpacker uses only the Python "
            "standard library.\n\n"
        )
        lines.append(
            "After reconstruction, inspect files under `reconstructed/`. Do not "
            "scrape file bodies from this markdown unless the unpacker fails "
            "with a Codecrate error.\n\n"
        )
        lines.append(
            "Fallback: if the generated unpacker fails with a Codecrate error, "
            "use `codecrate unpack PACK.md -o OUT` if Codecrate is installed. "
            "Do not use whole-file regex extraction; any fallback parser must "
            "copy the generated unpacker's line-by-line fence parsing, manifest "
            "and file hash verification, and path traversal rejection.\n\n"
        )

    lines.append("**Quick workflow**\n")
    step = 1
    if include_directory_tree:
        lines.append(
            f"{step}. **Directory Tree** {_range_token('SECTION', 'Directory Tree')}\n"
        )
        step += 1
    if include_repository_guide:
        lines.append(
            f"{step}. **Repository Guide** "
            f"{_range_token('SECTION', 'Repository Guide')}\n"
        )
        step += 1
    if include_symbol_index:
        lines.append(
            f"{step}. **Symbol Index** {_range_token('SECTION', 'Symbol Index')}\n"
        )
        step += 1
    if use_stubs:
        lines.append(
            f"{step}. **Function Library** "
            f"{_range_token('SECTION', 'Function Library')}\n"
        )
        step += 1
        lines.append(f"{step}. **Files** {_range_token('SECTION', 'Files')}\n")
        lines.append(
            f"{step + 1}. For stubbed functions (`...  # ↪ FUNC:v1:XXXXXXXX`), "
            "use **Function "
            "Library** to read full bodies by ID.\n"
        )
    else:
        lines.append(f"{step}. **Files** {_range_token('SECTION', 'Files')}\n")
    lines.append("\n")

    lines.append(
        "**Proposing changes**\n"
        "- Prefer minimal unified diffs (`--- a/...` / `+++ b/...`) with "
        "repo-relative paths.\n\n"
    )

    return "".join(lines)


def _reconstruct_command(usage_context: MarkdownUsageContext) -> list[str]:
    command = [
        "python3",
        "-S",
        usage_context.standalone_unpacker_filename or "context.unpack.py",
        usage_context.markdown_filename,
        "-o",
        "reconstructed",
    ]
    if usage_context.include_machine_header:
        command.append("--check-machine-header")
    command.extend(["--strict", "--fail-on-warning"])
    return command


def _render_agent_workflow_block(
    usage_context: MarkdownUsageContext | None,
) -> str:
    if usage_context is None or usage_context.standalone_unpacker_filename is None:
        return ""
    payload: dict[str, Any] = {
        "schema": "codecrate.agent-workflow.v1",
        "recommended_first_action": "reconstruct",
        "markdown": usage_context.markdown_filename,
        "standalone_unpacker": usage_context.standalone_unpacker_filename,
        "reconstruct_command": _reconstruct_command(usage_context),
        "fallback_interpreters": ["/usr/bin/python3", "python3", "python -S"],
        "inspect_after_reconstruction": True,
        "manual_markdown_scraping": "avoid-unless-unpacker-fails",
    }
    if usage_context.index_json_filename:
        payload["index_json"] = usage_context.index_json_filename
    if usage_context.manifest_json_filename:
        payload["manifest_json"] = usage_context.manifest_json_filename

    lines: list[str] = []
    _append_fenced_block(
        lines,
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        FENCE_AGENT_WORKFLOW,
    )
    return "".join(lines)


def _render_dependency_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items)


def _render_environment_setup_section(root: Path) -> str:
    setup = detect_setup_metadata(root)
    if setup is None:
        return ""

    lines: list[str] = []
    lines.append("## Environment Setup\n\n")
    lines.append(f"- Ecosystem: {setup.ecosystem}\n")
    lines.append(f"- Detected from: `{setup.source_file}`\n")
    lines.append(f"- Prepare command: `{setup.prepare_command}`\n")
    if setup.dev_prepare_command:
        lines.append(f"- Optional dev command: `{setup.dev_prepare_command}`\n")
    if setup.runtime_dependencies:
        lines.append(
            "- Runtime dependencies: "
            f"{_render_dependency_list(setup.runtime_dependencies)}\n"
        )
    if setup.dev_dependencies:
        lines.append(
            f"- Dev dependencies: {_render_dependency_list(setup.dev_dependencies)}\n"
        )
    lines.append(
        "- If dependencies or tools are missing at runtime, run the prepare command "
        "before executing project code or tests.\n\n"
    )
    return "".join(lines)


def _render_repository_guide_section(*, root: Path, pack: PackResult) -> str:
    guide = build_repository_guide(root=root, pack=pack)
    if not any(guide.values()):
        return ""

    label_map = {
        "entrypoints": "Entrypoints",
        "main_workflows": "Main workflows",
        "key_config_files": "Key config files",
        "central_modules": "Central modules",
        "test_clusters": "Primary test clusters",
    }
    lines = ["## Repository Guide\n\n"]
    for key in (
        "entrypoints",
        "main_workflows",
        "key_config_files",
        "central_modules",
        "test_clusters",
    ):
        values = guide.get(key, [])
        if not values:
            continue
        lines.append(f"- {label_map[key]}: {_render_dependency_list(values)}\n")
    lines.append("\n")
    return "".join(lines)


def _render_focus_selection_section(
    focus_selection: FocusSelectionResult | None,
) -> str:
    if focus_selection is None or not focus_selection.inclusion_reasons:
        return ""
    lines = ["## Focus Selection\n\n"]
    lines.append(f"- Selected files: {len(focus_selection.selected_paths)}\n")
    reasons = sorted(
        {
            reason
            for item in focus_selection.inclusion_reasons.values()
            for reason in item.selected_by
        }
    )
    if reasons:
        lines.append(
            "- Inclusion reasons: " + ", ".join(f"`{item}`" for item in reasons) + "\n"
        )
    preview = list(focus_selection.selected_paths[:8])
    if preview:
        lines.append("- Preview: " + ", ".join(f"`{item}`" for item in preview) + "\n")
    lines.append("\n")
    return "".join(lines)


def render_markdown_result(  # noqa: C901
    pack: PackResult,
    canonical_sources: dict[str, str],
    layout: str = "auto",
    nav_mode: Literal["compact", "full"] = "full",
    skipped_for_safety_count: int = 0,
    skipped_for_binary_count: int = 0,
    redacted_for_safety_count: int = 0,
    *,
    include_safety_report: bool = False,
    safety_report_entries: list[dict[str, str]] | None = None,
    include_manifest: bool = True,
    include_repository_guide: bool = True,
    include_symbol_index: bool = True,
    include_directory_tree: bool = True,
    include_environment_setup: bool = True,
    include_how_to_use: bool = True,
    manifest_data: dict[str, Any] | None = None,
    repo_label: str = "repo",
    repo_slug: str = "repo",
    focus_selection: FocusSelectionResult | None = None,
    usage_context: MarkdownUsageContext | None = None,
) -> RenderedMarkdown:
    lines: list[str] = []
    lines.append("# Codecrate Context Pack\n\n")
    # Do not leak absolute local paths; keep the header root stable + relative.
    lines.append("Root: `.`\n\n")
    lines.append(f"Format: `{PACK_FORMAT_VERSION}`\n\n")
    layout_norm = (layout or "auto").strip().lower()
    if layout_norm not in {"auto", "stubs", "full"}:
        layout_norm = "auto"
    nav_mode_norm = nav_mode.strip().lower()
    if nav_mode_norm not in {"compact", "full"}:
        nav_mode_norm = "full"
    compact_nav = nav_mode_norm == "compact"
    use_stubs = layout_norm == "stubs" or (
        layout_norm == "auto" and _has_dedupe_effect(pack)
    )
    resolved_layout = "stubs" if use_stubs else "full"
    lines.append(f"Layout: `{resolved_layout}`\n\n")
    if skipped_for_safety_count > 0:
        lines.append(f"Skipped for safety: {skipped_for_safety_count} file(s)\n\n")
    if skipped_for_binary_count > 0:
        lines.append(f"Skipped as binary: {skipped_for_binary_count} file(s)\n\n")
    if redacted_for_safety_count > 0:
        lines.append(f"Redacted for safety: {redacted_for_safety_count} file(s)\n\n")

    if include_safety_report:
        lines.append("## Safety Report\n\n")
        entries = safety_report_entries or []
        if not entries:
            lines.append("_No safety findings._\n\n")
        else:
            skipped_entries = [e for e in entries if e.get("action") == "skipped"]
            redacted_entries = [e for e in entries if e.get("action") == "redacted"]
            lines.append(f"- Skipped: {len(skipped_entries)}\n")
            lines.append(f"- Redacted: {len(redacted_entries)}\n\n")
            for item in entries:
                path = item.get("path", "")
                action = item.get("action", "")
                reason = item.get("reason", "")
                lines.append(f"- `{path}` - **{action}** ({reason})\n")
            lines.append("\n")

    def_line_map: dict[str, tuple[int, int]] = {}
    class_line_map: dict[str, tuple[int, int]] = {}
    def_to_canon: dict[str, str] = {}
    def_to_file: dict[str, str] = {}
    class_to_file: dict[str, str] = {}
    defs_by_file: dict[str, list[str]] = {}

    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        defs_by_file[rel] = [
            d.local_id for d in sorted(fp.defs, key=lambda d: (d.def_line, d.qualname))
        ]
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
                parsed_classes = parse_symbols(
                    path=fp.path, root=pack.root, text=fp.stubbed_text
                ).classes
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

    guide_section = (
        _render_repository_guide_section(root=pack.root, pack=pack)
        if include_repository_guide
        else ""
    )
    if include_how_to_use:
        lines.append(
            _render_how_to_use_section(
                use_stubs=use_stubs,
                include_repository_guide=bool(guide_section),
                include_directory_tree=include_directory_tree,
                include_symbol_index=include_symbol_index,
                usage_context=usage_context,
            )
        )
    lines.append(_render_agent_workflow_block(usage_context))
    if include_environment_setup:
        lines.append(_render_environment_setup_section(pack.root))
    lines.append(guide_section)
    lines.append(_render_focus_selection_section(focus_selection))

    if include_manifest:
        manifest_obj = manifest_data or to_manifest(pack, minimal=not use_stubs)
        header_obj = machine_header(
            manifest=manifest_obj,
            repo_label=repo_label,
            repo_slug=repo_slug,
        )
        lines.append("## Machine Header\n\n")
        _append_fenced_block(
            lines,
            json.dumps(header_obj, sort_keys=True, separators=(",", ":")) + "\n",
            FENCE_MACHINE_HEADER,
        )

        lines.append("## Manifest\n\n")
        _append_fenced_block(
            lines,
            json.dumps(manifest_obj, indent=2, sort_keys=False) + "\n",
            FENCE_MANIFEST,
        )

    rel_paths = [
        path.relative_to(pack.root).as_posix()
        for path in sort_paths([f.path for f in pack.files])
    ]
    if include_directory_tree:
        lines.append("## Directory Tree\n\n")
        _append_fenced_block(lines, _render_tree(rel_paths) + "\n", "text")

    if include_symbol_index:
        lines.append("## Symbol Index\n\n")

        for fp in sorted(pack.files, key=lambda x: x.path.as_posix()):
            rel = fp.path.relative_to(pack.root).as_posix()
            file_range = _range_token("FILE", rel)
            fa = anchor_for_file_index(rel)
            sa = anchor_for_file_source(rel)
            if compact_nav:
                lines.append(f"### `{rel}` {file_range}\n")
                lines.append(f'<a id="{fa}"></a>\n')
            else:
                # Always provide a jump target to the file contents.
                lines.append(f"### `{rel}` {file_range} — [jump](#{sa})\n")
                lines.append(f'<a id="{fa}"></a>\n')

            for c in sorted(fp.classes, key=lambda x: (x.class_line, x.qualname)):
                class_loc = _range_token("CLASS", c.id)
                lines.append(f"- `class {c.qualname}` {class_loc}\n")

            for d in sorted(fp.defs, key=lambda d: (d.def_line, d.qualname)):
                loc = _range_token("DEF", d.local_id)
                has_canonical = d.id in canonical_sources
                link = "\n"
                if use_stubs and has_canonical:
                    anchor = anchor_for_symbol(d.id)
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
            lines.append(f'<a id="{anchor_for_symbol(defn_id)}"></a>\n')
            lines.append(f"### {defn_id}\n")
            _append_fenced_block(lines, _ensure_nl(code), "python")

    lines.append("## Files\n\n")
    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        file_range = _range_token("FILE", rel)
        lines.append(f"### `{rel}` {file_range}\n")
        sa = anchor_for_file_source(rel)
        lines.append(f'<a id="{sa}"></a>\n')
        if compact_nav:
            lines.append("\n")
        else:
            fa = anchor_for_file_index(rel)
            lines.append(f"[jump to index](#{fa})\n\n")

        # Compact stubs are not line-count aligned, so render as a single block.

        if use_stubs:
            file_content = _ensure_nl(fp.stubbed_text)
        else:
            file_content = _ensure_nl(_read_full_text(fp))
        _append_fenced_block(lines, file_content, _fence_lang_for(rel))
        # Only emit the Symbols block when there are actually symbols.
        if use_stubs and fp.defs:
            lines.append("**Symbols**\n\n")
            if fp.module:
                lines.append(f"_Module_: `{fp.module}`\n\n")
            for d in sorted(fp.defs, key=lambda x: (x.def_line, x.qualname)):
                loc = _range_token("DEF", d.local_id)
                has_canonical = d.id in canonical_sources
                if has_canonical:
                    anchor = anchor_for_symbol(d.id)
                    link = f" — [jump](#{anchor})\n"
                    id_display = f"**{d.id}**"
                    if getattr(d, "local_id", d.id) != d.id:
                        id_display += f" (local **{d.local_id}**)"
                    lines.append(f"- `{d.qualname}` → {id_display} {loc}{link}")
                else:
                    lines.append(f"- `{d.qualname}` → {loc}\n")
            lines.append("\n")
    text = "".join(lines)
    return _apply_context_line_numbers(
        text,
        def_line_map=def_line_map,
        class_line_map=class_line_map,
        def_to_canon=def_to_canon,
        def_to_file=def_to_file,
        class_to_file=class_to_file,
        defs_by_file=defs_by_file,
        use_stubs=use_stubs,
    )


def render_markdown(  # noqa: C901
    pack: PackResult,
    canonical_sources: dict[str, str],
    layout: str = "auto",
    nav_mode: Literal["compact", "full"] = "full",
    skipped_for_safety_count: int = 0,
    skipped_for_binary_count: int = 0,
    redacted_for_safety_count: int = 0,
    *,
    include_safety_report: bool = False,
    safety_report_entries: list[dict[str, str]] | None = None,
    include_manifest: bool = True,
    include_repository_guide: bool = True,
    include_symbol_index: bool = True,
    include_directory_tree: bool = True,
    include_environment_setup: bool = True,
    include_how_to_use: bool = True,
    manifest_data: dict[str, Any] | None = None,
    repo_label: str = "repo",
    repo_slug: str = "repo",
    usage_context: MarkdownUsageContext | None = None,
) -> str:
    return render_markdown_result(
        pack,
        canonical_sources,
        layout=layout,
        nav_mode=nav_mode,
        skipped_for_safety_count=skipped_for_safety_count,
        skipped_for_binary_count=skipped_for_binary_count,
        redacted_for_safety_count=redacted_for_safety_count,
        include_safety_report=include_safety_report,
        safety_report_entries=safety_report_entries,
        include_manifest=include_manifest,
        include_repository_guide=include_repository_guide,
        include_symbol_index=include_symbol_index,
        include_directory_tree=include_directory_tree,
        include_environment_setup=include_environment_setup,
        include_how_to_use=include_how_to_use,
        manifest_data=manifest_data,
        repo_label=repo_label,
        repo_slug=repo_slug,
        usage_context=usage_context,
    ).markdown
