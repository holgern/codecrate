from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from typing import Any

from .model import ClassRef, DefRef, FilePack, PackResult

_BUILTIN_NAMES = frozenset(dir(builtins))


@dataclass(frozen=True)
class ReferenceEdge:
    source_local_id: str
    source_path: str
    target_local_id: str
    target_path: str
    target_qualname: str
    line: int
    kind: str


@dataclass(frozen=True)
class CallLikeEdge:
    source_local_id: str
    source_path: str
    target_local_id: str
    target_path: str
    target_qualname: str
    line: int
    expression: str


@dataclass(frozen=True)
class ReferenceAnalysis:
    reference_edges: tuple[ReferenceEdge, ...]
    call_like_edges: tuple[CallLikeEdge, ...]
    file_references_out: dict[str, list[str]]
    file_references_in: dict[str, list[str]]
    symbol_references_out: dict[str, list[str]]
    symbol_references_in: dict[str, list[str]]
    unresolved_references_by_file: dict[str, int]
    unresolved_references_by_symbol: dict[str, int]


@dataclass(frozen=True)
class _ResolvedTarget:
    target_local_id: str
    target_path: str
    target_qualname: str


@dataclass(frozen=True)
class _ModuleAlias:
    module_name: str
    target_path: str | None


@dataclass(frozen=True)
class _ClassTarget:
    path: str
    qualname: str


@dataclass
class _Indexes:
    defs_by_path_qualname: dict[tuple[str, str], DefRef] = field(default_factory=dict)
    classes_by_path_qualname: dict[tuple[str, str], ClassRef] = field(
        default_factory=dict
    )
    module_paths: dict[str, str] = field(default_factory=dict)
    top_level_defs_by_path: dict[str, dict[str, DefRef]] = field(default_factory=dict)
    top_level_classes_by_path: dict[str, dict[str, ClassRef]] = field(
        default_factory=dict
    )
    methods_by_path_class: dict[tuple[str, str], dict[str, DefRef]] = field(
        default_factory=dict
    )


class _ReferenceVisitor(ast.NodeVisitor):
    def __init__(self, file_pack: FilePack, indexes: _Indexes) -> None:
        self.file_pack = file_pack
        self.path = file_pack.path.as_posix()
        self.indexes = indexes
        self.scope_stack: list[set[str]] = [set()]
        self.import_stack: list[
            dict[str, _ModuleAlias | _ResolvedTarget | _ClassTarget]
        ] = [{}]
        self.qual_stack: list[str] = []
        self.class_stack: list[str] = []
        self.current_symbol_local_id: str | None = None
        self.reference_edges: dict[tuple[str, str, int, str], ReferenceEdge] = {}
        self.call_like_edges: dict[tuple[str, str, int], CallLikeEdge] = {}
        self.unresolved_references_by_symbol: dict[str, int] = {}
        self.unresolved_references_by_file = 0

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack[-1].add(node.name)
        self.qual_stack.append(node.name)
        self.class_stack.append(".".join(self.qual_stack))
        self.scope_stack.append(set())
        self.import_stack.append(dict(self.import_stack[-1]))
        self.generic_visit(node)
        self.import_stack.pop()
        self.scope_stack.pop()
        self.class_stack.pop()
        self.qual_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Import(self, node: ast.Import) -> None:
        aliases = self.import_stack[-1]
        for alias in node.names:
            bound_name = alias.asname or alias.name.split(".", 1)[0]
            target_path = self.indexes.module_paths.get(alias.name)
            aliases[bound_name] = _ModuleAlias(alias.name, target_path)
            self.scope_stack[-1].add(bound_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module_name = "." * int(getattr(node, "level", 0)) + (node.module or "")
        resolved_module_name = _resolve_relative_module(
            self.file_pack.module,
            module_name,
        )
        aliases = self.import_stack[-1]
        for alias in node.names:
            if alias.name == "*":
                continue
            bound_name = alias.asname or alias.name
            resolved_target = _resolve_import_target(
                indexes=self.indexes,
                resolved_module_name=resolved_module_name,
                imported_name=alias.name,
            )
            aliases[bound_name] = resolved_target
            self.scope_stack[-1].add(bound_name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._bind_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self._bind_target(node.target)
        if node.annotation is not None:
            self.visit(node.annotation)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self.visit(node.target)
        self._bind_target(node.target)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self._bind_target(node.target)
        for child in node.body:
            self.visit(child)
        for child in node.orelse:
            self.visit(child)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.iter)
        self._bind_target(node.target)
        for child in node.body:
            self.visit(child)
        for child in node.orelse:
            self.visit(child)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars)
        for child in node.body:
            self.visit(child)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars)
        for child in node.body:
            self.visit(child)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record_reference(node, kind="name")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record_reference(node, kind="attribute")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._record_call(node)
        self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack[-1].add(node.name)
        self.qual_stack.append(node.name)
        current_qualname = ".".join(self.qual_stack)
        def_ref = self.indexes.defs_by_path_qualname.get((self.path, current_qualname))
        previous_symbol = self.current_symbol_local_id
        self.current_symbol_local_id = def_ref.local_id if def_ref is not None else None
        self.scope_stack.append(set(_parameter_names(node.args)))
        self.import_stack.append(dict(self.import_stack[-1]))
        self.generic_visit(node)
        self.import_stack.pop()
        self.scope_stack.pop()
        self.current_symbol_local_id = previous_symbol
        self.qual_stack.pop()

    def _visit_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp,
    ) -> None:
        self.scope_stack.append(set())
        self.import_stack.append(dict(self.import_stack[-1]))
        for generator in node.generators:
            self.visit(generator.iter)
            self._bind_target(generator.target)
            for if_clause in generator.ifs:
                self.visit(if_clause)
        for field_name in ("elt", "key", "value"):
            value = getattr(node, field_name, None)
            if value is not None:
                self.visit(value)
        self.import_stack.pop()
        self.scope_stack.pop()

    def _bind_target(self, node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            self.scope_stack[-1].add(node.id)
            return
        if isinstance(node, ast.Starred):
            self._bind_target(node.value)
            return
        if isinstance(node, ast.Tuple | ast.List):
            for child in node.elts:
                self._bind_target(child)

    def _record_reference(self, node: ast.Name | ast.Attribute, *, kind: str) -> None:
        if self.current_symbol_local_id is None:
            return
        resolved = self._resolve_expr(node)
        if resolved is None:
            if kind == "attribute" or self._should_count_unresolved_name(node):
                self._count_unresolved()
            return
        edge = ReferenceEdge(
            source_local_id=self.current_symbol_local_id,
            source_path=self.path,
            target_local_id=resolved.target_local_id,
            target_path=resolved.target_path,
            target_qualname=resolved.target_qualname,
            line=int(getattr(node, "lineno", 1)),
            kind=kind,
        )
        self.reference_edges[
            (
                edge.source_local_id,
                edge.target_local_id,
                edge.line,
                edge.kind,
            )
        ] = edge

    def _record_call(self, node: ast.Call) -> None:
        if self.current_symbol_local_id is None:
            return
        resolved = self._resolve_expr(node.func)
        if resolved is None:
            self._count_unresolved()
            return
        expression = _safe_unparse(node.func)
        edge = CallLikeEdge(
            source_local_id=self.current_symbol_local_id,
            source_path=self.path,
            target_local_id=resolved.target_local_id,
            target_path=resolved.target_path,
            target_qualname=resolved.target_qualname,
            line=int(getattr(node, "lineno", 1)),
            expression=expression,
        )
        self.call_like_edges[
            (edge.source_local_id, edge.target_local_id, edge.line)
        ] = edge

    def _count_unresolved(self) -> None:
        if self.current_symbol_local_id is None:
            return
        self.unresolved_references_by_file += 1
        self.unresolved_references_by_symbol[self.current_symbol_local_id] = (
            self.unresolved_references_by_symbol.get(self.current_symbol_local_id, 0)
            + 1
        )

    def _should_count_unresolved_name(self, node: ast.Name | ast.Attribute) -> bool:
        if isinstance(node, ast.Name):
            name = node.id
            if name in _BUILTIN_NAMES:
                return False
            return not self._is_locally_bound(name)
        chain = _attribute_chain(node)
        return bool(chain)

    def _is_locally_bound(self, name: str) -> bool:
        return any(name in scope for scope in reversed(self.scope_stack))

    def _resolve_expr(self, node: ast.AST) -> _ResolvedTarget | None:
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        chain = _attribute_chain(node)
        if not chain:
            return None
        return self._resolve_chain(chain)

    def _resolve_name(self, name: str) -> _ResolvedTarget | None:
        if self._is_locally_bound(name) and name not in self.import_stack[-1]:
            return None
        alias_target = self.import_stack[-1].get(name)
        if isinstance(alias_target, _ResolvedTarget):
            return alias_target
        if isinstance(alias_target, _ClassTarget):
            return None
        top_level_def = self.indexes.top_level_defs_by_path.get(self.path, {}).get(name)
        if top_level_def is not None:
            return _ResolvedTarget(
                target_local_id=top_level_def.local_id,
                target_path=self.path,
                target_qualname=top_level_def.qualname,
            )
        return None

    def _resolve_chain(self, chain: list[str]) -> _ResolvedTarget | None:
        if not chain:
            return None
        base_name = chain[0]
        if base_name in {"self", "cls"} and self.class_stack:
            current_class = self.class_stack[-1]
            methods = self.indexes.methods_by_path_class.get(
                (self.path, current_class), {}
            )
            if len(chain) >= 2:
                method = methods.get(chain[1])
                if method is not None:
                    return _ResolvedTarget(
                        target_local_id=method.local_id,
                        target_path=self.path,
                        target_qualname=method.qualname,
                    )
            return None

        alias_target = self.import_stack[-1].get(base_name)
        if isinstance(alias_target, _ResolvedTarget):
            return alias_target if len(chain) == 1 else None
        if isinstance(alias_target, _ClassTarget):
            return _resolve_class_chain(
                self.indexes, alias_target.path, alias_target.qualname, chain[1:]
            )
        if isinstance(alias_target, _ModuleAlias):
            return _resolve_module_chain(self.indexes, alias_target, chain[1:])

        top_level_class = self.indexes.top_level_classes_by_path.get(self.path, {}).get(
            base_name
        )
        if top_level_class is not None:
            return _resolve_class_chain(
                self.indexes,
                self.path,
                top_level_class.qualname,
                chain[1:],
            )
        return None


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def _attribute_chain(node: ast.AST) -> list[str] | None:
    chain: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        chain.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        chain.append(current.id)
        chain.reverse()
        return chain
    return None


def _parameter_names(arguments: ast.arguments) -> set[str]:
    names = {
        arg.arg for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs
    }
    if arguments.vararg is not None:
        names.add(arguments.vararg.arg)
    if arguments.kwarg is not None:
        names.add(arguments.kwarg.arg)
    return names


def _resolve_relative_module(current_module: str, module_name: str) -> str | None:
    if not module_name:
        return None
    if not module_name.startswith("."):
        return module_name
    level = len(module_name) - len(module_name.lstrip("."))
    remainder = module_name[level:]
    package_parts = [part for part in current_module.split(".") if part]
    trim = max(level - 1, 0)
    if trim:
        if trim >= len(package_parts):
            package_parts = []
        else:
            package_parts = package_parts[:-trim]
    resolved_parts = package_parts + ([remainder] if remainder else [])
    return ".".join(part for part in resolved_parts if part) or None


def _resolve_import_target(
    *,
    indexes: _Indexes,
    resolved_module_name: str | None,
    imported_name: str,
) -> _ModuleAlias | _ResolvedTarget | _ClassTarget:
    if resolved_module_name:
        module_path = indexes.module_paths.get(
            f"{resolved_module_name}.{imported_name}"
        )
        if module_path is not None:
            return _ModuleAlias(f"{resolved_module_name}.{imported_name}", module_path)
        source_path = indexes.module_paths.get(resolved_module_name)
        if source_path is not None:
            top_def = indexes.top_level_defs_by_path.get(source_path, {}).get(
                imported_name
            )
            if top_def is not None:
                return _ResolvedTarget(
                    target_local_id=top_def.local_id,
                    target_path=source_path,
                    target_qualname=top_def.qualname,
                )
            top_class = indexes.top_level_classes_by_path.get(source_path, {}).get(
                imported_name
            )
            if top_class is not None:
                return _ClassTarget(path=source_path, qualname=top_class.qualname)
    return _ModuleAlias(imported_name, indexes.module_paths.get(imported_name))


def _resolve_class_chain(
    indexes: _Indexes,
    path: str,
    class_qualname: str,
    attrs: list[str],
) -> _ResolvedTarget | None:
    if not attrs:
        return None
    methods = indexes.methods_by_path_class.get((path, class_qualname), {})
    target = methods.get(attrs[0])
    if target is None:
        return None
    return _ResolvedTarget(
        target_local_id=target.local_id,
        target_path=path,
        target_qualname=target.qualname,
    )


def _resolve_module_chain(
    indexes: _Indexes,
    alias_target: _ModuleAlias,
    attrs: list[str],
) -> _ResolvedTarget | None:
    if alias_target.target_path is None:
        return None
    if not attrs:
        return None
    current_module_name = alias_target.module_name
    current_path = alias_target.target_path
    for index, attr in enumerate(attrs):
        nested_module_name = f"{current_module_name}.{attr}"
        nested_path = indexes.module_paths.get(nested_module_name)
        if nested_path is not None:
            current_module_name = nested_module_name
            current_path = nested_path
            continue
        top_def = indexes.top_level_defs_by_path.get(current_path, {}).get(attr)
        if top_def is not None:
            if index != len(attrs) - 1:
                return None
            return _ResolvedTarget(
                target_local_id=top_def.local_id,
                target_path=current_path,
                target_qualname=top_def.qualname,
            )
        top_class = indexes.top_level_classes_by_path.get(current_path, {}).get(attr)
        if top_class is not None:
            return _resolve_class_chain(
                indexes, current_path, top_class.qualname, attrs[index + 1 :]
            )
        return None
    return None


def _build_indexes(pack: PackResult) -> _Indexes:
    indexes = _Indexes()
    for file_pack in pack.files:
        rel_path = file_pack.path.relative_to(pack.root).as_posix()
        if file_pack.module:
            indexes.module_paths[file_pack.module] = rel_path
        indexes.top_level_defs_by_path[rel_path] = {
            defn.qualname: defn for defn in file_pack.defs if "." not in defn.qualname
        }
        indexes.top_level_classes_by_path[rel_path] = {
            class_ref.qualname: class_ref
            for class_ref in file_pack.classes
            if "." not in class_ref.qualname
        }
        for defn in file_pack.defs:
            indexes.defs_by_path_qualname[(rel_path, defn.qualname)] = defn
            if defn.owner_class:
                key = (rel_path, defn.owner_class)
                indexes.methods_by_path_class.setdefault(key, {})[
                    defn.qualname.rsplit(".", 1)[-1]
                ] = defn
        for class_ref in file_pack.classes:
            indexes.classes_by_path_qualname[(rel_path, class_ref.qualname)] = class_ref
    return indexes


def analyze_references(pack: PackResult) -> ReferenceAnalysis:
    indexes = _build_indexes(pack)
    reference_edges: list[ReferenceEdge] = []
    call_like_edges: list[CallLikeEdge] = []
    unresolved_by_file: dict[str, int] = {}
    unresolved_by_symbol: dict[str, int] = {}
    for file_pack in pack.files:
        rel_path = file_pack.path.relative_to(pack.root).as_posix()
        if file_pack.path.suffix.lower() != ".py":
            unresolved_by_file.setdefault(rel_path, 0)
            continue
        try:
            tree = ast.parse(
                file_pack.original_text, filename=file_pack.path.as_posix()
            )
        except SyntaxError:
            unresolved_by_file.setdefault(rel_path, 0)
            continue
        visitor = _ReferenceVisitor(file_pack, indexes)
        visitor.path = rel_path
        visitor.visit(tree)
        reference_edges.extend(visitor.reference_edges.values())
        call_like_edges.extend(visitor.call_like_edges.values())
        unresolved_by_file[rel_path] = visitor.unresolved_references_by_file
        unresolved_by_symbol.update(visitor.unresolved_references_by_symbol)

    reference_edges = sorted(
        reference_edges,
        key=lambda item: (
            item.source_path,
            item.source_local_id,
            item.line,
            item.target_path,
            item.target_local_id,
        ),
    )
    call_like_edges = sorted(
        call_like_edges,
        key=lambda item: (
            item.source_path,
            item.source_local_id,
            item.line,
            item.target_path,
            item.target_local_id,
        ),
    )
    file_references_out: dict[str, list[str]] = {}
    file_references_in: dict[str, list[str]] = {}
    symbol_references_out: dict[str, list[str]] = {}
    symbol_references_in: dict[str, list[str]] = {}
    for edge in reference_edges:
        file_references_out.setdefault(edge.source_path, []).append(edge.target_path)
        file_references_in.setdefault(edge.target_path, []).append(edge.source_path)
        symbol_references_out.setdefault(edge.source_local_id, []).append(
            edge.target_local_id
        )
        symbol_references_in.setdefault(edge.target_local_id, []).append(
            edge.source_local_id
        )

    return ReferenceAnalysis(
        reference_edges=tuple(reference_edges),
        call_like_edges=tuple(call_like_edges),
        file_references_out={
            key: sorted(set(values))
            for key, values in sorted(file_references_out.items())
        },
        file_references_in={
            key: sorted(set(values))
            for key, values in sorted(file_references_in.items())
        },
        symbol_references_out={
            key: sorted(set(values))
            for key, values in sorted(symbol_references_out.items())
        },
        symbol_references_in={
            key: sorted(set(values))
            for key, values in sorted(symbol_references_in.items())
        },
        unresolved_references_by_file={
            key: unresolved_by_file.get(key, 0)
            for key in sorted(
                file_pack.path.relative_to(pack.root).as_posix()
                for file_pack in pack.files
            )
        },
        unresolved_references_by_symbol={
            defn.local_id: unresolved_by_symbol.get(defn.local_id, 0)
            for defn in sorted(
                pack.defs,
                key=lambda item: (
                    item.path.relative_to(pack.root).as_posix(),
                    item.def_line,
                    item.qualname,
                ),
            )
        },
    )


def call_like_edges_payload(analysis: ReferenceAnalysis) -> list[dict[str, Any]]:
    return [
        {
            "source_local_id": edge.source_local_id,
            "source_path": edge.source_path,
            "target_local_id": edge.target_local_id,
            "target_path": edge.target_path,
            "target_qualname": edge.target_qualname,
            "line": edge.line,
            "expression": edge.expression,
        }
        for edge in analysis.call_like_edges
    ]
