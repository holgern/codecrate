from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .mdparse import parse_packed_markdown
from .udiff import normalize_newlines
from .unpacker import _apply_canonical_into_stub

_MARK_RE = re.compile(r"FUNC:([0-9A-Fa-f]{8})")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str]
    warnings: list[str]


def validate_pack_markdown(
    markdown_text: str, *, root: Path | None = None
) -> ValidationReport:
    """Validate a packed Codecrate Markdown for internal consistency.

    Checks (pack-only):
    - Every manifest file has a corresponding stubbed code block.
    - sha256_stubbed matches the stubbed code block (normalized newlines).
    - Every def in manifest has a canonical body in the function library.
    - Reconstructing each file from stub+canonical reproduces sha256_original.
    - Marker collisions / missing markers are reported as warnings.

    Optional root:
    - If provided, compares reconstructed 'original' text against files on disk.
    """
    packed = parse_packed_markdown(markdown_text)
    manifest = packed.manifest

    errors: list[str] = []
    warnings: list[str] = []

    root_resolved = root.resolve() if root is not None else None

    files = manifest.get("files") or []
    for f in files:
        rel = f.get("path")
        if not rel:
            errors.append("Manifest entry missing 'path'")
            continue

        stub = packed.stubbed_files.get(rel)
        if stub is None:
            errors.append(f"Missing stubbed file block for {rel}")
            continue

        stub_norm = normalize_newlines(stub)
        exp_stub = f.get("sha256_stubbed")
        got_stub = _sha256_text(stub_norm)
        if exp_stub and got_stub != exp_stub:
            errors.append(
                f"Stub sha mismatch for {rel}: expected {exp_stub}, got {got_stub}"
            )

        marker_ids = [m.group(1).upper() for m in _MARK_RE.finditer(stub_norm)]
        if marker_ids:
            from collections import Counter

            c = Counter(marker_ids)
            dup = [k for k, v in c.items() if v > 1]
            if dup:
                warnings.append(f"Marker collision in {rel}: {', '.join(sorted(dup))}")

        defs = f.get("defs") or []
        for d in defs:
            cid = str(d.get("id") or "").upper()
            lid = str(d.get("local_id") or "").upper()
            if cid and cid not in packed.canonical_sources:
                errors.append(
                    f"Missing canonical source for {rel}:{d.get('qualname')} id={cid}"
                )

            # local_id marker is preferred; fall back to id for older packs
            if (lid and lid not in marker_ids) and (cid and cid not in marker_ids):
                warnings.append(
                    f"Missing FUNC marker in stub for {rel}:{d.get('qualname')} "
                    f"(local_id={lid or '∅'}, id={cid or '∅'})"
                )

        try:
            reconstructed = _apply_canonical_into_stub(
                stub_norm, defs, packed.canonical_sources
            )
            reconstructed = normalize_newlines(reconstructed)
        except Exception as e:  # pragma: no cover
            errors.append(f"Failed to reconstruct {rel}: {e}")
            continue

        exp_orig = f.get("sha256_original")
        got_orig = _sha256_text(reconstructed)
        if exp_orig and got_orig != exp_orig:
            errors.append(
                f"Original sha mismatch for {rel}: expected {exp_orig}, got {got_orig}"
            )

        if root_resolved is not None:
            disk_path = root_resolved / rel
            if not disk_path.exists():
                warnings.append(f"On-disk file missing under root: {rel}")
            else:
                disk_text = normalize_newlines(
                    disk_path.read_text(encoding="utf-8", errors="replace")
                )
                if _sha256_text(disk_text) != got_orig:
                    warnings.append(f"On-disk file differs from pack for {rel}")

    return ValidationReport(errors=errors, warnings=warnings)
