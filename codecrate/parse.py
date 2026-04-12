from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

from .ids import stable_location_id
from .model import ClassRef, DefRef, ImportRef, ParseResult


def module_name_for(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    parts = list(rel.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.root = root
        self.module = module_name_for(path, root)
        self.qual_stack: list[str] = []
        self.class_stack: list[str] = []
        self.defs: list[DefRef] = []
        self.classes: list[ClassRef] = []
        self.imports: list[ImportRef] = []
        self.exports: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_class(node)
        self.qual_stack.append(node.name)
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()
        self.qual_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_def(node, kind="function")
        self.qual_stack.append(node.name)
        self.generic_visit(node)
        self.qual_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_def(node, kind="async_function")
        self.qual_stack.append(node.name)
        self.generic_visit(node)
        self.qual_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        if not self.qual_stack:
            line = int(getattr(node, "lineno", 1))
            self.imports.extend(
                ImportRef(
                    module=alias.name,
                    imported_name=None,
                    alias=alias.asname,
                    line=line,
                    kind="import",
                )
                for alias in node.names
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not self.qual_stack:
            line = int(getattr(node, "lineno", 1))
            module = "." * int(getattr(node, "level", 0)) + (node.module or "")
            self.imports.extend(
                ImportRef(
                    module=module,
                    imported_name=alias.name,
                    alias=alias.asname,
                    line=line,
                    kind="from",
                )
                for alias in node.names
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self.qual_stack:
            exports = _assigned_exports(node)
            if exports is not None:
                self.exports = exports
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self.qual_stack:
            exports = _assigned_exports(node)
            if exports is not None:
                self.exports = exports
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if not self.qual_stack:
            exports = _augmented_exports(node)
            if exports:
                self.exports.extend(exports)
        self.generic_visit(node)

    def _decorator_start(self, node: ast.AST, default_line: int) -> int:
        start = default_line
        for d in getattr(node, "decorator_list", []) or []:
            if hasattr(d, "lineno"):
                start = min(start, int(d.lineno))
        return start

    def _add_class(self, node: ast.ClassDef) -> None:
        qual = (
            ".".join(self.qual_stack + [node.name]) if self.qual_stack else node.name
        )
        class_line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", class_line))
        decorator_start = self._decorator_start(node, class_line)

        rel_path = self.path.resolve().relative_to(self.root.resolve())
        cid = stable_location_id(rel_path, f"class:{qual}", class_line)

        self.classes.append(
            ClassRef(
                path=self.path,
                module=self.module,
                qualname=qual,
                id=cid,
                decorator_start=decorator_start,
                class_line=class_line,
                end_line=end_line,
                base_classes=_names_for_nodes(node.bases),
                decorators=_names_for_nodes(node.decorator_list),
            )
        )

    def _add_def(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name", "<anon>")
        qual = ".".join(self.qual_stack + [name]) if self.qual_stack else name

        def_line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", def_line))
        decorator_start = self._decorator_start(node, def_line)

        body = getattr(node, "body", []) or []
        body_start = def_line
        doc_start: int | None = None
        doc_end: int | None = None

        if body:
            body_start = int(getattr(body[0], "lineno", def_line))
            if (
                isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(getattr(body[0].value, "value", None), str)
            ):
                doc_start = int(getattr(body[0], "lineno", body_start))
                doc_end = int(getattr(body[0], "end_lineno", doc_start))
        else:
            body_start = end_line

        is_single_line = def_line == end_line

        rel_path = self.path.resolve().relative_to(self.root.resolve())
        local_id = stable_location_id(rel_path, qual, def_line)
        canonical_id = local_id

        self.defs.append(
            DefRef(
                path=self.path,
                module=self.module,
                qualname=qual,
                id=canonical_id,
                local_id=local_id,
                kind=kind,
                decorator_start=decorator_start,
                def_line=def_line,
                body_start=body_start,
                end_line=end_line,
                doc_start=doc_start,
                doc_end=doc_end,
                is_single_line=is_single_line,
                decorators=_names_for_nodes(getattr(node, "decorator_list", [])),
                owner_class=(
                    ".".join(self.class_stack) if self.class_stack else None
                ),
            )
        )


def _unparse_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def _names_for_nodes(nodes: Sequence[ast.AST]) -> list[str]:
    return [name for node in nodes if (name := _unparse_name(node))]


def _module_docstring_range(tree: ast.Module) -> tuple[int, int] | None:
    if not tree.body:
        return None
    first = tree.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(getattr(first, "value", None), ast.Constant)
        and isinstance(getattr(first.value, "value", None), str)
    ):
        start = int(getattr(first, "lineno", 1))
        end = int(getattr(first, "end_lineno", start))
        return (start, end)
    return None


def _string_literals(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for elt in node.elts:
            strings = _string_literals(elt)
            if strings is None:
                return None
            values.extend(strings)
        return values
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_literals(node.left)
        right = _string_literals(node.right)
        if left is None or right is None:
            return None
        return left + right
    return None


def _is_dunder_all(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Name) and node.id == "__all__"


def _assigned_exports(node: ast.Assign | ast.AnnAssign) -> list[str] | None:
    if isinstance(node, ast.Assign):
        if not any(_is_dunder_all(target) for target in node.targets):
            return None
        return _string_literals(node.value)
    if not _is_dunder_all(node.target) or node.value is None:
        return None
    return _string_literals(node.value)


def _augmented_exports(node: ast.AugAssign) -> list[str] | None:
    if not _is_dunder_all(node.target) or not isinstance(node.op, ast.Add):
        return None
    return _string_literals(node.value)


def parse_symbols(path: Path, root: Path, text: str) -> ParseResult:
    # Pass filename so SyntaxWarnings (e.g. invalid escape sequences) point to
    # the real file instead of "<unknown>".
    tree = ast.parse(text, filename=path.as_posix())
    v = _Visitor(path=path, root=root)
    v.visit(tree)
    return ParseResult(
        module=v.module,
        classes=v.classes,
        defs=v.defs,
        imports=v.imports,
        exports=v.exports,
        module_docstring=_module_docstring_range(tree),
    )
