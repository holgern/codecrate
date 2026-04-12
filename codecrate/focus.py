from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .analysis_metadata import build_entrypoints, build_import_edges, build_test_links
from .model import PackResult
from .options import PackOptions


@dataclass(frozen=True)
class FocusMatchDiagnostic:
    selector: str
    selector_kind: str
    matched_paths: tuple[str, ...] = ()
    missing: bool = False


@dataclass(frozen=True)
class FocusExpansionEdge:
    reason: str
    target_path: str
    source_path: str | None = None
    distance: int | None = None
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class InclusionReason:
    selected_by: tuple[str, ...]
    distance: int | None = None
    via: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "selected_by": list(self.selected_by),
            "via": list(self.via),
        }
        if self.distance is not None:
            payload["distance"] = self.distance
        return payload


@dataclass(frozen=True)
class FocusSelectionResult:
    selected_paths: tuple[str, ...]
    inclusion_reasons: dict[str, InclusionReason]
    expansion_graph: tuple[FocusExpansionEdge, ...] = ()
    match_diagnostics: tuple[FocusMatchDiagnostic, ...] = ()

    def repository_payload(self) -> dict[str, object]:
        return {
            "selected_file_count": len(self.selected_paths),
            "selected_paths": list(self.selected_paths),
            "match_diagnostics": [
                {
                    "selector": item.selector,
                    "selector_kind": item.selector_kind,
                    "matched_paths": list(item.matched_paths),
                    "missing": item.missing,
                }
                for item in self.match_diagnostics
            ],
            "expansion_graph": [
                {
                    "reason": edge.reason,
                    "target_path": edge.target_path,
                    "source_path": edge.source_path,
                    "distance": edge.distance,
                    "via": list(edge.via),
                }
                for edge in self.expansion_graph
            ],
        }


@dataclass
class _SelectionState:
    selected_paths: set[str] = field(default_factory=set)
    inclusion_reasons: dict[str, InclusionReason] = field(default_factory=dict)
    expansion_graph: list[FocusExpansionEdge] = field(default_factory=list)
    match_diagnostics: list[FocusMatchDiagnostic] = field(default_factory=list)

    def add(
        self,
        path: str,
        *,
        reason: str,
        source_path: str | None = None,
        distance: int | None = None,
        via: tuple[str, ...] = (),
    ) -> None:
        self.selected_paths.add(path)
        existing = self.inclusion_reasons.get(path)
        reason_names = set(existing.selected_by if existing is not None else ())
        reason_names.add(reason)
        via_values = sorted(set((existing.via if existing is not None else ()) + via))
        best_distance = _best_distance(
            existing.distance if existing is not None else None,
            distance,
        )
        self.inclusion_reasons[path] = InclusionReason(
            selected_by=tuple(sorted(reason_names)),
            distance=best_distance,
            via=tuple(via_values),
        )
        self.expansion_graph.append(
            FocusExpansionEdge(
                reason=reason,
                target_path=path,
                source_path=source_path,
                distance=distance,
                via=via,
            )
        )


def _best_distance(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _normalize_focus_path(raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return Path(value).as_posix()


def _resolve_focus_paths(
    pack: PackResult,
    options: PackOptions,
    state: _SelectionState,
) -> set[str]:
    available_paths = {
        file_pack.path.relative_to(pack.root).as_posix() for file_pack in pack.files
    }
    selected: set[str] = set()
    missing: list[str] = []

    for raw_path in options.focus_file:
        rel = _normalize_focus_path(raw_path)
        if rel in available_paths:
            selected.add(rel)
            state.add(
                rel,
                reason="focus_file",
                distance=0,
                via=(raw_path,),
            )
            state.match_diagnostics.append(
                FocusMatchDiagnostic(
                    selector=raw_path,
                    selector_kind="focus_file",
                    matched_paths=(rel,),
                )
            )
        else:
            missing.append(raw_path)
            state.match_diagnostics.append(
                FocusMatchDiagnostic(
                    selector=raw_path,
                    selector_kind="focus_file",
                    missing=True,
                )
            )

    for raw_symbol in options.focus_symbol:
        query = raw_symbol.strip()
        matched_paths: set[str] = set()
        if ":" in query:
            module, qualname = query.split(":", 1)
            for def_item in pack.defs:
                rel = def_item.path.relative_to(pack.root).as_posix()
                if def_item.module == module and def_item.qualname == qualname:
                    matched_paths.add(rel)
            for class_item in pack.classes:
                rel = class_item.path.relative_to(pack.root).as_posix()
                if class_item.module == module and class_item.qualname == qualname:
                    matched_paths.add(rel)
        else:
            for def_item in pack.defs:
                rel = def_item.path.relative_to(pack.root).as_posix()
                if def_item.qualname == query:
                    matched_paths.add(rel)
            for class_item in pack.classes:
                rel = class_item.path.relative_to(pack.root).as_posix()
                if class_item.qualname == query:
                    matched_paths.add(rel)
        if not matched_paths:
            missing.append(raw_symbol)
            state.match_diagnostics.append(
                FocusMatchDiagnostic(
                    selector=raw_symbol,
                    selector_kind="focus_symbol",
                    missing=True,
                )
            )
            continue
        for rel in sorted(matched_paths):
            selected.add(rel)
            state.add(
                rel,
                reason="focus_symbol",
                distance=0,
                via=(raw_symbol,),
            )
        state.match_diagnostics.append(
            FocusMatchDiagnostic(
                selector=raw_symbol,
                selector_kind="focus_symbol",
                matched_paths=tuple(sorted(matched_paths)),
            )
        )

    if missing:
        missing_text = ", ".join(f"`{item}`" for item in missing)
        raise ValueError(f"focus selectors matched no files for: {missing_text}")
    return selected


def _expand_import_neighbors(
    seed_paths: set[str],
    *,
    pack: PackResult,
    depth: int,
    state: _SelectionState,
) -> set[str]:
    if depth <= 0 or not seed_paths:
        return set(seed_paths)

    adjacency: dict[str, set[str]] = {}
    for edge in build_import_edges(pack):
        if edge.target_path is None:
            continue
        adjacency.setdefault(edge.source_path, set()).add(edge.target_path)
        adjacency.setdefault(edge.target_path, set()).add(edge.source_path)

    selected = set(seed_paths)
    distances = {path: 0 for path in seed_paths}
    queue = deque(sorted(seed_paths))
    while queue:
        current = queue.popleft()
        current_distance = distances[current]
        if current_distance >= depth:
            continue
        for target in sorted(adjacency.get(current, set())):
            next_distance = current_distance + 1
            if target not in distances or next_distance < distances[target]:
                distances[target] = next_distance
            if target not in selected:
                selected.add(target)
                queue.append(target)
            state.add(
                target,
                reason="import_neighbor",
                source_path=current,
                distance=next_distance,
                via=(current,),
            )
    return selected


def _expand_reverse_import_neighbors(
    seed_paths: set[str],
    *,
    pack: PackResult,
    depth: int,
    state: _SelectionState,
) -> set[str]:
    if depth <= 0 or not seed_paths:
        return set(seed_paths)

    reverse_adjacency: dict[str, set[str]] = {}
    for edge in build_import_edges(pack):
        if edge.target_path is None:
            continue
        reverse_adjacency.setdefault(edge.target_path, set()).add(edge.source_path)

    selected = set(seed_paths)
    distances = {path: 0 for path in seed_paths}
    queue = deque(sorted(seed_paths))
    while queue:
        current = queue.popleft()
        current_distance = distances[current]
        if current_distance >= depth:
            continue
        for target in sorted(reverse_adjacency.get(current, set())):
            next_distance = current_distance + 1
            if target not in distances or next_distance < distances[target]:
                distances[target] = next_distance
            if target not in selected:
                selected.add(target)
                queue.append(target)
            state.add(
                target,
                reason="reverse_import_neighbor",
                source_path=current,
                distance=next_distance,
                via=(current,),
            )
    return selected


def _include_same_package_neighbors(
    selected_paths: set[str],
    *,
    pack: PackResult,
    state: _SelectionState,
) -> set[str]:
    if not selected_paths:
        return set(selected_paths)

    package_by_path: dict[str, str] = {}
    groups: dict[str, set[str]] = {}
    for file_pack in pack.files:
        rel = file_pack.path.relative_to(pack.root).as_posix()
        package = file_pack.module.rsplit(".", 1)[0] if "." in file_pack.module else ""
        if file_pack.path.name == "__init__.py":
            package = file_pack.module
        package_by_path[rel] = package
        groups.setdefault(package, set()).add(rel)

    expanded = set(selected_paths)
    for path in sorted(selected_paths):
        for target in sorted(groups.get(package_by_path.get(path, ""), set()) - {path}):
            expanded.add(target)
            state.add(
                target,
                reason="same_package",
                source_path=path,
                distance=1,
                via=(path,),
            )
    return expanded


def _include_entrypoint_context(
    selected_paths: set[str],
    *,
    root: Path,
    pack: PackResult,
    state: _SelectionState,
) -> set[str]:
    if not selected_paths:
        return set(selected_paths)

    adjacency: dict[str, set[str]] = {}
    for edge in build_import_edges(pack):
        if edge.target_path is None:
            continue
        adjacency.setdefault(edge.source_path, set()).add(edge.target_path)

    entrypoints = build_entrypoints(root=root, pack=pack)
    expanded = set(selected_paths)
    targets = set(selected_paths)
    for entrypoint in entrypoints:
        frontier = [entrypoint]
        seen = {entrypoint}
        path_to_target: list[str] | None = None
        parents: dict[str, str | None] = {entrypoint: None}
        while frontier and path_to_target is None:
            current = frontier.pop()
            if current in targets:
                path_to_target = []
                cursor: str | None = current
                while cursor is not None:
                    path_to_target.append(cursor)
                    cursor = parents.get(cursor)
                path_to_target.reverse()
                break
            for target in sorted(adjacency.get(current, set())):
                if target in seen:
                    continue
                seen.add(target)
                parents[target] = current
                frontier.append(target)
        if path_to_target is not None:
            expanded.add(entrypoint)
            state.add(
                entrypoint,
                reason="entrypoint",
                source_path=path_to_target[-1] if path_to_target else None,
                distance=max(len(path_to_target) - 1, 0),
                via=tuple(path_to_target),
            )
    return expanded


def _include_related_tests(
    selected_paths: set[str],
    *,
    pack: PackResult,
    state: _SelectionState,
) -> set[str]:
    selected = set(selected_paths)
    for link in build_test_links(pack):
        if link.source_path not in selected:
            continue
        selected.add(link.test_path)
        state.add(
            link.test_path,
            reason="related_test",
            source_path=link.source_path,
            distance=1,
            via=(link.source_path, link.match_reason),
        )
    return selected


def _include_related_context(
    selected_paths: set[str],
    available_paths: set[str],
    state: _SelectionState,
) -> set[str]:
    selected = set(selected_paths)
    for candidate, reason in (
        ("pyproject.toml", "config_context"),
        ("codecrate.toml", "config_context"),
        (".codecrate.toml", "config_context"),
        ("README.md", "readme_context"),
        ("README.rst", "readme_context"),
    ):
        if candidate not in available_paths:
            continue
        selected.add(candidate)
        state.add(candidate, reason=reason, distance=1, via=(candidate,))
    return selected


def build_focus_selection(
    *,
    root: Path,
    pack: PackResult,
    options: PackOptions,
    available_paths: set[str],
) -> FocusSelectionResult:
    state = _SelectionState()
    if (
        not options.focus_file
        and not options.focus_symbol
        and options.include_import_neighbors <= 0
        and options.include_reverse_import_neighbors <= 0
        and not options.include_same_package
        and not options.include_entrypoints
        and not options.include_tests
    ):
        return FocusSelectionResult(
            selected_paths=tuple(sorted(available_paths)), inclusion_reasons={}
        )
    if not options.focus_file and not options.focus_symbol:
        raise ValueError(
            "focus expansion options require --focus-file or --focus-symbol"
        )

    selected_paths = _resolve_focus_paths(pack, options, state)
    selected_paths = _expand_import_neighbors(
        selected_paths,
        pack=pack,
        depth=options.include_import_neighbors,
        state=state,
    )
    selected_paths = _expand_reverse_import_neighbors(
        selected_paths,
        pack=pack,
        depth=options.include_reverse_import_neighbors,
        state=state,
    )
    if options.include_same_package:
        selected_paths = _include_same_package_neighbors(
            selected_paths,
            pack=pack,
            state=state,
        )
    if options.include_entrypoints:
        selected_paths = _include_entrypoint_context(
            selected_paths,
            root=root,
            pack=pack,
            state=state,
        )
    if options.include_tests:
        selected_paths = _include_related_tests(
            selected_paths,
            pack=pack,
            state=state,
        )
    selected_paths = _include_related_context(selected_paths, available_paths, state)
    if not selected_paths:
        raise ValueError("focus options produced an empty file set")
    return FocusSelectionResult(
        selected_paths=tuple(sorted(selected_paths)),
        inclusion_reasons=dict(sorted(state.inclusion_reasons.items())),
        expansion_graph=tuple(state.expansion_graph),
        match_diagnostics=tuple(state.match_diagnostics),
    )
