from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from codecrate.cli import main
from codecrate.tokens import TokenCounter


def test_pack_stdin_uses_explicit_files_not_include_globs(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(sys, "stdin", io.StringIO("notes.txt\n"))
    main(
        [
            "pack",
            str(tmp_path),
            "--stdin",
            "--include",
            "**/*.py",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `notes.txt`" in text
    assert "### `a.py`" not in text


def test_pack_stdin_rejects_repo_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["pack", "--repo", str(repo), "--stdin"])

    assert excinfo.value.code == 2


def test_pack_stdin_requires_non_empty_input(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(sys, "stdin", io.StringIO("\n# comment\n  \n"))
    with pytest.raises(SystemExit) as excinfo:
        main(["pack", str(tmp_path), "--stdin"])

    assert excinfo.value.code == 2


def test_pack_invalid_token_encoding_does_not_crash(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    def _raise_count_error(self: TokenCounter, text: str) -> int:
        raise ValueError("unknown encoding")

    monkeypatch.setattr(TokenCounter, "count", _raise_count_error)

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--top-files-len",
            "3",
            "--token-count-encoding",
            "bad_encoding",
        ]
    )

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "Warning: token counting disabled" in captured.err


def test_pack_token_count_tree_writes_context(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--token-count-tree"])

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "Token counts for" in captured.err
    assert "Token Count Tree" in captured.err
    assert "Pack Summary" in captured.err
    assert "Total Files" in captured.err
    assert "Total Tokens" in captured.err
    assert "Total Chars" in captured.err


def test_pack_prints_summary_without_token_flags(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path)])

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "Pack Summary" in captured.err
    assert "Total Files" in captured.err


def test_pack_no_file_summary_suppresses_summary(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--token-count-tree",
            "--no-file-summary",
        ]
    )

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "Token counts for" in captured.err
    assert "Pack Summary" not in captured.err


def test_pack_file_summary_respects_config_default(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
file_summary = false
""",
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path)])

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "Pack Summary" not in captured.err


def test_pack_nav_mode_auto_unsplit_is_compact(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert '<a id="src-' not in text
    assert "[jump to index](#file-" not in text


def test_pack_nav_mode_full_keeps_file_navigation(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--nav-mode", "full"])

    text = out_path.read_text(encoding="utf-8")
    assert '<a id="src-' in text
    assert "[jump to index](#file-" in text


def test_pack_nav_mode_auto_with_split_is_full(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--split-max-chars", "80"])

    text = out_path.read_text(encoding="utf-8")
    assert '<a id="src-' in text
    assert "[jump to index](#file-" in text


def test_pack_token_count_tree_before_root_recovers_root(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            "--token-count-tree",
            str(tmp_path),
            "-o",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "Token counts for" in captured.err


def test_pack_token_count_tree_threshold_filters_tree(tmp_path: Path, capsys) -> None:
    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text(
        "\n".join(f"x{i} = {i}" for i in range(400)) + "\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--token-count-tree",
            "100",
            "--top-files-len",
            "0",
        ]
    )

    captured = capsys.readouterr()
    assert out_path.exists()
    assert "threshold=100" in captured.err
    assert "big.py" in captured.err
    assert "small.py" not in captured.err
