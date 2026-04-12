from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..analysis_metadata import import_edges_payload, role_hint_for_file
from ..ids import stable_machine_location_id
from ..output_model import PackRun
from ..token_budget import Part


def _relative_output_path(path: Path, *, base_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def _sort_rel_paths(paths: Iterable[str]) -> list[str]:
    return sorted(set(paths), key=lambda item: (item.lower(), item))


def _line_range(start_line: int, end_line: int) -> dict[str, int]:
    return {
        "start_line": start_line,
        "end_line": end_line,
    }


def _locator_line_range(start_line: int, end_line: int) -> dict[str, int]:
    return {
        "start": start_line,
        "end": end_line,
    }


def _locator_line_range_from_markdown(
    line_range: dict[str, Any] | None,
) -> dict[str, int] | None:
    if not isinstance(line_range, dict):
        return None
    start_line = int(line_range.get("start_line", 0) or 0)
    end_line = int(line_range.get("end_line", 0) or 0)
    if start_line <= 0 or end_line < start_line:
        return None
    return _locator_line_range(start_line, end_line)


def _line_ranges_from_metadata(ranges: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        key: _line_range(value.start_line, value.end_line)
        for key, value in ranges.items()
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _class_id_maps(
    run: PackRun,
) -> tuple[dict[str, str], dict[tuple[str, str], dict[str, str]]]:
    machine_ids: dict[str, str] = {}
    by_path_qualname: dict[tuple[str, str], dict[str, str]] = {}
    for class_ref in run.pack_result.classes:
        rel = class_ref.path.relative_to(run.pack_result.root).as_posix()
        machine_id = stable_machine_location_id(
            Path(rel),
            f"class:{class_ref.qualname}",
            class_ref.class_line,
        )
        machine_ids[class_ref.id] = machine_id
        by_path_qualname[(rel, class_ref.qualname)] = {
            "display_local_id": class_ref.id,
            "local_id": machine_id,
        }
    return machine_ids, by_path_qualname


def _imports_by_source(run: PackRun) -> dict[str, list[dict[str, Any]]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for edge in import_edges_payload(run.pack_result):
        source_path = str(edge.get("source_path") or "")
        if not source_path:
            continue
        by_source.setdefault(source_path, []).append(
            {
                "module": edge.get("import_module"),
                "resolved_module": edge.get("resolved_module"),
                "imported_name": edge.get("imported_name"),
                "alias": edge.get("alias"),
                "line": edge.get("line"),
                "kind": edge.get("kind"),
                "target_module": edge.get("target_module"),
                "target_path": edge.get("target_path"),
            }
        )
    return by_source


def _role_hints_by_path(run: PackRun) -> dict[str, str | None]:
    return {
        file_pack.path.relative_to(run.pack_result.root).as_posix(): role_hint_for_file(
            file_pack.path.relative_to(run.pack_result.root).as_posix()
        )
        for file_pack in run.pack_result.files
    }


def _parameter_payload(parameters: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": parameter.name,
            "kind": parameter.kind,
            "has_default": parameter.has_default,
            "annotation": parameter.annotation,
        }
        for parameter in parameters
    ]


def _semantic_symbol_payload(defn: Any) -> dict[str, Any]:
    return {
        "signature_text": defn.signature_text,
        "parameters": _parameter_payload(defn.parameters),
        "return_annotation": defn.return_annotation,
        "is_method": defn.is_method,
        "is_property": defn.is_property,
        "is_classmethod": defn.is_classmethod,
        "is_staticmethod": defn.is_staticmethod,
        "is_generator": defn.is_generator,
        "is_coroutine": defn.is_coroutine,
        "is_public": defn.is_public,
        "is_overload": defn.is_overload,
        "is_abstractmethod": defn.is_abstractmethod,
    }


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


def _should_include_canonical_ids(run: PackRun) -> bool:
    return run.effective_layout == "stubs" or any(
        defn.id != defn.local_id for defn in run.pack_result.defs
    )
