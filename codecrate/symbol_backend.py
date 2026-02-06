from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .ids import stable_location_id
from .model import DefRef

_LANG_BY_SUFFIX: dict[str, str] = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
}

_SUPPORTED_NODE_TYPES: dict[str, dict[str, str]] = {
    "javascript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "tsx": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type",
    },
    "rust": {
        "function_item": "function",
        "struct_item": "type",
        "enum_item": "type",
        "trait_item": "type",
    },
}


@dataclass(frozen=True)
class SymbolExtractionResult:
    defs: list[DefRef]
    backend_used: str


def _module_name_for_non_python(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    return rel.with_suffix("").as_posix().replace("/", ".")


def _decode_node_text(source: bytes, node: Any) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _node_name(source: bytes, node: Any) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        name = _decode_node_text(source, name_node).strip()
        if name:
            return name

    for child in getattr(node, "children", []):
        ctype = getattr(child, "type", "")
        if ctype in {
            "identifier",
            "property_identifier",
            "type_identifier",
            "field_identifier",
        }:
            name = _decode_node_text(source, child).strip()
            if name:
                return name
    return None


def _collect_defs_with_tree_sitter(
    *,
    path: Path,
    root: Path,
    text: str,
    language: str,
) -> list[DefRef]:
    try:
        tsl = importlib.import_module("tree_sitter_languages")
    except ModuleNotFoundError:
        return []

    get_parser = getattr(tsl, "get_parser", None)
    if not callable(get_parser):
        return []

    parser = cast(Any, get_parser(language))
    source = text.encode("utf-8")
    tree = parser.parse(source)
    node_kinds = _SUPPORTED_NODE_TYPES.get(language, {})
    module = _module_name_for_non_python(path, root)
    rel_path = path.resolve().relative_to(root.resolve())

    defs: list[DefRef] = []
    stack: list[Any] = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(reversed(getattr(node, "children", [])))

        kind = node_kinds.get(getattr(node, "type", ""))
        if kind is None:
            continue

        name = _node_name(source, node)
        if not name:
            continue

        start_row = int(getattr(node, "start_point", (0, 0))[0]) + 1
        end_row = int(getattr(node, "end_point", (start_row - 1, 0))[0]) + 1
        local_id = stable_location_id(rel_path, f"{kind}:{name}", start_row)
        defs.append(
            DefRef(
                path=path,
                module=module,
                qualname=name,
                id=local_id,
                local_id=local_id,
                kind=f"symbol_{kind}",
                decorator_start=start_row,
                def_line=start_row,
                body_start=min(start_row + 1, end_row),
                end_line=end_row,
                doc_start=None,
                doc_end=None,
                is_single_line=start_row == end_row,
            )
        )

    defs.sort(key=lambda d: (d.def_line, d.qualname))
    return defs


def extract_non_python_symbols(
    *,
    path: Path,
    root: Path,
    text: str,
    backend: str,
) -> SymbolExtractionResult:
    language = _LANG_BY_SUFFIX.get(path.suffix.lower())
    if language is None:
        return SymbolExtractionResult(defs=[], backend_used="none")

    mode = backend.strip().lower()
    if mode in {"none", "python"}:
        return SymbolExtractionResult(defs=[], backend_used="none")

    if mode in {"auto", "tree-sitter"}:
        defs = _collect_defs_with_tree_sitter(
            path=path,
            root=root,
            text=text,
            language=language,
        )
        if defs:
            return SymbolExtractionResult(defs=defs, backend_used="tree-sitter")
        return SymbolExtractionResult(defs=[], backend_used="none")

    return SymbolExtractionResult(defs=[], backend_used="none")
