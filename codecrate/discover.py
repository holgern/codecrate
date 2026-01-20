from __future__ import annotations

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


def _load_gitignore(root: Path) -> pathspec.PathSpec:
    gi = root / ".gitignore"
    if not gi.exists():
        return pathspec.PathSpec.from_lines("gitwildmatch", [])
    return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text(encoding="utf-8").splitlines())


def discover_python_files(
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
    respect_gitignore: bool = True,
) -> Discovery:
    root = root.resolve()

    gi = _load_gitignore(root) if respect_gitignore else pathspec.PathSpec.from_lines("gitwildmatch", [])
    inc = pathspec.PathSpec.from_lines("gitwildmatch", include or ["**/*.py"])

    effective_exclude = DEFAULT_EXCLUDES + (exclude or [])
    exc = pathspec.PathSpec.from_lines("gitwildmatch", effective_exclude)

    out: list[Path] = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        rel_s = rel.as_posix()

        if respect_gitignore and gi.match_file(rel_s):
            continue
        if not inc.match_file(rel_s):
            continue
        if exc.match_file(rel_s):
            continue

        out.append(p)

    out.sort()
    return Discovery(files=out, root=root)
