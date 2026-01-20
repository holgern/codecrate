from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DefRef:
    """Represents a function/method definition discovered in a file."""

    path: Path
    module: str  # e.g. "codecrate.config"
    qualname: str  # e.g. "load_config" or "Class.method"
    id: str  # canonical id (dedupe may redirect)
    local_id: str  # id for this location (unique per location)
    kind: str  # "function" | "async_function"
    decorator_start: int  # 1-based
    def_line: int  # 1-based
    body_start: int  # 1-based (first stmt in body)
    end_line: int  # 1-based (end of def)
    doc_start: int | None = None  # 1-based, if docstring exists
    doc_end: int | None = None  # 1-based, if docstring exists
    is_single_line: bool = False  # def header and body on one line


@dataclass(frozen=True)
class ClassRef:
    """Represents a class definition discovered in a file."""

    path: Path
    module: str  # e.g. "codecrate.config"
    qualname: str  # e.g. "Config" or "Outer.Inner"
    id: str  # stable id for linking/indexing
    decorator_start: int  # 1-based
    class_line: int  # 1-based (line with 'class ...')
    end_line: int  # 1-based (end of class)


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
