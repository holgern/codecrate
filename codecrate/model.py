from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DefRef:
    """Represents a function/method definition discovered in a file."""

    path: Path
    module: str  # module derived from relative path, e.g. "pkg.mod"
    qualname: str  # within module, e.g. "Class.method" or "func"
    id: str  # canonical id (dedupe may redirect)
    local_id: str  # id for this location (always unique per location)
    kind: str  # "function" | "async_function"
    decorator_start: int  # 1-based
    def_line: int  # 1-based
    body_start: int  # 1-based (first stmt in body)
    end_line: int  # 1-based (end of def)
    doc_start: int | None = None  # 1-based, if docstring exists
    doc_end: int | None = None  # 1-based, if docstring exists
    is_single_line: bool = False  # def header and body on one line


@dataclass(frozen=True)
class FilePack:
    path: Path
    module: str
    original_text: str
    stubbed_text: str
    defs: list[DefRef]


@dataclass(frozen=True)
class PackResult:
    root: Path
    files: list[FilePack]
    defs: list[DefRef]  # flattened
