from __future__ import annotations

import difflib
import json
from pathlib import Path

from .config import DEFAULT_INCLUDES
from .discover import discover_files
from .formats import FENCE_PATCH_META, PATCH_FORMAT_VERSION
from .manifest import manifest_sha256
from .mdparse import parse_packed_markdown
from .udiff import normalize_newlines
from .unpacker import _apply_canonical_into_stub


def _to_lf_keepends(text: str) -> list[str]:
    return normalize_newlines(text).splitlines(keepends=True)


def _render_unified_diff(diff: list[str]) -> list[str]:
    out: list[str] = []
    for line in diff:
        has_newline = line.endswith("\n")
        out.append(line[:-1] if has_newline else line)
        is_hunk_body_line = (
            bool(line)
            and line[0] in {" ", "+", "-"}
            and not line.startswith(("---", "+++", "@@"))
        )
        if is_hunk_body_line and not has_newline:
            out.append(r"\ No newline at end of file")
    return out


def generate_patch_markdown(
    old_pack_md: str,
    root: Path,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    respect_gitignore: bool = True,
    encoding_errors: str = "replace",
) -> str:
    # If caller doesn't pass include/exclude, use the same defaults as Config.
    include = DEFAULT_INCLUDES.copy() if include is None else list(include)
    exclude = [] if exclude is None else list(exclude)

    packed = parse_packed_markdown(old_pack_md)
    manifest = packed.manifest
    root = root.resolve()
    baseline_files_sha256 = {
        str(f.get("path")): str(f.get("sha256_original"))
        for f in manifest.get("files", [])
        if f.get("path") and f.get("sha256_original")
    }

    blocks: list[str] = []
    blocks.append("# Codecrate Patch\n\n")
    # Do not leak absolute local paths; keep the header root stable + relative.
    blocks.append("Root: `.`\n\n")
    blocks.append(f"```{FENCE_PATCH_META}\n")
    blocks.append(
        json.dumps(
            {
                "format": PATCH_FORMAT_VERSION,
                "baseline_manifest_sha256": manifest_sha256(manifest),
                "baseline_files_sha256": baseline_files_sha256,
            },
            sort_keys=True,
        )
        + "\n"
    )
    blocks.append("```\n\n")
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
        old_lines = _to_lf_keepends(old_text)

        cur_path = root / rel
        if not cur_path.exists():
            # treat as deleted in current
            diff = difflib.unified_diff(
                old_lines,
                [],
                fromfile=f"a/{rel}",
                tofile="/dev/null",
                lineterm="",
            )
        else:
            try:
                text = cur_path.read_text(encoding="utf-8", errors=encoding_errors)
            except UnicodeDecodeError as e:
                raise ValueError(
                    f"Failed to decode UTF-8 for {rel} "
                    f"(encoding_errors={encoding_errors})"
                ) from e
            new_lines = _to_lf_keepends(text)
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                lineterm="",
            )

        diff_lines = _render_unified_diff(list(diff))
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

        try:
            text = p.read_text(encoding="utf-8", errors=encoding_errors)
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Failed to decode UTF-8 for {rel} (encoding_errors={encoding_errors})"
            ) from e
        new_lines = _to_lf_keepends(text)
        diff = difflib.unified_diff(
            [],
            new_lines,
            fromfile="/dev/null",
            tofile=f"b/{rel}",
            lineterm="",
        )
        diff_lines = _render_unified_diff(list(diff))
        if diff_lines:
            any_changes = True
            blocks.append(f"## `{rel}`\n\n")
            blocks.append("```diff\n")
            blocks.append("\n".join(diff_lines) + "\n")
            blocks.append("```\n\n")

    if not any_changes:
        blocks.append("_No changes detected._\n")

    return "".join(blocks)
