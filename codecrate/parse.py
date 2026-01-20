from __future__ import annotations

import ast
from pathlib import Path

from .ids import stable_location_id
from .model import DefRef


def module_name_for(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    parts = list(rel.parts)
    # Support common "src layout" even when scanning from repo root.
    # If you scan a repo root that contains src/codecrate/..., strip leading "src".
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class _DefVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, root: Path):
        self.path = path
        self.root = root
        self.module = module_name_for(path, root)
        self.stack: list[str] = []
        self.defs: list[DefRef] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add(node, kind="function")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add(node, kind="async_function")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _add(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name", "<anon>")
        qual = ".".join(self.stack + [name]) if self.stack else name

        decorator_start = int(getattr(node, "lineno", 1))
        decs = getattr(node, "decorator_list", []) or []
        for d in decs:
            if hasattr(d, "lineno"):
                decorator_start = min(decorator_start, int(d.lineno))

        def_line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", def_line))

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


def parse_defs(path: Path, root: Path, text: str) -> list[DefRef]:
    tree = ast.parse(text)
    v = _DefVisitor(path=path, root=root)
    v.visit(tree)
    return v.defs
