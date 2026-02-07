from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pathspec

DEFAULT_EXCLUDES = [
    "**/__pycache__/**",
    "**/*.pyc",
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/.tox/**",
    "**/.pytest_cache/**",
    "**/build/**",
    "**/dist/**",
    "**/_version.py",
]


@dataclass(frozen=True)
class Discovery:
    files: list[Path]
    root: Path


def _load_ignore_lines(root: Path, filename: str) -> list[str]:
    p = root / filename
    if not p.exists():
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines()


def _load_gitignore(root: Path) -> pathspec.PathSpec:
    return pathspec.PathSpec.from_lines(
        "gitwildmatch", _load_ignore_lines(root, ".gitignore")
    )


def _load_combined_ignore(root: Path, *, respect_gitignore: bool) -> pathspec.PathSpec:
    # Order matters: patterns later in the list take precedence (e.g. negations).
    lines: list[str] = []
    if respect_gitignore:
        lines.extend(_load_ignore_lines(root, ".gitignore"))
    # Tool-specific ignore is always respected and has higher priority.
    lines.extend(_load_ignore_lines(root, ".codecrateignore"))
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _is_confined_to_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_explicit_files(root: Path, files: Sequence[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    for raw in files:
        p = Path(raw)
        if not p.is_absolute():
            p = root / p
        if not p.is_file():
            continue
        if not _is_confined_to_root(p, root):
            continue

        p = p.resolve()

        key = p.as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)

    out.sort()
    return out


def discover_files(
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
    respect_gitignore: bool = True,
    *,
    explicit_files: Sequence[Path] | None = None,
) -> Discovery:
    """Discover repository files matching include/exclude patterns.

    Unlike discover_python_files, this scans *all* files (not just *.py). This is
    useful for packing metadata and docs files (e.g. pyproject.toml, *.rst).
    Notes:
    - If a ``.codecrateignore`` file exists in ``root``, its patterns are always
      respected (gitignore-style).
    - When ``explicit_files`` is provided, only those files are considered (after
      resolution + deduplication). Include patterns are not applied to the explicit
      list; exclude patterns and ignore files still are.
    """
    root = root.resolve()

    ignore = _load_combined_ignore(root, respect_gitignore=respect_gitignore)
    inc = pathspec.PathSpec.from_lines("gitwildmatch", include or ["**/*.py"])

    effective_exclude = DEFAULT_EXCLUDES + (exclude or [])
    exc = pathspec.PathSpec.from_lines("gitwildmatch", effective_exclude)

    out: list[Path] = []
    if explicit_files is None:
        candidates = [p for p in root.rglob("*") if p.is_file()]
        apply_inc = True
    else:
        candidates = _resolve_explicit_files(root, explicit_files)
        apply_inc = False

    for p in candidates:
        if not _is_confined_to_root(p, root):
            continue
        rel = p.relative_to(root)
        rel_s = rel.as_posix()

        if ignore.match_file(rel_s):
            continue
        if apply_inc and not inc.match_file(rel_s):
            continue
        if exc.match_file(rel_s):
            continue

        out.append(p)

    out.sort()
    return Discovery(files=out, root=root)


def discover_python_files(
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
    respect_gitignore: bool = True,
) -> Discovery:
    root = root.resolve()

    ignore = _load_combined_ignore(root, respect_gitignore=respect_gitignore)
    inc = pathspec.PathSpec.from_lines("gitwildmatch", include or ["**/*.py"])

    effective_exclude = DEFAULT_EXCLUDES + (exclude or [])
    exc = pathspec.PathSpec.from_lines("gitwildmatch", effective_exclude)

    out: list[Path] = []
    for p in root.rglob("*.py"):
        if not _is_confined_to_root(p, root):
            continue
        rel = p.relative_to(root)
        rel_s = rel.as_posix()

        if ignore.match_file(rel_s):
            continue
        if not inc.match_file(rel_s):
            continue
        if exc.match_file(rel_s):
            continue

        out.append(p)

    out.sort()
    return Discovery(files=out, root=root)
