from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Any

from .model import PackResult


def to_manifest(pack: PackResult) -> dict[str, Any]:
    def sha256_text(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    files = []
    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        files.append(
            {
                "path": rel,
                "module": fp.module,
                "line_count": fp.line_count,
                "sha256_original": sha256_text(fp.original_text),
                "sha256_stubbed": sha256_text(fp.stubbed_text),
                "classes": [asdict(c) | {"path": rel} for c in fp.classes],
                "defs": [asdict(d) | {"path": rel} for d in fp.defs],
            }
        )
    return {"format": "codecrate.v3", "root": pack.root.as_posix(), "files": files}
