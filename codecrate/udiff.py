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
                    if lines[i].startswith((" ", "+", "-", "\\")):
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

    def _parse_count(raw: str) -> int:
        return 1 if raw == "" else int(raw)

    old_text_norm = normalize_newlines(old_text)
    old_lines = old_text_norm.splitlines()
    old_has_trailing_newline = old_text_norm.endswith("\n")
    new_lines: list[str] = []
    old_i = 0
    new_has_trailing_newline = old_has_trailing_newline

    for hunk in hunks:
        m = _HUNK_RE.match(hunk[0])
        if not m:
            raise ValueError(f"bad hunk header: {hunk[0]}")
        old_start = max(0, int(m.group(1)) - 1)  # 0-based; -0 in hunks means start
        old_count = _parse_count(m.group(2))
        new_count = _parse_count(m.group(4))

        # copy unchanged prefix
        if old_start < old_i and not (old_i == 0 and len(old_lines) == 0):
            raise ValueError(f"{hunk[0]}: overlapping hunks")
        if old_start > len(old_lines):
            raise ValueError(f"{hunk[0]}: hunk start out of range")
        new_lines.extend(old_lines[old_i:old_start])
        old_i = old_start

        consumed_old = 0
        produced_new = 0
        prev_tag: str | None = None

        # apply hunk lines
        for line in hunk[1:]:
            if line == r"\ No newline at end of file":
                if prev_tag in {" ", "+"}:
                    new_has_trailing_newline = False
                elif prev_tag is None:
                    raise ValueError(f"{hunk[0]}: dangling no-newline marker in patch")
                continue

            tag = line[:1]
            payload = line[1:]
            if tag == " ":
                if old_i >= len(old_lines) or old_lines[old_i] != payload:
                    actual = old_lines[old_i] if old_i < len(old_lines) else "<EOF>"
                    raise ValueError(
                        f"{hunk[0]}: context mismatch at line {old_i + 1}; "
                        f"expected {payload!r}, got {actual!r}"
                    )
                new_lines.append(payload)
                old_i += 1
                consumed_old += 1
                produced_new += 1
                new_has_trailing_newline = True
                prev_tag = " "
            elif tag == "-":
                if old_i >= len(old_lines) or old_lines[old_i] != payload:
                    actual = old_lines[old_i] if old_i < len(old_lines) else "<EOF>"
                    raise ValueError(
                        f"{hunk[0]}: delete mismatch at line {old_i + 1}; "
                        f"expected {payload!r}, got {actual!r}"
                    )
                old_i += 1
                consumed_old += 1
                prev_tag = "-"
            elif tag == "+":
                new_lines.append(payload)
                produced_new += 1
                new_has_trailing_newline = True
                prev_tag = "+"
            else:
                raise ValueError(f"{hunk[0]}: unexpected diff tag: {tag}")

        if consumed_old != old_count:
            raise ValueError(
                f"{hunk[0]}: hunk old-line count mismatch "
                f"(expected {old_count}, got {consumed_old})"
            )
        if produced_new != new_count:
            raise ValueError(
                f"{hunk[0]}: hunk new-line count mismatch "
                f"(expected {new_count}, got {produced_new})"
            )

    # copy remainder
    new_lines.extend(old_lines[old_i:])
    if old_i < len(old_lines):
        new_has_trailing_newline = old_has_trailing_newline

    out = "\n".join(new_lines)
    if out and new_has_trailing_newline:
        out += "\n"
    return out


def apply_file_diffs(
    diffs: list[FileDiff],
    root: Path,
    *,
    dry_run: bool = False,
) -> list[Path]:
    """
    Applies diffs to files under root. Returns list of modified paths.
    """
    root = root.resolve()
    changed: list[Path] = []

    for fd in diffs:
        path = safe_join(root, fd.path)

        if fd.op == "delete":
            if path.exists() and not dry_run:
                path.unlink()
            changed.append(path)
            continue

        old = ""
        if path.exists():
            old = path.read_text(encoding="utf-8", errors="replace")
        try:
            new = apply_hunks_to_text(old, fd.hunks)
        except ValueError as e:
            hunk_header = fd.hunks[0][0] if fd.hunks else "@@ <unknown> @@"
            raise ValueError(f"{fd.path}: {hunk_header}: {e}") from e
        if not dry_run:
            ensure_parent_dir(path)
            path.write_text(new, encoding="utf-8")
        changed.append(path)

    return changed
