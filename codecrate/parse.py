from __future__ import annotations

import ast
from pathlib import Path

from .ids import stable_location_id
from .model import ClassRef, DefRef


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
        self.stack: list[str] = []
        self.defs: list[DefRef] = []
        self.classes: list[ClassRef] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_class(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_def(node, kind="function")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_def(node, kind="async_function")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _decorator_start(self, node: ast.AST, default_line: int) -> int:
        start = default_line
        for d in getattr(node, "decorator_list", []) or []:
            if hasattr(d, "lineno"):
                start = min(start, int(d.lineno))
        return start

    def _add_class(self, node: ast.ClassDef) -> None:
        qual = ".".join(self.stack + [node.name]) if self.stack else node.name
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
            )
        )

    def _add_def(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name", "<anon>")
        qual = ".".join(self.stack + [name]) if self.stack else name

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
            )
        )


def parse_symbols(
    path: Path, root: Path, text: str
) -> tuple[list[ClassRef], list[DefRef]]:
    # Pass filename so SyntaxWarnings (e.g. invalid escape sequences) point to
    # the real file instead of "<unknown>".
    tree = ast.parse(text, filename=path.as_posix())
    v = _Visitor(path=path, root=root)
    v.visit(tree)
    return v.classes, v.defs
