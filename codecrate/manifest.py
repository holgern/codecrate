from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from .ids import ID_FORMAT_VERSION, MARKER_FORMAT_VERSION
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

    files = []
    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        entry: dict[str, Any] = {
            "path": rel,
            "line_count": fp.line_count,
            "sha256_original": sha256_text(fp.original_text),
        }
        if not minimal:
            entry |= {
                "module": fp.module,
                "sha256_stubbed": sha256_text(fp.stubbed_text),
                "classes": [asdict(c) | {"path": rel} for c in fp.classes],
                "defs": [asdict(d) | {"path": rel} for d in fp.defs],
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
