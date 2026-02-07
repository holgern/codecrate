from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

_HUNK_RE = re.compile(r"^@@\s+-(\d+),?(\d*)\s+\+(\d+),?(\d*)\s+@@")
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _is_absolute_like(path: str) -> bool:
    return (
        path.startswith(("/", "\\"))
        or bool(_WINDOWS_ABS_RE.match(path))
        or Path(path).is_absolute()
    )


def _normalize_diff_path(path: str) -> str:
    raw = path.strip()
    if not raw:
        raise ValueError("Refusing empty diff path")
    if _is_absolute_like(raw):
        raise ValueError(f"Refusing absolute diff path: {raw}")

    normalized = posixpath.normpath(raw.replace("\\", "/"))
    if normalized in {"", "."}:
        raise ValueError(f"Refusing invalid diff path: {raw}")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise ValueError(f"Refusing path traversal in diff path: {raw}")
    return normalized


def safe_join(root: Path, relpath: str) -> Path:
    root_resolved = root.resolve()
    normalized_rel = _normalize_diff_path(relpath)
    target = (root_resolved / normalized_rel).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as e:
        raise ValueError(f"Refusing path outside root: {relpath}") from e
    return target


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class FileDiff:
    path: str
    hunks: list[list[str]]  # raw hunk lines including @@ header and +/-/space lines
    op: Literal["add", "modify", "delete"]


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    lines = normalize_newlines(diff_text).splitlines()
    i = 0
    out: list[FileDiff] = []

    while i < len(lines):
        if not lines[i].startswith("--- "):
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        if not lines[i + 1].startswith("+++ "):
            i += 1
            continue
        from_raw = lines[i][4:].strip()
        to_raw = lines[i + 1][4:].strip()

        def _side(raw: str, prefix: str) -> str | None:
            if raw == "/dev/null":
                return None
            return raw[len(prefix) :] if raw.startswith(prefix) else raw

        from_path_raw = _side(from_raw, "a/")
        to_path_raw = _side(to_raw, "b/")

        from_path = (
            _normalize_diff_path(from_path_raw) if from_path_raw is not None else None
        )
        to_path = _normalize_diff_path(to_path_raw) if to_path_raw is not None else None

        if from_path is None and to_path is None:
            i += 2
            continue

        if from_path is None:
            op: Literal["add", "modify", "delete"] = "add"
            if to_path is None:
                raise ValueError("Patch has no file path")
            path = to_path
        elif to_path is None:
            op = "delete"
            path = from_path
        else:
            op = "modify"
            path = to_path
        i += 2

        hunks: list[list[str]] = []
        while i < len(lines):
            if lines[i].startswith("--- "):
                break
            if lines[i].startswith("@@"):
                h = [lines[i]]
                i += 1
                while (
                    i < len(lines)
                    and not lines[i].startswith("@@")
                    and not lines[i].startswith("--- ")
                ):
                    if lines[i].startswith((" ", "+", "-")):
                        h.append(lines[i])
                    i += 1
                hunks.append(h)
            else:
                i += 1

        out.append(FileDiff(path=path, hunks=hunks, op=op))

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
        if old_start < old_i and not (old_i == 0 and len(old_lines) == 0):
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
                # Check if current line matches what we'd add (file already modified)
                current_line_matches_target = False
                if old_i < len(old_lines) and old_lines[old_i] != payload:
                    # Look ahead to find what we're adding
                    add_line = None
                    for next_line in hunk[1:]:
                        if next_line.startswith("+"):
                            add_line = next_line[1:]  # Full add line with indentation
                            break
                    # If current line matches what we'd add (with/without stripping),
                    # skip the delete operation
                    if add_line is not None:
                        current_matches_add = old_lines[old_i] == add_line
                        current_matches_add_stripped = (
                            old_lines[old_i].strip() == add_line.strip()
                        )
                        if current_matches_add or current_matches_add_stripped:
                            current_line_matches_target = True

                if not current_line_matches_target:
                    # Use original payload for comparison, but also try stripped version
                    if old_i < len(old_lines) and old_lines[old_i] != payload:
                        # Try stripped versions for fuzzy matching
                        old_stripped = old_lines[old_i].strip()
                        payload_stripped = payload.strip()
                        if old_stripped != payload_stripped:
                            raise ValueError("Delete mismatch while applying patch")
                old_i += 1
            elif tag == "+":
                new_lines.append(payload)
            else:
                raise ValueError(f"Unexpected diff tag: {tag}")

    # copy remainder
    new_lines.extend(old_lines[old_i:])
    out = "\n".join(new_lines)
    if old_text.endswith("\n") or (not old_text and out):
        out += "\n"
    return out


def apply_file_diffs(diffs: list[FileDiff], root: Path) -> list[Path]:
    """
    Applies diffs to files under root. Returns list of modified paths.
    """
    root = root.resolve()
    changed: list[Path] = []

    for fd in diffs:
        path = safe_join(root, fd.path)

        if fd.op == "delete":
            if path.exists():
                path.unlink()
            changed.append(path)
            continue

        old = ""
        if path.exists():
            old = path.read_text(encoding="utf-8", errors="replace")
        new = apply_hunks_to_text(old, fd.hunks)
        ensure_parent_dir(path)
        path.write_text(new, encoding="utf-8")
        changed.append(path)

    return changed
