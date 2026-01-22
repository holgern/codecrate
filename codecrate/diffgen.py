from __future__ import annotations

import difflib
from pathlib import Path

from .config import DEFAULT_INCLUDES
from .discover import discover_files
from .mdparse import parse_packed_markdown
from .udiff import normalize_newlines
from .unpacker import _apply_canonical_into_stub


def generate_patch_markdown(
    old_pack_md: str,
    root: Path,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    respect_gitignore: bool = True,
) -> str:
    # If caller doesn't pass include/exclude, use the same defaults as Config.
    include = DEFAULT_INCLUDES.copy() if include is None else list(include)
    exclude = [] if exclude is None else list(exclude)

    packed = parse_packed_markdown(old_pack_md)
    manifest = packed.manifest
    root = root.resolve()

    blocks: list[str] = []
    blocks.append("# Codecrate Patch\n\n")
    # Do not leak absolute local paths; keep the header root stable + relative.
    blocks.append("Root: `.`\n\n")
    blocks.append("This file contains unified diffs inside ```diff code fences.\n\n")

    any_changes = False

    old_paths = {f["path"] for f in manifest.get("files", []) if "path" in f}
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
                tofile="/dev/null",
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

    # Added files (present in current repo, not in baseline manifest)
    disc = discover_files(
        root,
        include=include,
        exclude=exclude,
        respect_gitignore=respect_gitignore,
    )
    for p in disc.files:
        rel = p.relative_to(root).as_posix()
        if rel in old_paths:
            continue

        new_text = normalize_newlines(p.read_text(encoding="utf-8", errors="replace"))
        diff = difflib.unified_diff(
            [],
            new_text.splitlines(),
            fromfile="/dev/null",
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
