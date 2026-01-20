from __future__ import annotations

import json

from .manifest import to_manifest
from .model import FilePack, PackResult


def _anchor_for(defn_id: str, module: str, qualname: str) -> str:
    base = f"{defn_id}-{module}-{qualname}".lower()
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


def _split_preamble_outline(
    fp: FilePack,
) -> tuple[tuple[int, int, str], tuple[int, int, str]]:
    lines = fp.stubbed_text.splitlines(keepends=True)

    first = None
    for c in fp.classes:
        first = c.decorator_start if first is None else min(first, c.decorator_start)
    for d in fp.defs:
        if "." not in d.qualname:
            first = (
                d.decorator_start if first is None else min(first, d.decorator_start)
            )

    if first is None:
        pre = fp.stubbed_text
        return (1, fp.line_count, pre.rstrip()), (fp.line_count + 1, fp.line_count, "")

    pre_lines = lines[: max(0, first - 1)]
    out_lines = lines[max(0, first - 1) :]

    pre_text = "".join(pre_lines).rstrip()
    out_text = "".join(out_lines).rstrip()

    pre_start, pre_end = 1, max(0, first - 1)
    out_start, out_end = first, fp.line_count
    return (pre_start, pre_end, pre_text), (out_start, out_end, out_text)


def render_markdown(pack: PackResult, canonical_sources: dict[str, str]) -> str:
    lines: list[str] = []
    lines.append("# Codecrate Context Pack\n\n")
    lines.append(f"Root: `{pack.root.as_posix()}`\n\n")

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
        lines.append(f"### `{rel}` (L1–L{fp.line_count})\n")
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
            lines.append(f"- {indent}`{label}` → **{d.id}** ({loc}){jump_link}")
        lines.append("\n")

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
        lines.append(f"### `{rel}` (L1–L{fp.line_count})\n")
        lines.append(f"[jump to index](#{fa})\n\n")

        (ps, pe, pre), (os, oe, outline) = _split_preamble_outline(fp)

        if pre.strip():
            lines.append(f"**Preamble (L{ps}–L{pe})**\n\n")
            lines.append("```python\n")
            lines.append(pre.rstrip() + "\n")
            lines.append("```\n\n")

        if outline.strip():
            lines.append(f"**Outline (L{os}–L{oe})**\n\n")
            lines.append("```python\n")
            lines.append(outline.rstrip() + "\n")
            lines.append("```\n\n")

        lines.append("**Symbols**\n\n")
        for d in sorted(fp.defs, key=lambda x: (x.def_line, x.qualname)):
            anchor = _anchor_for(d.id, d.module, d.qualname)
            loc = f"L{d.def_line}–L{d.end_line}"
            link = f" — [jump](#{anchor})\n"
            lines.append(f"- `{d.module}.{d.qualname}` → **{d.id}** ({loc}){link}")
        lines.append("\n")

    return "".join(lines)
