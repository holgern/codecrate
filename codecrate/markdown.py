from __future__ import annotations

from pathlib import Path

from .model import DefRef, PackResult


def _anchor_for(defn: DefRef) -> str:
    base = f"{defn.id}-{defn.module}-{defn.qualname}".lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in base)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def render_markdown(pack: PackResult, canonical_sources: dict[str, str]) -> str:
    lines: list[str] = []
    lines.append("# Codecrate Context Pack\n\n")
    lines.append(f"Root: `{pack.root.as_posix()}`\n\n")
    lines.append("## Index\n\n")

    by_file: dict[Path, list[DefRef]] = {}
    for d in pack.defs:
        by_file.setdefault(d.path, []).append(d)

    for path in sorted(by_file.keys()):
        rel = path.relative_to(pack.root)
        lines.append(f"### `{rel.as_posix()}`\n\n")
        for d in sorted(by_file[path], key=lambda x: (x.def_line, x.qualname)):
            anchor = _anchor_for(d)
            lines.append(
                f"- `{d.module}.{d.qualname}` → **{d.id}** "
                f"(L{d.def_line}–L{d.end_line}) — [jump](#{anchor})\n"
            )
        lines.append("\n")

    lines.append("## Function Library\n\n")
    for cid in sorted(canonical_sources.keys()):
        rep = next((d for d in pack.defs if d.id == cid), None)
        if rep is None:
            continue
        rel = rep.path.relative_to(pack.root)
        anchor = _anchor_for(rep)
        lines.append(
            f"### {cid} — `{rep.module}.{rep.qualname}` "
            f"({rel.as_posix()}:L{rep.def_line}–L{rep.end_line})\n"
        )
        lines.append(f'<a id="{anchor}"></a>\n\n')
        lines.append("```python\n")
        lines.append(canonical_sources[cid].rstrip() + "\n")
        lines.append("```\n\n")

    lines.append("## Files (Stubbed)\n\n")
    for f in pack.files:
        rel = f.path.relative_to(pack.root)
        lines.append(f"### `{rel.as_posix()}`\n\n")
        lines.append("```python\n")
        lines.append(f.stubbed_text.rstrip() + "\n")
        lines.append("```\n\n")

    return "".join(lines)
