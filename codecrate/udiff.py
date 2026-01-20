from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HUNK_RE = re.compile(r"^@@\s+-(\d+),?(\d*)\s+\+(\d+),?(\d*)\s+@@")
_FROM_RE = re.compile(r"^---\s+a/(.+)$")
_TO_RE = re.compile(r"^\+\+\+\s+b/(.+)$")


def normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class FileDiff:
    path: str
    hunks: list[list[str]]  # raw hunk lines including @@ header and +/-/space lines


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    lines = normalize_newlines(diff_text).splitlines()
    i = 0
    out: list[FileDiff] = []

    while i < len(lines):
        m_from = _FROM_RE.match(lines[i])
        if not m_from:
            i += 1
            continue
        from_path = m_from.group(1)
        if i + 1 >= len(lines):
            break
        m_to = _TO_RE.match(lines[i + 1])
        if not m_to:
            i += 1
            continue
        to_path = m_to.group(1)
        path = to_path  # apply to b/<path>
        i += 2

        hunks: list[list[str]] = []
        while i < len(lines):
            if _FROM_RE.match(lines[i]):
                break
            if lines[i].startswith("@@"):
                h = [lines[i]]
                i += 1
                while (
                    i < len(lines)
                    and not lines[i].startswith("@@")
                    and not _FROM_RE.match(lines[i])
                ):
                    if lines[i].startswith((" ", "+", "-")):
                        h.append(lines[i])
                    i += 1
                hunks.append(h)
            else:
                i += 1

        out.append(FileDiff(path=path, hunks=hunks))

    return out


def apply_hunks_to_text(old_text: str, hunks: list[list[str]]) -> str:
    """
    Minimal unified-diff applier.
    - Expects hunks in order and matching context lines.
    - Raises ValueError on mismatch.
    """
    old_lines = normalize_newlines(old_text).splitlines()
    new_lines: list[str] = []
    old_i = 0

    for hunk in hunks:
        m = _HUNK_RE.match(hunk[0])
        if not m:
            raise ValueError(f"Bad hunk header: {hunk[0]}")
        old_start = int(m.group(1)) - 1  # 0-based

        # copy unchanged prefix
        if old_start < old_i:
            raise ValueError("Overlapping hunks")
        new_lines.extend(old_lines[old_i:old_start])
        old_i = old_start

        # apply hunk lines
        for line in hunk[1:]:
            tag = line[:1]
            payload = line[1:]
            if tag == " ":
                if old_i >= len(old_lines) or old_lines[old_i] != payload:
                    raise ValueError("Context mismatch while applying patch")
                new_lines.append(payload)
                old_i += 1
            elif tag == "-":
                if old_i >= len(old_lines) or old_lines[old_i] != payload:
                    raise ValueError("Delete mismatch while applying patch")
                old_i += 1
            elif tag == "+":
                new_lines.append(payload)
            else:
                raise ValueError(f"Unexpected diff tag: {tag}")

    # copy remainder
    new_lines.extend(old_lines[old_i:])
    return "\n".join(new_lines) + ("\n" if old_text.endswith("\n") else "")


def apply_file_diffs(diffs: list[FileDiff], root: Path) -> list[Path]:
    """
    Applies diffs to files under root. Returns list of modified paths.
    """
    root = root.resolve()
    changed: list[Path] = []

    for fd in diffs:
        path = root / fd.path
        old = ""
        if path.exists():
            old = path.read_text(encoding="utf-8", errors="replace")
        new = apply_hunks_to_text(old, fd.hunks)
        ensure_parent_dir(path)
        path.write_text(new, encoding="utf-8")
        changed.append(path)

    return changed
