from __future__ import annotations

from pathlib import Path
from typing import Any

from ..locators import anchor_for_file_index
from ..output_model import PackRun
from ..token_budget import Part
from ..tokens import approx_token_count
from .common import (
    _all_repo_canonical_ids,
    _all_repo_display_canonical_ids,
    _all_repo_file_paths,
    _relative_output_path,
    _sha256_text,
    _sorted_unique_parts,
    _strong_id_maps,
)


def _part_id(*, slug: str, kind: str, part_number: int | None) -> str:
    if kind == "pack":
        return f"{slug}:pack"
    if kind == "index":
        return f"{slug}:index"
    if part_number is None:
        return f"{slug}:part"
    return f"{slug}:part{part_number}"


def _part_metadata(
    run: PackRun,
    *,
    repo_output_parts: list[Part],
    base_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str], dict[str, str]]:
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
            "line_count": len(part.content.splitlines()),
            "sha256_content": _sha256_text(part.content),
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
        single_file_to_part = {
            rel: rel_path for rel in (list(part.files) or _all_repo_file_paths(run))
        }
        single_file_index_to_part = {
            rel: rel_path for rel in (list(part.files) or _all_repo_file_paths(run))
        }
        single_func_to_part = {
            canonical_id: rel_path
            for canonical_id in (
                list(part.canonical_ids) or _all_repo_canonical_ids(run)
            )
        }
        return (
            [part_entry],
            single_file_to_part,
            single_file_index_to_part,
            single_func_to_part,
        )

    parts: list[dict[str, Any]] = []
    file_to_part: dict[str, str] = {}
    file_index_to_part: dict[str, str] = {}
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
                "line_count": len(part.content.splitlines()),
                "sha256_content": _sha256_text(part.content),
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
        for rel in _all_repo_file_paths(run):
            if anchor_for_file_index(rel) in part.content:
                file_index_to_part.setdefault(rel, rel_path)
        for canonical_id in canonical_ids:
            func_to_part.setdefault(canonical_id, rel_path)

    return parts, file_to_part, file_index_to_part, func_to_part
