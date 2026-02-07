from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .fences import is_fence_close, parse_fence_open
from .ids import ID_FORMAT_VERSION, MARKER_FORMAT_VERSION, MARKER_NAMESPACE
from .manifest import manifest_sha256
from .mdparse import parse_packed_markdown
from .repositories import split_repository_sections
from .udiff import normalize_newlines
from .unpacker import _apply_canonical_into_stub

_MARK_RE = re.compile(rf"{MARKER_NAMESPACE}:(?:v\d+:)?(?P<id>[0-9A-Fa-f]{{8}})")
_ANCHOR_RE = re.compile(r'^\s*<a id="([^"]+)"></a>\s*$')


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_machine_header(
    *,
    machine_header: dict | None,
    manifest: dict,
) -> list[str]:
    if machine_header is None:
        return []

    errors: list[str] = []
    got_format = str(machine_header.get("format") or "")
    exp_format = str(manifest.get("format") or "")
    if got_format and exp_format and got_format != exp_format:
        errors.append(
            f"Machine header format mismatch: expected {exp_format}, got {got_format}"
        )

    got_manifest_sha = str(machine_header.get("manifest_sha256") or "")
    exp_manifest_sha = manifest_sha256(manifest)
    if not got_manifest_sha:
        errors.append("Machine header missing manifest_sha256")
    elif got_manifest_sha != exp_manifest_sha:
        errors.append(
            "Machine header checksum mismatch: "
            f"expected {exp_manifest_sha}, got {got_manifest_sha}"
        )
    return errors


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class _FileValidationResult:
    errors: list[str]
    warnings: list[str]
    marker_ids: list[str]


def _validate_manifest_structure(markdown_text: str, manifest: dict) -> list[str]:
    errors: list[str] = []

    file_block_paths = _scan_file_block_paths(markdown_text)
    manifest_paths = [
        str(f.get("path") or "") for f in manifest.get("files") or [] if f.get("path")
    ]

    file_block_counts = Counter(file_block_paths)
    for rel in sorted(path for path, count in file_block_counts.items() if count > 1):
        errors.append(f"Duplicate file block for {rel}")

    file_block_set = set(file_block_paths)
    manifest_path_set = set(manifest_paths)
    for rel in sorted(manifest_path_set - file_block_set):
        errors.append(f"Manifest file missing from file blocks: {rel}")
    for rel in sorted(file_block_set - manifest_path_set):
        errors.append(f"File block not present in manifest: {rel}")

    referenced_ids = {
        str(d.get("id") or "").upper()
        for f in manifest.get("files") or []
        for d in f.get("defs") or []
        if d.get("id")
    }
    function_library_ids = {
        i.upper() for i in _scan_function_library_ids(markdown_text)
    }
    for orphan in sorted(function_library_ids - referenced_ids):
        errors.append(f"Orphan function-library entry: id={orphan}")

    return errors


def _is_sha256_hex(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value.lower())


def _validate_manifest_schema(manifest: dict) -> list[str]:
    errors: list[str] = []

    fmt = manifest.get("format")
    if fmt != "codecrate.v4":
        errors.append(f"Unsupported manifest format: {fmt!r}")

    id_fmt = manifest.get("id_format_version")
    if id_fmt not in {None, ID_FORMAT_VERSION}:
        errors.append(
            f"Unsupported id_format_version: {id_fmt!r} (expected {ID_FORMAT_VERSION})"
        )
    marker_fmt = manifest.get("marker_format_version")
    if marker_fmt not in {None, MARKER_FORMAT_VERSION}:
        errors.append(
            "Unsupported marker_format_version: "
            f"{marker_fmt!r} (expected {MARKER_FORMAT_VERSION})"
        )

    files = manifest.get("files")
    if not isinstance(files, list):
        errors.append("Manifest 'files' must be a list")
        return errors

    for i, f in enumerate(files):
        if not isinstance(f, dict):
            errors.append(f"Manifest file[{i}] must be an object")
            continue
        rel = f.get("path")
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"Manifest file[{i}] has invalid 'path'")
        if "line_count" in f and not isinstance(f.get("line_count"), int):
            errors.append(f"Manifest file[{i}] has invalid 'line_count'")
        if not _is_sha256_hex(f.get("sha256_original")):
            errors.append(f"Manifest file[{i}] has invalid 'sha256_original'")
        if "sha256_stubbed" in f and not _is_sha256_hex(f.get("sha256_stubbed")):
            errors.append(f"Manifest file[{i}] has invalid 'sha256_stubbed'")

        defs = f.get("defs")
        if defs is None:
            continue
        if "sha256_stubbed" not in f:
            errors.append(
                f"Manifest file[{i}] missing 'sha256_stubbed' for stub layout"
            )
        if not isinstance(defs, list):
            errors.append(f"Manifest file[{i}] has invalid 'defs' (must be list)")
            continue
        for j, d in enumerate(defs):
            if not isinstance(d, dict):
                errors.append(f"Manifest file[{i}] def[{j}] must be an object")
                continue
            if not isinstance(d.get("id"), str) or not d.get("id"):
                errors.append(f"Manifest file[{i}] def[{j}] has invalid 'id'")
            if not isinstance(d.get("local_id"), str) or not d.get("local_id"):
                errors.append(f"Manifest file[{i}] def[{j}] has invalid 'local_id'")
            if not isinstance(d.get("qualname"), str) or not d.get("qualname"):
                errors.append(f"Manifest file[{i}] def[{j}] has invalid 'qualname'")

    return errors


def _validate_file_entry(
    *,
    file_entry: dict,
    packed: object,
    strict: bool,
    root_resolved: Path | None,
    encoding_errors: str,
) -> _FileValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    rel = file_entry.get("path")
    if not rel:
        return _FileValidationResult(
            errors=["Manifest entry missing 'path'"],
            warnings=[],
            marker_ids=[],
        )

    stub = getattr(packed, "stubbed_files", {}).get(rel)
    if stub is None:
        return _FileValidationResult(
            errors=[f"Missing stubbed file block for {rel}"],
            warnings=[],
            marker_ids=[],
        )

    stub_norm = normalize_newlines(stub)
    exp_stub = file_entry.get("sha256_stubbed")
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

    defs = file_entry.get("defs") or []
    canonical_sources = getattr(packed, "canonical_sources", {})
    for d in defs:
        cid = str(d.get("id") or "").upper()
        lid = str(d.get("local_id") or "").upper()
        if cid and cid not in canonical_sources:
            errors.append(
                f"Missing canonical source for {rel}:{d.get('qualname')} id={cid}"
            )

        if d.get("has_marker") is False:
            continue

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
            canonical_sources,
            strict=False,
            issues=marker_issues,
        )
        reconstructed = normalize_newlines(reconstructed)
    except Exception as e:  # pragma: no cover
        errors.append(f"Failed to reconstruct {rel}: {e}")
        return _FileValidationResult(
            errors=errors, warnings=warnings, marker_ids=marker_ids
        )

    for issue in marker_issues:
        msg = f"Unresolved marker mapping for {rel}: {issue}"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    exp_orig = file_entry.get("sha256_original")
    got_orig = _sha256_text(reconstructed)
    if exp_orig and got_orig != exp_orig:
        errors.append(
            f"Original sha mismatch for {rel}: expected {exp_orig}, got {got_orig}"
        )

    if root_resolved is not None:
        disk_path = root_resolved / str(rel)
        if not disk_path.exists():
            warnings.append(f"On-disk file missing under root: {rel}")
        else:
            try:
                disk_text = normalize_newlines(
                    disk_path.read_text(encoding="utf-8", errors=encoding_errors)
                )
            except UnicodeDecodeError as e:
                errors.append(
                    f"Failed to decode on-disk file {rel} "
                    f"(encoding_errors={encoding_errors}): {e}"
                )
                return _FileValidationResult(
                    errors=errors,
                    warnings=warnings,
                    marker_ids=marker_ids,
                )
            if _sha256_text(disk_text) != got_orig:
                warnings.append(f"On-disk file differs from pack for {rel}")

    return _FileValidationResult(
        errors=errors, warnings=warnings, marker_ids=marker_ids
    )


def validate_pack_markdown(
    markdown_text: str,
    *,
    root: Path | None = None,
    strict: bool = False,
    encoding_errors: str = "replace",
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
                encoding_errors=encoding_errors,
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
    encoding_errors: str = "replace",
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

    manifest_count = _count_manifest_blocks(markdown_text)
    if manifest_count != 1:
        errors.append(
            f"expected exactly one codecrate-manifest block, found {manifest_count}"
        )

    machine_header_count = _count_machine_header_blocks(markdown_text)
    if machine_header_count != 1:
        errors.append(
            "expected exactly one codecrate-machine-header block, "
            f"found {machine_header_count}"
        )

    errors.extend(_validate_manifest_schema(manifest))

    errors.extend(
        _validate_machine_header(
            machine_header=packed.machine_header,
            manifest=manifest,
        )
    )

    errors.extend(_validate_manifest_structure(markdown_text, manifest))

    files = manifest.get("files") or []
    marker_owners: dict[str, set[str]] = {}
    for f in files:
        result = _validate_file_entry(
            file_entry=f,
            packed=packed,
            strict=strict,
            root_resolved=root_resolved,
            encoding_errors=encoding_errors,
        )
        errors.extend(result.errors)
        warnings.extend(result.warnings)
        rel = str(f.get("path") or "")
        for marker_id in result.marker_ids:
            marker_owners.setdefault(marker_id, set()).add(rel)

    for marker_id in sorted(marker_owners):
        owners = sorted(marker_owners[marker_id])
        if len(owners) <= 1:
            continue
        warnings.append(
            f"Repo-scope marker collision for {marker_id}: {', '.join(owners)}"
        )

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


def _count_machine_header_blocks(markdown_text: str) -> int:
    count = 0
    fence: str | None = None
    for line in markdown_text.splitlines():
        if fence is None:
            opened = parse_fence_open(line)
            if opened is None:
                continue
            fence = opened[0]
            if opened[1] == "codecrate-machine-header":
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


def _scan_section_lines(markdown_text: str, section_title: str) -> list[str]:
    lines = markdown_text.splitlines()
    fence: str | None = None
    start: int | None = None

    for i, line in enumerate(lines):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            if line.strip() == section_title:
                start = i + 1
                break
        else:
            if is_fence_close(line, fence):
                fence = None

    if start is None:
        return []

    fence = None
    end = len(lines)
    for j in range(start, len(lines)):
        line = lines[j]
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            if line.startswith("## ") and line.strip() != section_title:
                end = j
                break
        else:
            if is_fence_close(line, fence):
                fence = None

    return lines[start:end]


def _scan_file_block_paths(markdown_text: str) -> list[str]:
    paths: list[str] = []
    fence: str | None = None
    for line in _scan_section_lines(markdown_text, "## Files"):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
        else:
            if is_fence_close(line, fence):
                fence = None
            continue

        if not line.startswith("### `"):
            continue
        first_tick = line.find("`")
        if first_tick < 0:
            continue
        second_tick = line.find("`", first_tick + 1)
        if second_tick <= first_tick:
            continue
        rel = line[first_tick + 1 : second_tick].strip()
        if rel:
            paths.append(rel)
    return paths


def _scan_function_library_ids(markdown_text: str) -> list[str]:
    ids: list[str] = []
    fence: str | None = None
    for line in _scan_section_lines(markdown_text, "## Function Library"):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
        else:
            if is_fence_close(line, fence):
                fence = None
            continue

        if not line.startswith("### "):
            continue
        title = line.replace("###", "", 1).strip()
        maybe_id = title.split(" — ", 1)[0].strip()
        if maybe_id:
            ids.append(maybe_id)
    return ids
