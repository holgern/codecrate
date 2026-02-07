from __future__ import annotations

import re

_BACKTICK_RUN_RE = re.compile(r"`+")
_FENCE_OPEN_RE = re.compile(
    r"^(?P<fence>`{3,})[ \t]*(?P<info>[A-Za-z0-9_-]+)(?:[ \t]+.*)?$"
)


def longest_backtick_run(text: str) -> int:
    max_len = 0
    for m in _BACKTICK_RUN_RE.finditer(text):
        max_len = max(max_len, len(m.group(0)))
    return max_len


def choose_backtick_fence(text: str, *, min_len: int = 3) -> str:
    return "`" * max(min_len, longest_backtick_run(text) + 1)


def parse_fence_open(line: str) -> tuple[str, str] | None:
    m = _FENCE_OPEN_RE.match(line.strip())
    if not m:
        return None
    return m.group("fence"), m.group("info")


def is_fence_close(line: str, fence: str) -> bool:
    return line.strip() == fence
