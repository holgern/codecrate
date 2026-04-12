from __future__ import annotations

import configparser
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]


@dataclass(frozen=True)
class SetupMetadata:
    ecosystem: str
    source_file: str
    prepare_command: str
    runtime_dependencies: list[str]
    dev_dependencies: list[str]
    dev_prepare_command: str | None = None


_PYTHON_DEV_GROUPS = {"dev", "test", "tests", "lint", "docs", "ci"}
_REQUIRE_RE = re.compile(r"^require\s+(?P<module>\S+)\s+(?P<version>\S+)$")


def _read_toml_file(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as fh:
            parsed = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _dedupe_items(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _parse_requirements_lines(text: str) -> list[str]:
    deps: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            continue
        if line.startswith(("--", "-f ", "--find-links ")):
            continue
        if " #" in line:
            line = line.split(" #", 1)[0].rstrip()
        deps.append(line)
    return _dedupe_items(deps)


def _parse_cfg_list(value: str) -> list[str]:
    return _dedupe_items([line.strip() for line in value.splitlines()])


def _format_dep_value(name: str, value: Any) -> str:
    if isinstance(value, str):
        version = value.strip()
        return name if not version or version == "*" else f"{name} {version}"
    if isinstance(value, dict):
        version = str(value.get("version") or "").strip()
        return name if not version or version == "*" else f"{name} {version}"
    return name


def _parse_go_mod(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    deps: list[str] = []
    in_require_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line == "require (":
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue

        match = _REQUIRE_RE.match(line)
        if match:
            deps.append(f"{match.group('module')} {match.group('version')}")
            continue

        if in_require_block:
            entry = line.split("//", 1)[0].strip()
            if entry:
                deps.append(entry)
    return _dedupe_items(deps)


def _detect_python_from_pyproject(root: Path) -> SetupMetadata | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None

    data = _read_toml_file(path)
    if data is None:
        return None

    project = data.get("project")
    if isinstance(project, dict):
        runtime = _dedupe_items(
            [str(item).strip() for item in project.get("dependencies", []) if item]
        )
        optional = project.get("optional-dependencies")
        dev: list[str] = []
        if isinstance(optional, dict):
            for group, values in optional.items():
                if group in _PYTHON_DEV_GROUPS and isinstance(values, list):
                    dev.extend(str(item).strip() for item in values if item)
        dev = _dedupe_items(dev)
        dev_prepare = 'python -m pip install -e ".[dev]"'
        if not isinstance(optional, dict) or "dev" not in optional:
            dev_prepare = None
        return SetupMetadata(
            ecosystem="Python",
            source_file="pyproject.toml",
            prepare_command="python -m pip install -e .",
            runtime_dependencies=runtime,
            dev_dependencies=dev,
            dev_prepare_command=dev_prepare,
        )

    tool = data.get("tool")
    if not isinstance(tool, dict):
        if "build-system" not in data:
            return None
        return SetupMetadata(
            ecosystem="Python",
            source_file="pyproject.toml",
            prepare_command="python -m pip install -e .",
            runtime_dependencies=[],
            dev_dependencies=[],
        )

    poetry = tool.get("poetry")
    if not isinstance(poetry, dict):
        if "build-system" not in data:
            return None
        return SetupMetadata(
            ecosystem="Python",
            source_file="pyproject.toml",
            prepare_command="python -m pip install -e .",
            runtime_dependencies=[],
            dev_dependencies=[],
        )

    runtime: list[str] = []
    deps = poetry.get("dependencies")
    if isinstance(deps, dict):
        for name, value in deps.items():
            if name == "python":
                continue
            runtime.append(_format_dep_value(str(name), value))

    dev: list[str] = []
    legacy_dev = poetry.get("dev-dependencies")
    if isinstance(legacy_dev, dict):
        for name, value in legacy_dev.items():
            dev.append(_format_dep_value(str(name), value))

    groups = poetry.get("group")
    if isinstance(groups, dict):
        for group_name, group_value in groups.items():
            if group_name not in _PYTHON_DEV_GROUPS or not isinstance(
                group_value, dict
            ):
                continue
            group_deps = group_value.get("dependencies")
            if not isinstance(group_deps, dict):
                continue
            for name, value in group_deps.items():
                dev.append(_format_dep_value(str(name), value))

    return SetupMetadata(
        ecosystem="Python",
        source_file="pyproject.toml",
        prepare_command="python -m pip install -e .",
        runtime_dependencies=_dedupe_items(runtime),
        dev_dependencies=_dedupe_items(dev),
        dev_prepare_command='python -m pip install -e ".[dev]"' if dev else None,
    )


def _detect_python_from_setup_cfg(root: Path) -> SetupMetadata | None:
    path = root / "setup.cfg"
    if not path.is_file():
        return None

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError):
        return None

    runtime = _parse_cfg_list(parser.get("options", "install_requires", fallback=""))
    dev: list[str] = []
    if parser.has_section("options.extras_require"):
        for group_name, value in parser.items("options.extras_require"):
            if group_name in _PYTHON_DEV_GROUPS:
                dev.extend(_parse_cfg_list(value))

    return SetupMetadata(
        ecosystem="Python",
        source_file="setup.cfg",
        prepare_command="python -m pip install -e .",
        runtime_dependencies=runtime,
        dev_dependencies=_dedupe_items(dev),
        dev_prepare_command='python -m pip install -e ".[dev]"' if dev else None,
    )


def _detect_python_from_setup_py(root: Path) -> SetupMetadata | None:
    path = root / "setup.py"
    if not path.is_file():
        return None
    return SetupMetadata(
        ecosystem="Python",
        source_file="setup.py",
        prepare_command="python -m pip install -e .",
        runtime_dependencies=[],
        dev_dependencies=[],
    )


def _detect_python_from_requirements(root: Path) -> SetupMetadata | None:
    runtime_path: Path | None = None
    for name in ("requirements.txt", "requirements.in"):
        candidate = root / name
        if candidate.is_file():
            runtime_path = candidate
            break
    if runtime_path is None:
        return None

    try:
        runtime_text = runtime_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    dev: list[str] = []
    dev_path: Path | None = None
    for name in ("requirements-dev.txt", "dev-requirements.txt", "requirements-dev.in"):
        candidate = root / name
        if not candidate.is_file():
            continue
        dev_path = candidate
        try:
            dev = _parse_requirements_lines(
                candidate.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            dev = []
        break

    dev_prepare = None
    if dev_path is not None:
        dev_prepare = f"python -m pip install -r {runtime_path.name} -r {dev_path.name}"

    return SetupMetadata(
        ecosystem="Python",
        source_file=runtime_path.name,
        prepare_command=f"python -m pip install -r {runtime_path.name}",
        runtime_dependencies=_parse_requirements_lines(runtime_text),
        dev_dependencies=dev,
        dev_prepare_command=dev_prepare,
    )


def _detect_node(root: Path) -> SetupMetadata | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    if (root / "pnpm-lock.yaml").is_file():
        prepare = "pnpm install"
    elif (root / "yarn.lock").is_file():
        prepare = "yarn install"
    elif (root / "package-lock.json").is_file() or (
        root / "npm-shrinkwrap.json"
    ).is_file():
        prepare = "npm install"
    else:
        package_manager = str(data.get("packageManager") or "")
        if package_manager.startswith("pnpm@"):  # pragma: no branch
            prepare = "pnpm install"
        elif package_manager.startswith("yarn@"):
            prepare = "yarn install"
        else:
            prepare = "npm install"

    runtime: list[str] = []
    for key in ("dependencies", "optionalDependencies"):
        deps = data.get(key)
        if not isinstance(deps, dict):
            continue
        runtime.extend(
            _format_dep_value(str(name), value) for name, value in deps.items()
        )

    dev_deps = data.get("devDependencies")
    dev = []
    if isinstance(dev_deps, dict):
        dev = [_format_dep_value(str(name), value) for name, value in dev_deps.items()]

    return SetupMetadata(
        ecosystem="Node.js",
        source_file="package.json",
        prepare_command=prepare,
        runtime_dependencies=_dedupe_items(runtime),
        dev_dependencies=_dedupe_items(dev),
    )


def _detect_rust(root: Path) -> SetupMetadata | None:
    path = root / "Cargo.toml"
    if not path.is_file():
        return None

    data = _read_toml_file(path)
    if data is None:
        return None

    runtime: list[str] = []
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        runtime.extend(
            _format_dep_value(str(name), value) for name, value in deps.items()
        )

    dev: list[str] = []
    dev_deps = data.get("dev-dependencies")
    if isinstance(dev_deps, dict):
        dev.extend(
            _format_dep_value(str(name), value) for name, value in dev_deps.items()
        )

    return SetupMetadata(
        ecosystem="Rust",
        source_file="Cargo.toml",
        prepare_command="cargo fetch",
        runtime_dependencies=_dedupe_items(runtime),
        dev_dependencies=_dedupe_items(dev),
    )


def _detect_go(root: Path) -> SetupMetadata | None:
    path = root / "go.mod"
    if not path.is_file():
        return None
    return SetupMetadata(
        ecosystem="Go",
        source_file="go.mod",
        prepare_command="go mod download",
        runtime_dependencies=_parse_go_mod(path),
        dev_dependencies=[],
    )


def detect_setup_metadata(root: Path) -> SetupMetadata | None:
    root = root.resolve()
    for detector in (
        _detect_python_from_pyproject,
        _detect_python_from_setup_cfg,
        _detect_python_from_setup_py,
        _detect_python_from_requirements,
        _detect_node,
        _detect_rust,
        _detect_go,
    ):
        detected = detector(root)
        if detected is not None:
            return detected
    return None
