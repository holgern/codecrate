from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DefRef:
    path: Path
    module: str
    qualname: str
    id: str
    local_id: str
    kind: str
    decorator_start: int
    def_line: int
    body_start: int
    end_line: int
    doc_start: int | None = None
    doc_end: int | None = None
    is_single_line: bool = False


@dataclass(frozen=True)
class ClassRef:
    path: Path
    module: str
    qualname: str
    id: str
    decorator_start: int
    class_line: int
    end_line: int


@dataclass(frozen=True)
class FilePack:
    path: Path
    module: str
    original_text: str
    stubbed_text: str
    line_count: int
    classes: list[ClassRef]
    defs: list[DefRef]


@dataclass(frozen=True)
class PackResult:
    root: Path
    files: list[FilePack]
    classes: list[ClassRef]
    defs: list[DefRef]
