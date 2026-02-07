from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .fences import is_fence_close, parse_fence_open
from .ids import MARKER_NAMESPACE
from .mdparse import parse_packed_markdown
from .repositories import split_repository_sections
from .udiff import normalize_newlines
from .unpacker import _apply_canonical_into_stub

_MARK_RE = re.compile(rf"{MARKER_NAMESPACE}:(?:v\d+:)?(?P<id>[0-9A-Fa-f]{{8}})")
_ANCHOR_RE = re.compile(r'^\s*<a id="([^"]+)"></a>\s*$')


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str]
    warnings: list[str]


def validate_pack_markdown(
    markdown_text: str,
    *,
    root: Path | None = None,
    strict: bool = False,
) -> ValidationReport:
    sections = split_repository_sections(markdown_text)
    if not sections:
        return _validate_single_pack_markdown(markdown_text, root=root, strict=strict)

    errors: list[str] = []
    warnings: list[str] = []
    anchor_owner: dict[str, str] = {}

    root_resolved = root.resolve() if root is not None else None

    for section in sections:
        scope = f"repo '{section.label}' ({section.slug})"
        if not section.content.strip():
            errors.append(f"{scope}: repository section is empty")
            continue

        manifest_count = _count_manifest_blocks(section.content)
        if manifest_count != 1:
            errors.append(
                f"{scope}: expected exactly one codecrate-manifest block, "
                f"found {manifest_count}"
            )

        for anchor in _iter_anchor_ids(section.content):
            owner = anchor_owner.get(anchor)
            if owner is None:
                anchor_owner[anchor] = scope
                continue
            if owner != scope:
                errors.append(
                    f"Cross-repo anchor collision for '{anchor}': {owner} vs {scope}"
                )

        section_root = (
            root_resolved / section.slug if root_resolved is not None else None
        )
        try:
            report = _validate_single_pack_markdown(
                section.content,
                root=section_root,
                strict=strict,
            )
        except Exception as e:
            errors.append(f"{scope}: failed to parse repository pack: {e}")
            continue
        errors.extend(f"{scope}: {err}" for err in report.errors)
        warnings.extend(f"{scope}: {w}" for w in report.warnings)

    return ValidationReport(errors=errors, warnings=warnings)


def _validate_single_pack_markdown(
    markdown_text: str,
    *,
    root: Path | None = None,
    strict: bool = False,
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
    errors: list[str] = []
    warnings: list[str] = []

    packed = parse_packed_markdown(markdown_text)
    manifest = packed.manifest
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

        marker_ids = [m.group("id").upper() for m in _MARK_RE.finditer(stub_norm)]
        if marker_ids:
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
                msg = (
                    f"Missing FUNC marker in stub for {rel}:{d.get('qualname')} "
                    f"(local_id={lid or '∅'}, id={cid or '∅'})"
                )
                if strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)

        try:
            marker_issues: list[str] = []
            reconstructed = _apply_canonical_into_stub(
                stub_norm,
                defs,
                packed.canonical_sources,
                strict=False,
                issues=marker_issues,
            )
            reconstructed = normalize_newlines(reconstructed)
        except Exception as e:  # pragma: no cover
            errors.append(f"Failed to reconstruct {rel}: {e}")
            continue

        if marker_issues:
            for issue in marker_issues:
                msg = f"Unresolved marker mapping for {rel}: {issue}"
                if strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)

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


def _count_manifest_blocks(markdown_text: str) -> int:
    count = 0
    fence: str | None = None
    for line in markdown_text.splitlines():
        if fence is None:
            opened = parse_fence_open(line)
            if opened is None:
                continue
            fence = opened[0]
            if opened[1] == "codecrate-manifest":
                count += 1
            continue
        if is_fence_close(line, fence):
            fence = None
    return count


def _iter_anchor_ids(markdown_text: str) -> list[str]:
    anchors: list[str] = []
    fence: str | None = None
    for line in markdown_text.splitlines():
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            match = _ANCHOR_RE.match(line)
            if match:
                anchors.append(match.group(1))
            continue
        if is_fence_close(line, fence):
            fence = None
    return anchors
