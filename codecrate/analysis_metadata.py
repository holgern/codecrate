from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import FilePack, ImportRef, PackResult

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
    suffix = rel.suffix.lower()

    if name == "__main__.py":
        return "entrypoint"
    if name == "__init__.py":
        return "package-init"
    if parts[:1] == (".github",) or path in _CONFIG_FILES:
        return "config"
    if parts[:1] == ("docs",) or suffix in {".md", ".rst"}:
        return "docs"
    if (
        parts[:1] == ("tests",)
        or "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        return "test"
    if name.startswith("cli") and suffix == ".py":
        return "entrypoint"
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
        key = (edge.target_path, edge.source_path)
        links.setdefault(
            key,
            TestLink(
                source_path=edge.target_path,
                test_path=edge.source_path,
                match_reason="import-heuristic",
            ),
        )

    for test_path in test_paths:
        test_stem = Path(test_path).stem
        candidates = {test_stem}
        if test_stem.startswith("test_"):
            candidates.add(test_stem[5:])
        if test_stem.endswith("_test"):
            candidates.add(test_stem[:-5])

        for source_path in source_paths:
            source_stem = Path(source_path).stem
            if source_stem in candidates:
                links.setdefault(
                    (source_path, test_path),
                    TestLink(
                        source_path=source_path,
                        test_path=test_path,
                        match_reason="filename-heuristic",
                    ),
                )
                continue
            if source_stem and source_stem in test_path:
                links.setdefault(
                    (source_path, test_path),
                    TestLink(
                        source_path=source_path,
                        test_path=test_path,
                        match_reason="string-heuristic",
                    ),
                )
    return sorted(links.values(), key=lambda item: (item.source_path, item.test_path))


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


def build_repository_guide(
    *,
    root: Path,
    pack: PackResult,
    file_bytes: dict[str, int] | None = None,
) -> dict[str, list[str]]:
    file_bytes = file_bytes or {}
    module_to_path = _module_to_path(pack)
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

    entrypoints = sorted(
        {path for path, hint in role_hints.items() if hint == "entrypoint"}
        | set(_entrypoints_from_pyproject(root, module_to_path))
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
    if any("patch" in path for path in rel_paths):
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
        "entrypoints": entrypoints,
        "main_workflows": workflows,
        "key_config_files": key_configs,
        "central_modules": central_modules,
        "test_clusters": test_clusters,
    }


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


def test_links_payload(pack: PackResult) -> list[dict[str, str]]:
    return [
        {
            "source_path": link.source_path,
            "test_path": link.test_path,
            "match_reason": link.match_reason,
        }
        for link in build_test_links(pack)
    ]
