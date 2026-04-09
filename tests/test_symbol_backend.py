from __future__ import annotations

from pathlib import Path

from codecrate.model import DefRef
from codecrate.symbol_backend import detect_language, extract_non_python_symbols


def test_detect_language_supports_phase_five_suffixes() -> None:
    assert detect_language(Path("Demo.java")) == "java"
    assert detect_language(Path("Demo.cs")) == "c_sharp"
    assert detect_language(Path("demo.cpp")) == "cpp"
    assert detect_language(Path("demo.rb")) == "ruby"
    assert detect_language(Path("demo.php")) == "php"
    assert detect_language(Path("demo.kt")) == "kotlin"


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
    assert result.backend_requested == "tree-sitter"
    assert result.backend_used == "none"
    assert result.language_detected == "unknown"
    assert result.extraction_status == "unsupported-language"


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
    assert result.backend_requested == "none"
    assert result.backend_used == "none"
    assert result.language_detected == "javascript"
    assert result.extraction_status == "disabled"


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

    def _fake_collect_defs_with_tree_sitter(
        **kwargs: object,
    ) -> tuple[list[DefRef], str]:
        assert kwargs["language"] == "typescript"
        return [fake_def], "ok"

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

    assert result.backend_requested == "tree-sitter"
    assert result.backend_used == "tree-sitter"
    assert result.language_detected == "typescript"
    assert result.extraction_status == "ok"
    assert len(result.defs) == 1
    assert result.defs[0].qualname == "f"


def test_extract_non_python_symbols_reports_no_symbols(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "Demo.java"
    path.write_text("class Demo {}\n", encoding="utf-8")

    def _fake_collect_defs_with_tree_sitter(
        **kwargs: object,
    ) -> tuple[list[DefRef], str]:
        assert kwargs["language"] == "java"
        return [], "no-symbols"

    monkeypatch.setattr(
        "codecrate.symbol_backend._collect_defs_with_tree_sitter",
        _fake_collect_defs_with_tree_sitter,
    )

    result = extract_non_python_symbols(
        path=path,
        root=tmp_path,
        text=path.read_text(encoding="utf-8"),
        backend="auto",
    )

    assert result.defs == []
    assert result.backend_requested == "auto"
    assert result.backend_used == "tree-sitter"
    assert result.language_detected == "java"
    assert result.extraction_status == "no-symbols"
