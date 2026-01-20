from __future__ import annotations

from pathlib import Path

from .mdparse import parse_packed_markdown
from .udiff import ensure_parent_dir


def _apply_canonical_into_stub(
    stub: str, defs: list[dict], canonical: dict[str, str]
) -> str:
    """
    Reconstruct original by replacing decorator_start..end_line with canonical code.
    Works even if stubbed file contains placeholders; we replace whole def region.
    """
    lines = stub.splitlines(keepends=True)

    # apply bottom-up so indexes remain stable
    defs_sorted = sorted(defs, key=lambda d: int(d["decorator_start"]), reverse=True)
    for d in defs_sorted:
        cid = d.get("id")  # canonical id after dedupe
        if not cid or cid not in canonical:
            # fallback: try local_id (older packs)
            cid = d.get("local_id")
        if not cid or cid not in canonical:
            continue

        i0 = max(0, int(d["decorator_start"]) - 1)
        i1 = min(len(lines), int(d["end_line"]))  # inclusive -> exclusive
        repl = canonical[cid].splitlines(keepends=True)
        lines[i0:i1] = repl

    return "".join(lines)


def unpack_to_dir(markdown_text: str, out_dir: Path) -> None:
    packed = parse_packed_markdown(markdown_text)
    manifest = packed.manifest
    if manifest.get("format") not in {"codecrate.v3", "codecrate.v2", "codecrate.v1"}:
        raise ValueError(f"Unsupported format: {manifest.get('format')}")

    out_dir = out_dir.resolve()
    for f in manifest.get("files", []):
        rel = f["path"]
        stub = packed.stubbed_files.get(rel)
        if stub is None:
            # no stubbed file block; cannot reconstruct safely
            continue
        defs = f.get("defs", [])
        reconstructed = _apply_canonical_into_stub(stub, defs, packed.canonical_sources)

        target = out_dir / rel
        ensure_parent_dir(target)
        target.write_text(reconstructed, encoding="utf-8")
