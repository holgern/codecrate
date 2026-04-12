from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportRef:
    module: str
    imported_name: str | None
    alias: str | None
    line: int
    kind: str


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
    decorators: list[str] = field(default_factory=list)
    owner_class: str | None = None


@dataclass(frozen=True)
class ClassRef:
    path: Path
    module: str
    qualname: str
    id: str
    decorator_start: int
    class_line: int
    end_line: int
    base_classes: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParseResult:
    module: str
    classes: list[ClassRef]
    defs: list[DefRef]
    imports: list[ImportRef] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    module_docstring: tuple[int, int] | None = None


@dataclass(frozen=True)
class FilePack:
    path: Path
    module: str
    original_text: str
    stubbed_text: str
    line_count: int
    classes: list[ClassRef]
    defs: list[DefRef]
    imports: list[ImportRef] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    module_docstring: tuple[int, int] | None = None
    language_detected: str = "python"
    symbol_backend_requested: str = "python-ast"
    symbol_backend_used: str = "python-ast"
    symbol_extraction_status: str = "ok"


@dataclass(frozen=True)
class PackResult:
    root: Path
    files: list[FilePack]
    classes: list[ClassRef]
    defs: list[DefRef]
