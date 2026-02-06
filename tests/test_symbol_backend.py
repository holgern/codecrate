from __future__ import annotations

from pathlib import Path

from codecrate.model import DefRef
from codecrate.symbol_backend import extract_non_python_symbols


def test_extract_non_python_symbols_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello\n", encoding="utf-8")

    result = extract_non_python_symbols(
        path=path,
        root=tmp_path,
        text=path.read_text(encoding="utf-8"),
        backend="tree-sitter",
    )

    assert result.defs == []
    assert result.backend_used == "none"


def test_extract_non_python_symbols_backend_none(tmp_path: Path) -> None:
    path = tmp_path / "a.js"
    path.write_text("function f() { return 1; }\n", encoding="utf-8")

    result = extract_non_python_symbols(
        path=path,
        root=tmp_path,
        text=path.read_text(encoding="utf-8"),
        backend="none",
    )

    assert result.defs == []
    assert result.backend_used == "none"


def test_extract_non_python_symbols_uses_tree_sitter_collector(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "a.ts"
    path.write_text("function f(): number { return 1 }\n", encoding="utf-8")

    fake_def = DefRef(
        path=path,
        module="a",
        qualname="f",
        id="ABCDEF12",
        local_id="ABCDEF12",
        kind="symbol_function",
        decorator_start=1,
        def_line=1,
        body_start=1,
        end_line=1,
    )

    def _fake_collect_defs_with_tree_sitter(**kwargs: object) -> list[DefRef]:
        return [fake_def]

    monkeypatch.setattr(
        "codecrate.symbol_backend._collect_defs_with_tree_sitter",
        _fake_collect_defs_with_tree_sitter,
    )

    result = extract_non_python_symbols(
        path=path,
        root=tmp_path,
        text=path.read_text(encoding="utf-8"),
        backend="tree-sitter",
    )

    assert result.backend_used == "tree-sitter"
    assert len(result.defs) == 1
    assert result.defs[0].qualname == "f"
