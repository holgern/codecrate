from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from .ids import ID_FORMAT_VERSION, MARKER_FORMAT_VERSION, marker_token
from .model import PackResult


def manifest_sha256(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def machine_header(
    *,
    manifest: dict[str, Any],
    repo_label: str,
    repo_slug: str,
) -> dict[str, str]:
    return {
        "format": str(manifest.get("format") or "codecrate.v4"),
        "repo_label": repo_label,
        "repo_slug": repo_slug,
        "manifest_sha256": manifest_sha256(manifest),
    }


def to_manifest(pack: PackResult, *, minimal: bool = False) -> dict[str, Any]:
    def sha256_text(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _def_manifest_entry(defn: dict[str, Any], stubbed_text: str) -> dict[str, Any]:
        local_id = str(defn.get("local_id") or "")
        canonical_id = str(defn.get("id") or "")
        has_marker = False
        if local_id:
            has_marker = marker_token(local_id) in stubbed_text
        if not has_marker and canonical_id:
            # Backwards compatibility with older packs that keyed stub markers by id.
            has_marker = marker_token(canonical_id) in stubbed_text
        return defn | {"has_marker": has_marker}

    files = []
    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        entry: dict[str, Any] = {
            "path": rel,
            "line_count": fp.line_count,
            "sha256_original": sha256_text(fp.original_text),
        }
        if not minimal:
            defs = [asdict(d) | {"path": rel} for d in fp.defs]
            entry |= {
                "module": fp.module,
                "sha256_stubbed": sha256_text(fp.stubbed_text),
                "classes": [asdict(c) | {"path": rel} for c in fp.classes],
                "defs": [_def_manifest_entry(d, fp.stubbed_text) for d in defs],
            }
        files.append(entry)
    # Root is already shown at the top of the pack; keep manifest root stable + short.
    return {
        "format": "codecrate.v4",
        "id_format_version": ID_FORMAT_VERSION,
        "marker_format_version": MARKER_FORMAT_VERSION,
        "root": ".",
        "files": files,
    }
