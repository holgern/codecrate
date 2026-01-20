from __future__ import annotations

import warnings
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

        try:
            i0 = max(0, int(d["decorator_start"]) - 1)
            i1 = min(len(lines), int(d["end_line"]))  # inclusive -> exclusive
        except Exception:
            continue
        if i0 > len(lines) or i1 > len(lines) or i0 >= i1:
            # Stub layout doesn't match manifest line coordinates.
            # Leave the stub region as-is rather than corrupting the file.
            continue

        repl = canonical[cid].splitlines(keepends=True)
        if repl and not repl[-1].endswith("\n"):
            repl[-1] = repl[-1] + "\n"
        lines[i0:i1] = repl

    return "".join(lines)


def unpack_to_dir(markdown_text: str, out_dir: Path) -> None:
    packed = parse_packed_markdown(markdown_text)
    manifest = packed.manifest
    if manifest.get("format") not in {"codecrate.v3", "codecrate.v2", "codecrate.v1"}:
        raise ValueError(f"Unsupported format: {manifest.get('format')}")

    out_dir = out_dir.resolve()
    missing: list[str] = []
    for f in manifest.get("files", []):
        rel = f["path"]
        stub = packed.stubbed_files.get(rel)
        exp = f.get("line_count")
        exp_n = int(exp) if exp is not None else None
        if stub is None or (exp_n and exp_n > 0 and not stub.strip()):
            missing.append(rel)
            continue

        # Optional integrity check: stub line count should match manifest line count.
        exp = f.get("line_count")
        if exp is not None:
            try:
                exp_n = int(exp)
                got_n = len(stub.splitlines()) if stub else 0
                if exp_n != got_n:
                    msg = (
                        f"Stub line count mismatch for {rel}: "
                        f"manifest={exp_n}, stub={got_n}"
                    )
                    warnings.warn(msg, RuntimeWarning, stacklevel=2)
            except Exception:
                pass

        defs = f.get("defs", [])
        reconstructed = _apply_canonical_into_stub(stub, defs, packed.canonical_sources)

        # Prevent path traversal / writing outside out_dir
        target = (out_dir / rel).resolve()
        if out_dir != target and out_dir not in target.parents:
            raise ValueError(f"Refusing to write outside out_dir: {rel}")
        ensure_parent_dir(target)
        target.write_text(reconstructed, encoding="utf-8")

    if missing:
        files_str = ", ".join(missing[:10])
        if len(missing) > 10:
            files_str += "..."
        msg = f"Missing stubbed file blocks for {len(missing)} file(s): {files_str}"
        warnings.warn(msg, RuntimeWarning, stacklevel=2)
