from __future__ import annotations

import hashlib
from pathlib import Path


def stable_location_id(path: Path, qualname: str, lineno: int) -> str:
    payload = f"{path.as_posix()}::{qualname}::{lineno}".encode()
    return hashlib.sha1(payload).hexdigest()[:8].upper()


def stable_body_hash(code: str) -> str:
    norm = "\n".join(
        line.rstrip()
        for line in code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest().upper()
