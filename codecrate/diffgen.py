from __future__ import annotations

import difflib
from pathlib import Path

from .mdparse import parse_packed_markdown
from .udiff import normalize_newlines
from .unpacker import _apply_canonical_into_stub


def generate_patch_markdown(old_pack_md: str, root: Path) -> str:
    packed = parse_packed_markdown(old_pack_md)
    manifest = packed.manifest
    root = root.resolve()

    blocks: list[str] = []
    blocks.append("# Codecrate Patch\n\n")
    blocks.append(f"Root: `{root.as_posix()}`\n\n")
    blocks.append("This file contains unified diffs inside ```diff code fences.\n\n")

    any_changes = False

    for f in manifest.get("files", []):
        rel = f["path"]
        stub = packed.stubbed_files.get(rel)
        if stub is None:
            continue

        old_text = _apply_canonical_into_stub(
            stub, f.get("defs", []), packed.canonical_sources
        )
        old_text = normalize_newlines(old_text)

        cur_path = root / rel
        if not cur_path.exists():
            # treat as deleted in current
            diff = difflib.unified_diff(
                old_text.splitlines(),
                [],
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                lineterm="",
            )
        else:
            new_text = normalize_newlines(
                cur_path.read_text(encoding="utf-8", errors="replace")
            )
            diff = difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                lineterm="",
            )

        diff_lines = list(diff)
        if diff_lines:
            any_changes = True
            blocks.append(f"## `{rel}`\n\n")
            blocks.append("```diff\n")
            blocks.append("\n".join(diff_lines) + "\n")
            blocks.append("```\n\n")

    if not any_changes:
        blocks.append("_No changes detected._\n")

    return "".join(blocks)
