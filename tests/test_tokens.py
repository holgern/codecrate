from __future__ import annotations

from codecrate.tokens import (
    TokenCounter,
    format_token_count_tree,
    format_top_files,
    format_top_files_by_size,
)


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


def test_format_top_files_by_size_orders_descending() -> None:
    out = format_top_files_by_size(
        {
            "a.py": 120,
            "b.py": 400,
            "sub/c.py": 200,
        },
        top_n=2,
    )

    assert out.splitlines() == [
        "Top files by size (heuristic tokens):",
        " 1. b.py (400 bytes, ~100 tokens)",
        " 2. sub/c.py (200 bytes, ~50 tokens)",
    ]


def test_token_counter_caches_by_content_hash(monkeypatch) -> None:
    calls: dict[str, int] = {"encode": 0}

    class _FakeEncoder:
        def encode(self, text: str) -> list[int]:
            calls["encode"] += 1
            return [1] * len(text)

    monkeypatch.setattr("codecrate.tokens._get_encoder", lambda _: _FakeEncoder())

    c = TokenCounter("cache-test-encoding")
    assert c.count("cache me") == len("cache me")
    assert c.count("cache me") == len("cache me")
    assert calls["encode"] == 1
