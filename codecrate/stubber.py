from __future__ import annotations

import io
import tokenize

from .model import DefRef


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _rewrite_single_line_def(line: str, marker: str) -> list[str]:
    """Keep one-liners as one-liners to preserve line numbers."""
    src = line if line.endswith("\n") else line + "\n"
    tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))

    colon_col = None
    for tok in tokens:
        if tok.type == tokenize.OP and tok.string == ":":
            colon_col = tok.end[1]
    if colon_col is None:
        return [line]

    head = line[:colon_col].rstrip()
    # marker already starts with '#', so this becomes an inline comment
    return [f"{head} ...  {marker}\n"]


def _replacement_lines(indent: str, marker: str, n: int) -> list[str]:
    """Create exactly n lines of stub replacement."""
    if n <= 0:
        return []
    if n == 1:
        return [f"{indent}{marker}\n"]
    if n == 2:
        return [f"{indent}{marker}\n", f"{indent}...\n"]
    filler = [f"{indent}# …\n"] * (n - 2)
    return [f"{indent}{marker}\n", f"{indent}...\n"] + filler


def stub_file_text(text: str, defs: list[DefRef], keep_docstrings: bool = True) -> str:
    """Return stubbed version of file text, preserving original line count."""
    lines = text.splitlines(keepends=True)
    defs_sorted = sorted(
        defs, key=lambda d: (d.def_line, d.body_start, d.end_line), reverse=True
    )

    for d in defs_sorted:
        marker = f"# ↪ FUNC:{d.id} (L{d.def_line}–L{d.end_line})"

        if d.is_single_line:
            i = d.def_line - 1
            if 0 <= i < len(lines):
                lines[i : i + 1] = _rewrite_single_line_def(lines[i], marker)
            continue

        start_line = d.body_start
        if keep_docstrings and d.doc_end is not None:
            start_line = d.doc_end + 1

        i0 = max(0, start_line - 1)
        i1 = min(len(lines), d.end_line)  # inclusive end_line -> exclusive slice end

        if i0 >= i1:
            insert_at = min(len(lines), (d.doc_end or d.body_start))
            base_line = lines[insert_at - 1] if 0 <= insert_at - 1 < len(lines) else ""
            indent = _indent_of(base_line) if base_line else " " * 4
            lines[insert_at:insert_at] = [f"{indent}{marker}\n", f"{indent}...\n"]
            continue

        n = i1 - i0
        sample = lines[i0] if 0 <= i0 < len(lines) else ""
        indent = _indent_of(sample) if sample else " " * 4
        lines[i0:i1] = _replacement_lines(indent, marker, n)

    return "".join(lines)
