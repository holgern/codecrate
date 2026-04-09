from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .formats import INDEX_JSON_FORMAT_VERSION, PACK_FORMAT_VERSION
from .ids import (
    ID_FORMAT_VERSION,
    MACHINE_ID_FORMAT_VERSION,
    stable_machine_location_id,
)
from .markdown import _anchor_for, _fence_lang_for, _file_anchor, _file_src_anchor
from .token_budget import Part
from .tokens import approx_token_count

if TYPE_CHECKING:
    from .cli import PackRun


def _relative_output_path(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def _sort_rel_paths(paths: Iterable[str]) -> list[str]:
    return sorted(set(paths), key=lambda item: (item.lower(), item))


def _sorted_unique_parts(parts: list[Part]) -> list[Part]:
    def _kind_rank(part: Part) -> tuple[int, int, str]:
        stem = part.path.stem
        if part.kind == "index" or ".index" in stem:
            return (0, 0, part.path.name)
        part_number = 0
        part_match = part.path.stem.rsplit(".part", 1)
        if len(part_match) == 2:
            try:
                part_number = int(part_match[1])
            except ValueError:
                part_number = 0
        if part.kind == "part":
            return (1, part_number, part.path.name)
        return (2, 0, part.path.name)

    seen: set[str] = set()
    unique: list[Part] = []
    for part in sorted(parts, key=_kind_rank):
        key = part.path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return unique


def _manifest_files_by_path(run: PackRun) -> dict[str, dict[str, Any]]:
    manifest_files = run.manifest.get("files")
    if not isinstance(manifest_files, list):
        return {}
    by_path: dict[str, dict[str, Any]] = {}
    for item in manifest_files:
        if not isinstance(item, dict):
            continue
        rel = item.get("path")
        if isinstance(rel, str) and rel:
            by_path[rel] = item
    return by_path


def _manifest_defs_by_local_id(run: PackRun) -> dict[str, dict[str, Any]]:
    defs_by_local_id: dict[str, dict[str, Any]] = {}
    for file_entry in _manifest_files_by_path(run).values():
        defs = file_entry.get("defs")
        if not isinstance(defs, list):
            continue
        for item in defs:
            if not isinstance(item, dict):
                continue
            local_id = item.get("local_id")
            if isinstance(local_id, str) and local_id:
                defs_by_local_id[local_id] = item
    return defs_by_local_id


def _strong_id_maps(run: PackRun) -> tuple[dict[str, str], dict[str, str]]:
    local_machine_ids: dict[str, str] = {}
    canonical_machine_ids: dict[str, str] = {}

    for defn in sorted(
        run.pack_result.defs,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.def_line,
            item.qualname,
            item.local_id,
        ),
    ):
        rel = defn.path.relative_to(run.pack_result.root)
        machine_id = stable_machine_location_id(rel, defn.qualname, defn.def_line)
        local_machine_ids[defn.local_id] = machine_id
        if defn.local_id == defn.id:
            canonical_machine_ids.setdefault(defn.id, machine_id)

    for defn in run.pack_result.defs:
        canonical_machine_ids.setdefault(
            defn.id,
            local_machine_ids.get(defn.local_id)
            or stable_machine_location_id(
                defn.path.relative_to(run.pack_result.root),
                defn.qualname,
                defn.def_line,
            ),
        )

    return local_machine_ids, canonical_machine_ids


def _safety_payload(run: PackRun) -> dict[str, Any]:
    findings = sorted(
        run.safety_findings,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.action,
            item.reason,
        ),
    )
    return {
        "skipped_count": run.skipped_for_safety_count,
        "redacted_count": run.redacted_for_safety_count,
        "findings": [
            {
                "path": item.path.relative_to(run.pack_result.root).as_posix(),
                "reason": item.reason,
                "action": item.action,
            }
            for item in findings
        ],
    }


def _split_policy(run: PackRun) -> str:
    if run.options.split_allow_cut_files:
        return "cut-files"
    if run.options.split_strict:
        return "strict"
    return "preserve"


def _part_id(*, slug: str, kind: str, part_number: int | None) -> str:
    if kind == "pack":
        return f"{slug}:pack"
    if kind == "index":
        return f"{slug}:index"
    if part_number is None:
        return f"{slug}:part"
    return f"{slug}:part{part_number}"


def _all_repo_file_paths(run: PackRun) -> list[str]:
    return _sort_rel_paths(
        file_pack.path.relative_to(run.pack_result.root).as_posix()
        for file_pack in run.pack_result.files
    )


def _all_repo_canonical_ids(run: PackRun) -> list[str]:
    if run.effective_layout != "stubs":
        return []
    _, canonical_machine_ids = _strong_id_maps(run)
    return sorted(canonical_machine_ids[cid] for cid in sorted(run.canonical_sources))


def _all_repo_display_canonical_ids(run: PackRun) -> list[str]:
    if run.effective_layout != "stubs":
        return []
    return sorted(run.canonical_sources)


def _part_metadata(
    run: PackRun,
    *,
    repo_output_parts: list[Part],
    base_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    parts_in = _sorted_unique_parts(repo_output_parts)
    _, canonical_machine_ids = _strong_id_maps(run)
    if len(parts_in) == 1 and parts_in[0].kind == "pack":
        part = parts_in[0]
        rel_path = _relative_output_path(part.path, base_dir=base_dir)
        part_entry = {
            "part_id": _part_id(slug=run.slug, kind="pack", part_number=None),
            "path": rel_path,
            "kind": "pack",
            "repo_slug": run.slug,
            "char_count": len(part.content),
            "token_estimate": approx_token_count(part.content),
            "is_oversized": False,
            "contains": {
                "files": list(part.files) or _all_repo_file_paths(run),
                "canonical_ids": list(part.canonical_ids)
                or _all_repo_canonical_ids(run),
                "display_canonical_ids": _all_repo_display_canonical_ids(run),
                "section_types": list(part.section_types) or ["Pack"],
            },
        }
        file_to_part = {
            rel: rel_path for rel in (list(part.files) or _all_repo_file_paths(run))
        }
        func_to_part = {
            canonical_id: rel_path
            for canonical_id in (
                list(part.canonical_ids) or _all_repo_canonical_ids(run)
            )
        }
        return [part_entry], file_to_part, func_to_part

    parts: list[dict[str, Any]] = []
    file_to_part: dict[str, str] = {}
    func_to_part: dict[str, str] = {}
    part_number = 0

    for part in parts_in:
        kind = part.kind
        if kind == "part":
            part_number += 1
            current_part_number = part_number
        else:
            current_part_number = None
        rel_path = _relative_output_path(part.path, base_dir=base_dir)
        files = list(part.files)
        canonical_ids = [
            canonical_machine_ids.get(display_id, display_id)
            for display_id in part.canonical_ids
        ]
        section_types = list(part.section_types)
        display_canonical_ids = list(part.canonical_ids)
        parts.append(
            {
                "part_id": _part_id(
                    slug=run.slug,
                    kind=kind,
                    part_number=current_part_number,
                ),
                "path": rel_path,
                "kind": kind,
                "repo_slug": run.slug,
                "char_count": len(part.content),
                "token_estimate": approx_token_count(part.content),
                "is_oversized": (
                    run.options.split_max_chars > 0
                    and kind != "index"
                    and len(part.content) > run.options.split_max_chars
                ),
                "contains": {
                    "files": files,
                    "canonical_ids": canonical_ids,
                    "display_canonical_ids": display_canonical_ids,
                    "section_types": section_types,
                },
            }
        )
        for rel in files:
            file_to_part.setdefault(rel, rel_path)
        for canonical_id in canonical_ids:
            func_to_part.setdefault(canonical_id, rel_path)

    return parts, file_to_part, func_to_part


def _safety_flags_by_path(run: PackRun) -> dict[str, dict[str, bool]]:
    flags: dict[str, dict[str, bool]] = {}
    for item in run.safety_findings:
        rel = item.path.relative_to(run.pack_result.root).as_posix()
        entry = flags.setdefault(
            rel,
            {
                "is_redacted": False,
                "is_binary_skipped": False,
                "is_safety_skipped": False,
            },
        )
        if item.action == "redacted":
            entry["is_redacted"] = True
        else:
            if item.reason == "binary":
                entry["is_binary_skipped"] = True
            else:
                entry["is_safety_skipped"] = True
    return flags


def _file_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
) -> list[dict[str, Any]]:
    manifest_by_path = _manifest_files_by_path(run)
    safety_by_path = _safety_flags_by_path(run)
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)

    payload: list[dict[str, Any]] = []
    for file_pack in sorted(
        run.pack_result.files,
        key=lambda item: item.path.relative_to(run.pack_result.root).as_posix(),
    ):
        rel = file_pack.path.relative_to(run.pack_result.root).as_posix()
        manifest_entry = manifest_by_path.get(rel, {})
        safety_flags = safety_by_path.get(
            rel,
            {
                "is_redacted": False,
                "is_binary_skipped": False,
                "is_safety_skipped": False,
            },
        )
        file_entry: dict[str, Any] = {
            "path": rel,
            "language": _fence_lang_for(rel),
            "language_detected": file_pack.language_detected,
            "module": file_pack.module or None,
            "line_count": file_pack.line_count,
            "sha256_original": manifest_entry.get("sha256_original"),
            "is_stubbed": run.effective_layout == "stubs",
            "is_redacted": safety_flags["is_redacted"],
            "is_binary_skipped": safety_flags["is_binary_skipped"],
            "is_safety_skipped": safety_flags["is_safety_skipped"],
            "symbol_backend_requested": file_pack.symbol_backend_requested,
            "symbol_backend_used": file_pack.symbol_backend_used,
            "symbol_extraction_status": file_pack.symbol_extraction_status,
            "part_path": file_to_part.get(rel),
            "anchors": {
                "index": _file_anchor(rel),
                "source": _file_src_anchor(rel),
            },
            "symbol_ids": [
                local_machine_ids[defn.local_id]
                for defn in sorted(
                    file_pack.defs,
                    key=lambda item: (item.def_line, item.qualname, item.local_id),
                )
            ],
            "display_symbol_ids": [
                defn.local_id
                for defn in sorted(
                    file_pack.defs,
                    key=lambda item: (item.def_line, item.qualname, item.local_id),
                )
            ],
            "symbol_canonical_ids": [
                canonical_machine_ids[defn.id]
                for defn in sorted(
                    file_pack.defs,
                    key=lambda item: (item.def_line, item.qualname, item.local_id),
                )
            ],
        }
        sha256_stubbed = manifest_entry.get("sha256_stubbed")
        if isinstance(sha256_stubbed, str) and sha256_stubbed:
            file_entry["sha256_stubbed"] = sha256_stubbed
        payload.append(file_entry)
    return payload


def _symbol_payload(
    run: PackRun,
    *,
    file_to_part: dict[str, str],
    func_to_part: dict[str, str],
) -> list[dict[str, Any]]:
    manifest_defs_by_local_id = _manifest_defs_by_local_id(run)
    local_machine_ids, canonical_machine_ids = _strong_id_maps(run)

    symbols: list[dict[str, Any]] = []
    for defn in sorted(
        run.pack_result.defs,
        key=lambda item: (
            item.path.relative_to(run.pack_result.root).as_posix(),
            item.def_line,
            item.qualname,
            item.local_id,
        ),
    ):
        rel = defn.path.relative_to(run.pack_result.root).as_posix()
        manifest_def = manifest_defs_by_local_id.get(defn.local_id, {})
        symbol_entry: dict[str, Any] = {
            "display_id": defn.id,
            "canonical_id": canonical_machine_ids[defn.id],
            "display_local_id": defn.local_id,
            "local_id": local_machine_ids[defn.local_id],
            "qualname": defn.qualname,
            "kind": defn.kind,
            "path": rel,
            "module": defn.module or None,
            "def_line": defn.def_line,
            "end_line": defn.end_line,
            "body_start": defn.body_start,
            "has_marker": bool(manifest_def.get("has_marker", False)),
            "is_deduped": defn.id != defn.local_id,
            "file_part": file_to_part.get(rel),
            "file_anchor": _file_src_anchor(rel),
        }
        if run.effective_layout == "stubs" and defn.id in run.canonical_sources:
            symbol_entry["canonical_part"] = func_to_part.get(
                canonical_machine_ids[defn.id]
            )
            symbol_entry["canonical_anchor"] = _anchor_for(
                defn.id,
                defn.module,
                defn.qualname,
            )
        symbols.append(symbol_entry)
    return symbols


def build_index_payload(
    *,
    codecrate_version: str,
    index_output_path: Path,
    pack_runs: list[PackRun],
    repo_output_parts: dict[str, list[Part]],
    is_split: bool,
) -> dict[str, Any]:
    base_dir = index_output_path.parent.resolve()

    repositories: list[dict[str, Any]] = []
    all_output_files: list[str] = []
    for run in pack_runs:
        parts_input = repo_output_parts.get(run.slug, [])
        parts, file_to_part, func_to_part = _part_metadata(
            run,
            repo_output_parts=parts_input,
            base_dir=base_dir,
        )
        all_output_files.extend(part["path"] for part in parts)
        markdown_path = parts[0]["path"] if len(parts) == 1 else None
        repositories.append(
            {
                "label": run.label,
                "slug": run.slug,
                "profile": run.options.profile,
                "split_policy": _split_policy(run),
                "layout": run.effective_layout,
                "contains_manifest": run.options.include_manifest,
                "manifest_sha256": run.manifest_sha256,
                "markdown_path": markdown_path,
                "parts": parts,
                "safety": _safety_payload(run),
                "files": _file_payload(
                    run,
                    file_to_part=file_to_part,
                ),
                "symbols": _symbol_payload(
                    run,
                    file_to_part=file_to_part,
                    func_to_part=func_to_part,
                ),
            }
        )

    return {
        "format": INDEX_JSON_FORMAT_VERSION,
        "generated_by": {
            "tool": "codecrate",
            "version": codecrate_version,
        },
        "pack": {
            "format": PACK_FORMAT_VERSION,
            "root": ".",
            "is_split": is_split,
            "repository_count": len(pack_runs),
            "display_id_format_version": ID_FORMAT_VERSION,
            "canonical_id_format_version": MACHINE_ID_FORMAT_VERSION,
            "profiles": sorted({run.options.profile for run in pack_runs}),
            "output_files": _sort_rel_paths(all_output_files),
        },
        "repositories": repositories,
    }


def write_index_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
