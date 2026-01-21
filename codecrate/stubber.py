from __future__ import annotations

import io
import tokenize

from .model import DefRef


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _rewrite_single_line_def(line: str, marker: str) -> list[str]:
    src = line if line.endswith("\n") else line + "\n"
    tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    colon_col = None
    for tok in tokens:
        if tok.type == tokenize.OP and tok.string == ":":
            colon_col = tok.end[1]
    if colon_col is None:
        return [line]
    head = line[:colon_col].rstrip()
    return [f"{head} ...  {marker}\n"]


def _replacement_lines(indent: str, marker: str) -> list[str]:
    # Compact stub: single placeholder line.
    return [f"{indent}...  {marker}\n"]


def stub_file_text(text: str, defs: list[DefRef], keep_docstrings: bool = True) -> str:
    lines = text.splitlines(keepends=True)
    defs_sorted = sorted(
        defs, key=lambda d: (d.def_line, d.body_start, d.end_line), reverse=True
    )

    for d in defs_sorted:
        marker = f"# ↪ FUNC:{d.id}"

        if d.is_single_line:
            i = d.def_line - 1
            if 0 <= i < len(lines):
                lines[i : i + 1] = _rewrite_single_line_def(lines[i], marker)
            continue

        start_line = d.body_start
        if keep_docstrings and d.doc_end is not None:
            start_line = d.doc_end + 1

        i0 = max(0, start_line - 1)
        i1 = min(len(lines), d.end_line)
        if i0 >= i1:
            # No body lines to replace.
            # If we kept the docstring, annotate the docstring closing line instead.
            if keep_docstrings and d.doc_end is not None:
                idx = d.doc_end - 1
                if 0 <= idx < len(lines):
                    ln = lines[idx]
                    base = ln[:-1] if ln.endswith("\n") else ln
                    if marker not in base:
                        lines[idx] = base + f"  {marker}\n"
            continue

        sample = lines[i0] if 0 <= i0 < len(lines) else ""
        indent = _indent_of(sample) if sample else " " * 4
        lines[i0:i1] = _replacement_lines(indent, marker)

    return "".join(lines)
