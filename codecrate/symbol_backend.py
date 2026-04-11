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
    ".java": "java",
    ".cs": "c_sharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
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
    "java": {
        "class_declaration": "class",
        "interface_declaration": "type",
        "enum_declaration": "type",
        "record_declaration": "type",
        "method_declaration": "method",
        "constructor_declaration": "method",
    },
    "c_sharp": {
        "class_declaration": "class",
        "struct_declaration": "type",
        "interface_declaration": "type",
        "enum_declaration": "type",
        "record_declaration": "type",
        "method_declaration": "method",
        "constructor_declaration": "method",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "type",
        "enum_specifier": "type",
        "union_specifier": "type",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "type",
        "enum_specifier": "type",
        "namespace_definition": "type",
    },
    "ruby": {
        "method": "method",
        "singleton_method": "method",
        "class": "class",
        "module": "type",
    },
    "php": {
        "function_definition": "function",
        "method_declaration": "method",
        "class_declaration": "class",
        "interface_declaration": "type",
        "trait_declaration": "type",
        "enum_declaration": "type",
    },
    "kotlin": {
        "function_declaration": "function",
        "class_declaration": "class",
        "object_declaration": "type",
        "interface_declaration": "type",
        "secondary_constructor": "method",
    },
}


@dataclass(frozen=True)
class SymbolExtractionResult:
    defs: list[DefRef]
    backend_requested: str
    backend_used: str
    language_detected: str
    extraction_status: str


def detect_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    return _LANG_BY_SUFFIX.get(suffix, "unknown")


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

    for field_name in {"declarator", "declaration", "body"}:
        child = node.child_by_field_name(field_name)
        if child is None:
            continue
        child_name = _node_name(source, child)
        if child_name:
            return child_name

    for child in getattr(node, "children", []):
        ctype = getattr(child, "type", "")
        if ctype in {
            "identifier",
            "property_identifier",
            "type_identifier",
            "field_identifier",
            "namespace_identifier",
            "name",
        }:
            child_name = _decode_node_text(source, child).strip()
            if child_name:
                return child_name
    return None


def _collect_defs_with_tree_sitter(
    *,
    path: Path,
    root: Path,
    text: str,
    language: str,
) -> tuple[list[DefRef], str]:
    try:
        tsl = importlib.import_module("tree_sitter_languages")
    except ModuleNotFoundError:
        return [], "backend-unavailable"

    get_parser = getattr(tsl, "get_parser", None)
    if not callable(get_parser):
        return [], "backend-unavailable"

    try:
        parser = cast(Any, get_parser(language))
    except Exception:
        return [], "backend-unavailable"

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
    return defs, "ok" if defs else "no-symbols"


def extract_non_python_symbols(
    *,
    path: Path,
    root: Path,
    text: str,
    backend: str,
) -> SymbolExtractionResult:
    requested = backend.strip().lower()
    language = detect_language(path)
    if language == "unknown":
        return SymbolExtractionResult(
            defs=[],
            backend_requested=requested,
            backend_used="none",
            language_detected=language,
            extraction_status="unsupported-language",
        )

    if requested in {"none", "python"}:
        return SymbolExtractionResult(
            defs=[],
            backend_requested=requested,
            backend_used="none",
            language_detected=language,
            extraction_status="disabled",
        )

    if requested in {"auto", "tree-sitter"}:
        defs, status = _collect_defs_with_tree_sitter(
            path=path,
            root=root,
            text=text,
            language=language,
        )
        return SymbolExtractionResult(
            defs=defs,
            backend_requested=requested,
            backend_used="tree-sitter" if status != "backend-unavailable" else "none",
            language_detected=language,
            extraction_status=status,
        )

    return SymbolExtractionResult(
        defs=[],
        backend_requested=requested,
        backend_used="none",
        language_detected=language,
        extraction_status="disabled",
    )
