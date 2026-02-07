from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path


def sort_paths(paths: Sequence[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: p.as_posix())


def sort_strings(items: Iterable[str]) -> list[str]:
    return sorted(items)
