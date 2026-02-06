from __future__ import annotations

from codecrate.tokens import format_token_count_tree, format_top_files


def test_format_top_files_orders_descending() -> None:
    file_tokens = {
        "a.py": 20,
        "b.py": 50,
        "sub/c.py": 30,
    }

    out = format_top_files(file_tokens, top_n=2)

    assert out.splitlines() == [
        "Top files by tokens:",
        " 1. b.py (50 tokens)",
        " 2. sub/c.py (30 tokens)",
    ]


def test_format_top_files_non_positive_returns_empty() -> None:
    assert format_top_files({"a.py": 1}, top_n=0) == ""
    assert format_top_files({"a.py": 1}, top_n=-1) == ""


def test_format_token_count_tree_applies_threshold() -> None:
    file_tokens = {
        "src/a.py": 100,
        "src/b.py": 5,
        "docs/readme.rst": 20,
    }

    out = format_token_count_tree(file_tokens, threshold=10)

    assert "Token Count Tree (threshold=10)" in out
    assert "└── . (125 tokens)" in out
    assert "src (105 tokens)" in out
    assert "a.py (100 tokens)" in out
    assert "b.py (5 tokens)" not in out
    assert "docs (20 tokens)" in out
