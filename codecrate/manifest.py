from __future__ import annotations

import hashlib
from typing import Any

from .model import PackResult


def to_manifest(pack: PackResult) -> dict[str, Any]:
    def sha256_text(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    files = []
    for fp in pack.files:
        rel = fp.path.relative_to(pack.root).as_posix()
        # Minimal mapping needed to reconstruct canonical bodies when local_id != id.
        # Consumers should treat missing entries as "id == local_id".
        idmap: dict[str, str] = {}
        for item in list(getattr(fp, "classes", ())) + list(getattr(fp, "defs", ())):
            local_id = getattr(item, "local_id", None)
            cid = getattr(item, "id", None)
            if local_id and cid and local_id != cid:
                idmap[local_id] = cid

        entry: dict[str, Any] = {
            "path": rel,
            "sha256_original": sha256_text(fp.original_text),
            "sha256_stubbed": sha256_text(fp.stubbed_text),
        }
        if idmap:
            entry["idmap"] = idmap

        files.append(entry)

    # NOTE: Manifest schema changed (compacted). Bump format to avoid silent breakage
    # in older unpackers that expected full per-def records.
    return {"format": "codecrate.v4", "root": pack.root.as_posix(), "files": files}
