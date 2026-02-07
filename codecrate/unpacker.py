from __future__ import annotations

import hashlib
import re
import warnings
from pathlib import Path

from .formats import PACK_FORMAT_VERSION
from .ids import MARKER_NAMESPACE
from .mdparse import parse_packed_markdown
from .repositories import split_repository_sections
from .udiff import ensure_parent_dir, normalize_newlines

_MARK_RE = re.compile(
    rf"{MARKER_NAMESPACE}:(?:v\d+:)?(?P<id>[0-9A-Fa-f]{{8}})",
)


def _ws_len(s: str) -> int:
    return len(s) - len(s.lstrip(" \t"))


def _apply_canonical_into_stub(
    stub: str,
    defs: list[dict],
    canonical: dict[str, str],
    *,
    strict: bool = False,
    issues: list[str] | None = None,
) -> str:
    """
    Reconstruct original by locating FUNC:<id> markers in the stub and replacing the
    surrounding def region (decorators + def + stubbed body/docstring) with the
    canonical code. Does not rely on line-number alignment.

    Marker semantics:
    - New packs use local_id in stub markers (unique per occurrence).
    - Canonical code is still fetched by id (deduped across identical bodies).
    - For backwards compatibility, we also accept markers keyed by id.
    """
    lines = stub.splitlines(keepends=True)

    # Allow multiple occurrences of the same marker id (older dedupe packs).
    marker_lines_for: dict[str, list[int]] = {}

    def _record_issue(message: str) -> None:
        if issues is not None:
            issues.append(message)
        if strict:
            raise ValueError(message)

    for i, ln in enumerate(lines):
        m = _MARK_RE.search(ln)
        if m:
            marker_lines_for.setdefault(m.group("id").upper(), []).append(i)

    # Apply bottom-up so indices remain stable.
    work: list[tuple[int, dict, str]] = []
    for d in defs:
        cid = d.get("id") or d.get("local_id")
        if not cid:
            _record_issue("definition missing both id and local_id")
            continue

        # Prefer locating the marker by local_id (unique), but fall back to cid for
        # older packs.
        marker_key = d.get("local_id") or cid
        idxs = marker_lines_for.get(str(marker_key).upper())
        if not idxs and str(cid).upper() != str(marker_key).upper():
            idxs = marker_lines_for.get(str(cid).upper())

        if not idxs:
            _record_issue(
                "missing marker for "
                f"{d.get('qualname') or '<unknown>'} "
                f"(local_id={d.get('local_id') or '∅'}, id={cid})"
            )
            continue

        mi = idxs.pop()  # consume the bottom-most occurrence
        work.append((mi, d, str(cid)))

    work.sort(key=lambda t: t[0], reverse=True)

    for mi, d, cid in work:
        # Fetch canonical by cid first, then fall back to local_id.
        code = canonical.get(cid)
        if code is None:
            alt = d.get("local_id")
            if alt:
                code = canonical.get(str(alt))
        if code is None:
            _record_issue(
                "missing canonical source for "
                f"{d.get('qualname') or '<unknown>'} "
                f"(id={cid}, local_id={d.get('local_id') or '∅'})"
            )
            continue

        # Find def line above (supports single-line defs where marker is on def line).
        def_i = mi
        while def_i >= 0:
            s = lines[def_i].lstrip(" \t")
            if s.startswith("def ") or s.startswith("async def "):
                break
            def_i -= 1
        if def_i < 0:
            _record_issue(
                "unable to locate def line above marker for "
                f"{d.get('qualname') or '<unknown>'}"
            )
            continue

        def_indent = _ws_len(lines[def_i])

        # Include decorators directly above the def.
        start_i = def_i
        j = def_i - 1
        while j >= 0:
            if _ws_len(lines[j]) == def_indent and lines[j].lstrip(" \t").startswith(
                "@"
            ):
                start_i = j
                j -= 1
                continue
            break

        # Replace through the marker line (or just the def line for single-line defs).
        end_i = (def_i + 1) if mi == def_i else (mi + 1)

        repl = code.splitlines(keepends=True)
        if repl and not repl[-1].endswith("\n"):
            repl[-1] = repl[-1] + "\n"
        lines[start_i:end_i] = repl

    return "".join(lines)


def _unpack_single_markdown(markdown_text: str, out_dir: Path, *, strict: bool) -> None:
    packed = parse_packed_markdown(markdown_text)
    manifest = packed.manifest
    if manifest.get("format") != PACK_FORMAT_VERSION:
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

        defs = f.get("defs", [])
        marker_issues: list[str] = []
        reconstructed = _apply_canonical_into_stub(
            stub,
            defs,
            packed.canonical_sources,
            strict=strict,
            issues=marker_issues,
        )
        reconstructed = normalize_newlines(reconstructed)
        if marker_issues:
            msg = (
                f"Unresolved marker mapping for {rel}: "
                + "; ".join(marker_issues[:5])
                + ("; ..." if len(marker_issues) > 5 else "")
            )
            warnings.warn(msg, RuntimeWarning, stacklevel=2)

        exp_sha = f.get("sha256_original")
        if exp_sha:
            got_sha = hashlib.sha256(reconstructed.encode("utf-8")).hexdigest()
            if got_sha != exp_sha:
                warnings.warn(
                    f"SHA256 mismatch for {rel}: expected {exp_sha}, got {got_sha}",
                    RuntimeWarning,
                    stacklevel=2,
                )

        # Prevent path traversal / writing outside out_dir
        target = (out_dir / rel).resolve()
        if out_dir != target and out_dir not in target.parents:
            raise ValueError(f"Refusing to write outside out_dir: {rel}")
        ensure_parent_dir(target)
        target.write_text(reconstructed, encoding="utf-8", newline="\n")

    if missing:
        files_str = ", ".join(missing[:10])
        if len(missing) > 10:
            files_str += "..."
        msg = f"Missing stubbed file blocks for {len(missing)} file(s): {files_str}"
        warnings.warn(msg, RuntimeWarning, stacklevel=2)


def unpack_to_dir(markdown_text: str, out_dir: Path, *, strict: bool = False) -> None:
    sections = split_repository_sections(markdown_text)
    if not sections:
        _unpack_single_markdown(markdown_text, out_dir, strict=strict)
        return

    out_root = out_dir.resolve()
    for section in sections:
        _unpack_single_markdown(section.content, out_root / section.slug, strict=strict)
