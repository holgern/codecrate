from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import ClassRef, DefRef, FilePack, ImportRef, PackResult

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

_CONFIG_FILES = {
    "pyproject.toml",
    "codecrate.toml",
    ".codecrate.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-test.txt",
    ".pre-commit-config.yaml",
}
_IO_IMPORT_HINTS = {
    "io",
    "json",
    "os",
    "pathlib",
    "shutil",
    "subprocess",
    "tempfile",
}
_SUMMARY_LIMIT = 5


@dataclass(frozen=True)
class ImportEdge:
    source_path: str
    kind: str
    import_module: str
    resolved_module: str | None
    imported_name: str | None
    alias: str | None
    line: int
    target_module: str | None
    target_path: str | None


@dataclass(frozen=True)
class TestLink:
    source_path: str
    test_path: str
    match_reason: str
    score: int = 0
    link_kind: str = "heuristic"
    evidence: tuple[str, ...] = ()


def _rel_path(pack: PackResult, file_pack: FilePack) -> str:
    return file_pack.path.relative_to(pack.root).as_posix()


def _module_to_path(pack: PackResult) -> dict[str, str]:
    out: dict[str, str] = {}
    for file_pack in pack.files:
        if not file_pack.module:
            continue
        out.setdefault(file_pack.module, _rel_path(pack, file_pack))
    return out


def role_hint_for_file(path: str) -> str | None:
    rel = Path(path)
    parts = rel.parts
    name = rel.name
    stem = rel.stem.lower()
    suffix = rel.suffix.lower()

    if name == "__main__.py":
        return "entrypoint"
    if name == "__init__.py":
        return "package-init"
    if parts[:1] == (".github",) or path in _CONFIG_FILES:
        return "config"
    if parts[:1] == ("docs",):
        if name == "conf.py":
            return "docs-config"
        return "docs"
    if suffix in {".md", ".rst"}:
        return "docs"
    if (
        parts[:1] == ("tests",)
        or "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        if "fixtures" in parts or "fixture" in stem:
            return "test-fixture"
        return "test"
    if name.startswith("cli") and suffix == ".py":
        return "cli-front-end"
    if stem in {"formats", "format"} or "format" in stem or "index_json" in stem:
        return "format-definition"
    if stem.startswith("validate") or "validator" in stem or "schema" in stem:
        return "schema-validator"
    if "serial" in stem or stem in {"manifest"}:
        return "serializer"
    if stem in {"unpack", "parse"} or "deserial" in stem:
        return "deserializer"
    if "pipeline" in stem or stem in {"packer"}:
        return "pipeline-orchestrator"
    if "security" in stem or "safety" in stem:
        return "security-layer"
    if "token" in stem or "budget" in stem:
        return "token-budgeting"
    if "diff" in stem or "patch" in stem or "apply" in stem:
        return "diff-engine"
    return None


def _package_context(file_pack: FilePack) -> str:
    module = file_pack.module
    if not module:
        return ""
    if file_pack.path.name == "__init__.py":
        return module
    if "." not in module:
        return ""
    return module.rsplit(".", 1)[0]


def _summary_label(values: list[str], *, limit: int = 3) -> str:
    return ", ".join(values[:limit])


def build_file_summary_text(
    *,
    role: str | None,
    primary_symbols: list[str],
    exports: list[str],
    touches_io: bool,
    is_test: bool,
) -> str:
    parts: list[str] = []
    if role:
        parts.append(f"{role.replace('-', ' ')} file")
    elif is_test:
        parts.append("test file")
    else:
        parts.append("source file")
    if primary_symbols:
        parts.append(f"primary symbols: {_summary_label(primary_symbols)}")
    if exports:
        parts.append(f"exports: {_summary_label(exports)}")
    if touches_io:
        parts.append("touches I/O")
    return "; ".join(parts)


def build_symbol_purpose_text(defn: DefRef) -> str:
    parts: list[str] = []
    visibility = "public" if defn.is_public else "private"
    if defn.is_property:
        kind = "property"
    elif defn.is_classmethod:
        kind = "classmethod"
    elif defn.is_staticmethod:
        kind = "staticmethod"
    elif defn.is_method:
        kind = "method"
    else:
        kind = defn.kind
    if defn.is_coroutine:
        kind = f"async {kind}"
    if defn.owner_class:
        parts.append(f"{visibility} {kind} on {defn.owner_class}")
    else:
        parts.append(f"{visibility} {kind}")
    if defn.return_annotation:
        parts.append(f"returns {defn.return_annotation}")
    elif defn.is_generator:
        parts.append("yields values")
    parameter_names = [
        parameter.name
        for parameter in defn.parameters
        if parameter.name not in {"self", "cls"}
    ]
    if parameter_names:
        parts.append(f"params: {_summary_label(parameter_names)}")
    return "; ".join(parts)


def build_class_purpose_text(class_ref: ClassRef) -> str:
    parts = ["public class" if class_ref.is_public else "private class"]
    if class_ref.base_classes:
        parts.append(f"bases: {_summary_label(class_ref.base_classes)}")
    if class_ref.decorators:
        parts.append(f"decorators: {_summary_label(class_ref.decorators)}")
    return "; ".join(parts)


def resolve_import_module(file_pack: FilePack, import_ref: ImportRef) -> str | None:
    module = import_ref.module
    if not module:
        return None
    if not module.startswith("."):
        return module

    level = len(module) - len(module.lstrip("."))
    remainder = module[level:]
    package_parts = [part for part in _package_context(file_pack).split(".") if part]
    trim = max(level - 1, 0)
    if trim:
        if trim >= len(package_parts):
            package_parts = []
        else:
            package_parts = package_parts[:-trim]
    resolved_parts = package_parts + ([remainder] if remainder else [])
    resolved = ".".join(part for part in resolved_parts if part)
    return resolved or None


def _best_local_module(
    module: str | None, module_to_path: dict[str, str]
) -> str | None:
    if not module:
        return None
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in module_to_path:
            return candidate
    return None


def _target_for_import(
    file_pack: FilePack,
    import_ref: ImportRef,
    module_to_path: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    resolved_module = resolve_import_module(file_pack, import_ref)
    target_module: str | None = None

    if import_ref.kind == "from":
        if import_ref.imported_name and import_ref.imported_name != "*":
            target_module = _best_local_module(
                (
                    f"{resolved_module}.{import_ref.imported_name}"
                    if resolved_module
                    else import_ref.imported_name
                ),
                module_to_path,
            )
        if target_module is None:
            target_module = _best_local_module(resolved_module, module_to_path)
    else:
        target_module = _best_local_module(resolved_module, module_to_path)

    return resolved_module, target_module, module_to_path.get(target_module or "")


def build_import_edges(pack: PackResult) -> list[ImportEdge]:
    module_to_path = _module_to_path(pack)
    edges: list[ImportEdge] = []
    for file_pack in pack.files:
        source_path = _rel_path(pack, file_pack)
        for import_ref in file_pack.imports:
            resolved_module, target_module, target_path = _target_for_import(
                file_pack,
                import_ref,
                module_to_path,
            )
            edges.append(
                ImportEdge(
                    source_path=source_path,
                    kind=import_ref.kind,
                    import_module=import_ref.module,
                    resolved_module=resolved_module,
                    imported_name=import_ref.imported_name,
                    alias=import_ref.alias,
                    line=import_ref.line,
                    target_module=target_module,
                    target_path=target_path or None,
                )
            )
    return edges


def _normalized_test_tokens(path: str) -> tuple[str, ...]:
    rel = Path(path)
    tokens: list[str] = []
    for part in rel.with_suffix("").parts:
        token = part.lower()
        if token in {"tests", "test"}:
            continue
        if token == "__init__":
            continue
        if token.startswith("test_"):
            token = token[5:]
        if token.endswith("_test"):
            token = token[:-5]
        if token:
            tokens.append(token)
    return tuple(tokens)


def _shared_package_depth(source_path: str, test_path: str) -> int:
    source_parts = [
        part
        for part in Path(source_path).with_suffix("").parts[:-1]
        if part not in {"tests", "test"}
    ]
    test_parts = [
        part
        for part in Path(test_path).with_suffix("").parts[:-1]
        if part not in {"tests", "test"}
    ]
    depth = 0
    for left, right in zip(source_parts, test_parts, strict=False):
        if left != right:
            break
        depth += 1
    return depth


def _store_test_link(
    links: dict[tuple[str, str], TestLink],
    *,
    source_path: str,
    test_path: str,
    match_reason: str,
    score: int,
    link_kind: str,
    evidence: list[str],
) -> None:
    key = (source_path, test_path)
    evidence_tuple = tuple(sorted(set(item for item in evidence if item)))
    candidate = TestLink(
        source_path=source_path,
        test_path=test_path,
        match_reason=match_reason,
        score=score,
        link_kind=link_kind,
        evidence=evidence_tuple,
    )
    existing = links.get(key)
    if existing is None:
        links[key] = candidate
        return
    if candidate.score > existing.score:
        links[key] = candidate
        return
    if candidate.score == existing.score:
        links[key] = TestLink(
            source_path=existing.source_path,
            test_path=existing.test_path,
            match_reason=existing.match_reason,
            score=existing.score,
            link_kind=existing.link_kind,
            evidence=tuple(sorted(set(existing.evidence) | set(candidate.evidence))),
        )


def build_test_links(pack: PackResult) -> list[TestLink]:
    role_hints = {
        _rel_path(pack, file_pack): role_hint_for_file(_rel_path(pack, file_pack))
        for file_pack in pack.files
    }
    edges = build_import_edges(pack)
    source_paths = [
        path for path, hint in role_hints.items() if hint not in {"test", "docs"}
    ]
    test_paths = [path for path, hint in role_hints.items() if hint == "test"]

    links: dict[tuple[str, str], TestLink] = {}
    for edge in edges:
        if edge.source_path not in test_paths or edge.target_path is None:
            continue
        bonus = 20 if edge.imported_name and edge.imported_name != "*" else 0
        bonus += _shared_package_depth(edge.target_path, edge.source_path) * 5
        evidence = ["import-edge"]
        if edge.imported_name and edge.imported_name != "*":
            evidence.append(f"imported-name:{edge.imported_name}")
        if edge.resolved_module:
            evidence.append(f"resolved-module:{edge.resolved_module}")
        _store_test_link(
            links,
            source_path=edge.target_path,
            test_path=edge.source_path,
            match_reason="import-heuristic",
            score=100 + bonus,
            link_kind="import",
            evidence=evidence,
        )

    for test_path in test_paths:
        test_stem = Path(test_path).stem
        candidates = {test_stem}
        if test_stem.startswith("test_"):
            candidates.add(test_stem[5:])
        if test_stem.endswith("_test"):
            candidates.add(test_stem[:-5])
        normalized_test = _normalized_test_tokens(test_path)

        for source_path in source_paths:
            source_stem = Path(source_path).stem
            proximity_bonus = _shared_package_depth(source_path, test_path) * 5
            if source_stem in candidates:
                _store_test_link(
                    links,
                    source_path=source_path,
                    test_path=test_path,
                    match_reason="filename-heuristic",
                    score=70 + proximity_bonus,
                    link_kind="filename",
                    evidence=[f"stem:{source_stem}"],
                )
                continue
            normalized_source = _normalized_test_tokens(source_path)
            if (
                normalized_source
                and normalized_test
                and len(normalized_test) >= len(normalized_source)
                and normalized_test[-len(normalized_source) :] == normalized_source
            ):
                _store_test_link(
                    links,
                    source_path=source_path,
                    test_path=test_path,
                    match_reason="module-name-heuristic",
                    score=60 + proximity_bonus,
                    link_kind="module-name",
                    evidence=["normalized-module-match"],
                )
                continue
            if source_stem and source_stem in test_path:
                _store_test_link(
                    links,
                    source_path=source_path,
                    test_path=test_path,
                    match_reason="string-heuristic",
                    score=50 + proximity_bonus,
                    link_kind="string",
                    evidence=[f"path-contains:{source_stem}"],
                )
    return sorted(
        links.values(),
        key=lambda item: (
            item.source_path,
            -item.score,
            item.test_path,
            item.link_kind,
        ),
    )


def _entrypoints_from_pyproject(
    root: Path, module_to_path: dict[str, str]
) -> list[str]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return []

    project = data.get("project")
    if not isinstance(project, dict):
        return []
    scripts = project.get("scripts")
    if not isinstance(scripts, dict):
        return []

    out: list[str] = []
    for target in scripts.values():
        if not isinstance(target, str) or ":" not in target:
            continue
        module_name = target.split(":", 1)[0].strip()
        path = module_to_path.get(module_name)
        if path:
            out.append(path)
    return sorted(set(out))


def build_entrypoints(*, root: Path, pack: PackResult) -> list[str]:
    module_to_path = _module_to_path(pack)
    role_hints = {
        _rel_path(pack, file_pack): role_hint_for_file(_rel_path(pack, file_pack))
        for file_pack in pack.files
    }
    return sorted(
        {path for path, hint in role_hints.items() if hint == "entrypoint"}
        | set(_entrypoints_from_pyproject(root, module_to_path))
    )


def build_repository_guide(
    *,
    root: Path,
    pack: PackResult,
    file_bytes: dict[str, int] | None = None,
) -> dict[str, list[str]]:
    file_bytes = file_bytes or {}
    role_hints = {
        _rel_path(pack, file_pack): role_hint_for_file(_rel_path(pack, file_pack))
        for file_pack in pack.files
    }
    import_edges = build_import_edges(pack)
    incoming_counts: dict[str, int] = {}
    for edge in import_edges:
        if edge.target_path is not None:
            incoming_counts[edge.target_path] = (
                incoming_counts.get(edge.target_path, 0) + 1
            )

    key_configs = sorted(path for path, hint in role_hints.items() if hint == "config")
    central_modules = [
        _rel_path(pack, file_pack)
        for file_pack in sorted(
            pack.files,
            key=lambda item: (
                incoming_counts.get(_rel_path(pack, item), 0),
                file_bytes.get(_rel_path(pack, item), 0),
                item.line_count,
                _rel_path(pack, item),
            ),
            reverse=True,
        )
        if role_hints.get(_rel_path(pack, file_pack)) not in {"test", "docs", "config"}
    ][:5]

    workflows: list[str] = []
    rel_paths = {path for path in role_hints}
    if any("pack" in path for path in rel_paths):
        workflows.append("pack")
    if any("unpack" in path for path in rel_paths):
        workflows.append("unpack")
    if any("patch" in path or "apply" in path for path in rel_paths):
        workflows.append("patch/apply")
    if any("validate" in path for path in rel_paths):
        workflows.append("validate")
    if any("doctor" in path for path in rel_paths):
        workflows.append("doctor")

    link_counts: dict[str, int] = {}
    for link in build_test_links(pack):
        link_counts[link.test_path] = link_counts.get(link.test_path, 0) + 1
    test_clusters = sorted(
        [path for path, hint in role_hints.items() if hint == "test"],
        key=lambda path: (link_counts.get(path, 0), path),
        reverse=True,
    )[:5]

    return {
        "entrypoints": build_entrypoints(root=root, pack=pack),
        "main_workflows": workflows,
        "key_config_files": key_configs,
        "central_modules": central_modules,
        "test_clusters": test_clusters,
    }


def build_architecture_map(*, root: Path, pack: PackResult) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = defaultdict(list)
    for file_pack in pack.files:
        rel = _rel_path(pack, file_pack)
        role = role_hint_for_file(rel)
        stem = Path(rel).stem.lower()
        if role == "cli-front-end" or stem.startswith("cli"):
            categories["cli_frontends"].append(rel)
        if role in {"format-definition", "serializer", "deserializer"} or stem in {
            "formats",
            "index_json",
            "manifest",
            "locators",
        }:
            categories["format_schema_layer"].append(rel)
        if stem in {"parse", "model", "symbol_backend"}:
            categories["parsing_symbol_extraction_layer"].append(rel)
        if stem in {"markdown", "render"}:
            categories["rendering_layer"].append(rel)
        if role == "pipeline-orchestrator" or stem in {"pack_pipeline", "packer"}:
            categories["pipeline_orchestrators"].append(rel)
        if role == "diff-engine":
            categories["patch_apply_layer"].append(rel)
        if role in {"schema-validator", "config"} or "validate" in stem:
            categories["validation_layer"].append(rel)
        if role == "security-layer":
            categories["security_layer"].append(rel)
        if role == "token-budgeting":
            categories["token_budgeting_layer"].append(rel)
        if role == "docs-config":
            categories["docs_config"].append(rel)
    return {
        key: sorted(set(values)) for key, values in sorted(categories.items()) if values
    }


def build_file_relationships(
    *,
    root: Path,
    pack: PackResult,
) -> dict[str, dict[str, list[str]]]:
    edges = build_import_edges(pack)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.target_path is None:
            continue
        outgoing[edge.source_path].add(edge.target_path)
        incoming[edge.target_path].add(edge.source_path)

    entrypoints = build_entrypoints(root=root, pack=pack)
    reachability: dict[str, set[str]] = defaultdict(set)
    for entrypoint in entrypoints:
        queue = deque([entrypoint])
        seen = {entrypoint}
        while queue:
            current = queue.popleft()
            reachability[current].add(entrypoint)
            for target in sorted(outgoing.get(current, set())):
                if target in seen:
                    continue
                seen.add(target)
                queue.append(target)

    related_tests: dict[str, list[str]] = defaultdict(list)
    for link in build_test_links(pack):
        related_tests[link.source_path].append(link.test_path)

    package_groups: dict[str, set[str]] = defaultdict(set)
    for file_pack in pack.files:
        rel = _rel_path(pack, file_pack)
        package_groups[_package_context(file_pack)].add(rel)

    relationships: dict[str, dict[str, list[str]]] = {}
    for file_pack in pack.files:
        rel = _rel_path(pack, file_pack)
        package_key = _package_context(file_pack)
        neighbors = sorted(package_groups.get(package_key, set()) - {rel})[
            :_SUMMARY_LIMIT
        ]
        relationships[rel] = {
            "depends_on": sorted(outgoing.get(rel, set()))[:_SUMMARY_LIMIT],
            "used_by": sorted(incoming.get(rel, set()))[:_SUMMARY_LIMIT],
            "related_tests": sorted(set(related_tests.get(rel, [])))[:_SUMMARY_LIMIT],
            "same_package_neighbors": neighbors,
            "entrypoint_reachability": sorted(reachability.get(rel, set()))[
                :_SUMMARY_LIMIT
            ],
        }
    return relationships


def build_file_summaries(
    *,
    pack: PackResult,
) -> dict[str, dict[str, Any]]:
    edges = build_import_edges(pack)
    imports_local: dict[str, int] = defaultdict(int)
    imports_external: dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge.target_path is None:
            imports_external[edge.source_path] += 1
        else:
            imports_local[edge.source_path] += 1

    summaries: dict[str, dict[str, Any]] = {}
    for file_pack in pack.files:
        rel = _rel_path(pack, file_pack)
        role = role_hint_for_file(rel)
        imports_roots = {
            import_ref.module.lstrip(".").split(".", 1)[0]
            for import_ref in file_pack.imports
            if import_ref.module
        }
        primary_symbols = [
            *(
                class_ref.qualname
                for class_ref in sorted(
                    file_pack.classes, key=lambda item: (item.class_line, item.qualname)
                )
            ),
            *(
                defn.qualname
                for defn in sorted(
                    file_pack.defs, key=lambda item: (item.def_line, item.qualname)
                )
            ),
        ][:_SUMMARY_LIMIT]
        summaries[rel] = {
            "role": role,
            "primary_symbols": primary_symbols,
            "imports_local": imports_local.get(rel, 0),
            "imports_external": imports_external.get(rel, 0),
            "exports": list(file_pack.exports[:_SUMMARY_LIMIT]),
            "touches_io": bool(imports_roots & _IO_IMPORT_HINTS),
            "is_test": role in {"test", "test-fixture"},
            "summary_text": build_file_summary_text(
                role=role,
                primary_symbols=primary_symbols,
                exports=list(file_pack.exports[:_SUMMARY_LIMIT]),
                touches_io=bool(imports_roots & _IO_IMPORT_HINTS),
                is_test=role in {"test", "test-fixture"},
            ),
        }
    return summaries


def import_edges_payload(pack: PackResult) -> list[dict[str, Any]]:
    return [
        {
            "source_path": edge.source_path,
            "kind": edge.kind,
            "import_module": edge.import_module,
            "resolved_module": edge.resolved_module,
            "imported_name": edge.imported_name,
            "alias": edge.alias,
            "line": edge.line,
            "target_module": edge.target_module,
            "target_path": edge.target_path,
        }
        for edge in build_import_edges(pack)
    ]


def test_links_payload(pack: PackResult) -> list[dict[str, Any]]:
    return [
        {
            "source_path": link.source_path,
            "test_path": link.test_path,
            "match_reason": link.match_reason,
            "score": link.score,
            "link_kind": link.link_kind,
            "evidence": list(link.evidence),
        }
        for link in build_test_links(pack)
    ]
