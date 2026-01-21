from __future__ import annotations

import json

from .manifest import to_manifest
from .model import PackResult


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


def _file_range(line_count: int) -> str:
    return "(empty)" if line_count == 0 else f"(L1–L{line_count})"


def _ensure_nl(s: str) -> str:
    return s if (not s or s.endswith("\n")) else (s + "\n")

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


def _read_full_text(fp) -> str:
    """
    Read file contents from disk for 'full' layout.
    """
    try:
        return fp.path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def _render_tree(paths: list[str]) -> str:
    root: dict[str, object] = {}
    for p in paths:
        cur = root
        parts = [x for x in p.split("/") if x]
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})  # type: ignore[assignment]
        cur.setdefault(parts[-1], None)

    def walk(node: dict[str, object], prefix: str = "") -> list[str]:
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


def render_markdown(
    pack: PackResult, canonical_sources: dict[str, str], layout: str = "auto"
) -> str:
    lines: list[str] = []
    lines.append("# Codecrate Context Pack\n\n")
    lines.append(f"Root: `{pack.root.as_posix()}`\n\n")
    layout_norm = (layout or "auto").strip().lower()
    if layout_norm not in {"auto", "stubs", "full"}:
        layout_norm = "auto"
    use_stubs = layout_norm == "stubs" or (
        layout_norm == "auto" and _has_dedupe_effect(pack)
    )
    resolved_layout = "stubs" if use_stubs else "full"
    lines.append(f"Layout: `{resolved_layout}`\n\n")

    lines.append("## How to Use This Pack\n\n")
    lines.append(
        "This Markdown is a self-contained *context pack* for an LLM. It contains the\n"
        "repository structure, a symbol index, full canonical definitions, and\n"
        "compact file stubs. Use it like this:\n\n"
        "**Suggested read order**\n"
        "1. **Directory Tree**: get a mental map of the project.\n"
        "2. **Symbol Index**: find the file / symbol you care about (with jump\n"
        "   links).\n"
        "3. **Function Library**: read the full implementation of a function by ID.\n"
        "4. **Files**: read file-level context; function bodies may be stubbed.\n\n"
        "**Stubs and markers**\n"
        "- In the **Files** section, function bodies may be replaced with a compact\n"
        "  placeholder line like `...  # ↪ FUNC:XXXXXXXX`.\n"
        "- The 8-hex value after `FUNC:` is the function’s **local_id** (unique per\n"
        "  occurrence in the repo).\n\n"
        "**IDs (important for dedupe)**\n"
        "- `id` is the **canonical** ID for a function body (deduped when\n"
        "  configured).\n"
        "- `local_id` is unique per definition occurrence. Multiple defs can\n"
        "  share the same `id` but must have different `local_id`.\n\n"
        "**Layout behavior**\n"
        "- If `Layout: full`, the **Files** section contains complete file contents.\n"
        "- If `Layout: stubs`, use **Function Library** + `FUNC:<local_id>` markers.\n\n"
        "**How to mentally reconstruct a file**\n"
        "- For each `FUNC:<local_id>` marker in a file stub, use the per-file\n"
        "  mapping table (local_id → canonical id link) shown under that file in\n"
        "  **Files** (only present when `local_id != id`, i.e. when dedupe\n"
        "  actually changed IDs) to jump to the full implementation in the\n"
        "  Function Library.\n\n"
        "**When proposing changes**\n"
        "- Reference changes by **file path** plus **function ID** (and local_id if\n"
        "  shown).\n"
        "- Prefer emitting a unified diff patch (`--- a/...` / `+++ b/...`).\n\n"
        "**Unpack algorithm**\n"
        "1. Parse **Manifest** JSON.\n"
        "2. For each file: map `L[path][local_id]=id`.\n"
        "3. Parse **Function Library**: map `C[id]=full snippet`.\n"
        "4. For each file stub in **Files**:\n"
        "- find markers `...  # ↪ FUNC:<local_id>`\n"
        "- let `id=L[path][local_id]`\n"
        "- let `body = C[id]` with everything up to and including the signature\n"
        "  removed (also drop decorators)\n"
        "- replace the marker line with `body` (indent already matches; methods\n"
        "  stay indented)\n"
        "5. Validate: reconstructed file sha256 == `sha256_original`.\n\n"
    )

    manifest = to_manifest(pack)
    lines.append("## Manifest\n\n")
    lines.append("```codecrate-manifest\n")
    lines.append(json.dumps(manifest, indent=2) + "\n")
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
        lines.append(f"### `{rel}` {_file_range(fp.line_count)}\n")
        lines.append(f'<a id="{fa}"></a>\n\n')

        for c in sorted(fp.classes, key=lambda c: (c.class_line, c.qualname)):
            depth = c.qualname.count(".")
            indent = "  " * depth
            class_name = c.qualname.split(".")[-1]
            lines.append(
                f"- {indent}`class {class_name}` (L{c.class_line}–L{c.end_line})\n"
            )

        for d in sorted(fp.defs, key=lambda d: (d.def_line, d.qualname)):
            anchor = _anchor_for(d.id, d.module, d.qualname)
            depth = d.qualname.count(".")
            indent = "  " * depth
            label = d.qualname.split(".")[-1]
            loc = f"L{d.def_line}–L{d.end_line}"
            jump_link = f" — [jump](#{anchor})\n"
            id_display = f"**{d.id}**"
            if getattr(d, "local_id", d.id) != d.id:
                id_display += f" (local **{d.local_id}**)"
            lines.append(f"- {indent}`{label}` → {id_display} ({loc}){jump_link}")
        lines.append("\n")

    if use_stubs:
        lines.append("## Function Library\n\n")
        for cid in sorted(canonical_sources.keys()):
            rep = next((d for d in pack.defs if d.id == cid), None)
            if rep is None:
                continue
            rel = rep.path.relative_to(pack.root).as_posix()
            anchor = _anchor_for(rep.id, rep.module, rep.qualname)
            loc = f"L{rep.def_line}–L{rep.end_line}"
            header = f"{cid} — `{rep.module}.{rep.qualname}` ({rel}:{loc})"
            lines.append(f"### {header}\n")
            lines.append(f'<a id="{anchor}"></a>\n\n')
            lines.append("```python\n")
            lines.append(canonical_sources[cid].rstrip() + "\n")
            lines.append("```\n\n")
 

    lines.append("## Files\n\n")
    for fp in sorted(pack.files, key=lambda x: x.path.as_posix()):
        rel = fp.path.relative_to(pack.root).as_posix()
        fa = _file_anchor(rel)
        lines.append(f"### `{rel}` {_file_range(fp.line_count)}\n")
        lines.append(f"[jump to index](#{fa})\n\n")

        if use_stubs:
            # local_id → canonical id mapping (only when dedupe actually changed IDs)
            mapping = []
            for d in sorted(fp.defs, key=lambda x: (x.def_line, x.qualname)):
                local_id = getattr(d, "local_id", d.id)
                if local_id != d.id:
                    anchor = _anchor_for(d.id, d.module, d.qualname)
                    mapping.append((local_id, d.id, anchor))
            if mapping:
                lines.append("| local_id | canonical |\n")
                lines.append("|---|---|\n")
                for local_id, cid, anchor in mapping:
                    lines.append(f"| `{local_id}` | [`{cid}`](#{anchor}) |\n")
                lines.append("\n")

        # Compact stubs are not line-count aligned, so render as a single block.

        lines.append("```python\n")
        if use_stubs:
            lines.append(_ensure_nl(fp.stubbed_text))
        else:
            lines.append(_ensure_nl(_read_full_text(fp)))
        lines.append("```\n\n")

        lines.append("**Symbols**\n\n")
        lines.append(f"_Module_: `{fp.module}`\n\n")
        for d in sorted(fp.defs, key=lambda x: (x.def_line, x.qualname)):
            anchor = _anchor_for(d.id, d.module, d.qualname)
            loc = f"L{d.def_line}–L{d.end_line}"
            link = f" — [jump](#{anchor})\n"
            id_display = f"**{d.id}**"
            if getattr(d, "local_id", d.id) != d.id:
                id_display += f" (local **{d.local_id}**)"
            # In full layout, anchors must exist somewhere (no Function Library),
            # so define them here (outside code fences) to keep jump links working.
            if not use_stubs:
                lines.append(f'<a id="{anchor}"></a>\n')
            lines.append(f"- `{d.qualname}` → {id_display} ({loc}){link}")
        lines.append("\n")

    return "".join(lines)
