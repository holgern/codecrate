from __future__ import annotations

import io
import json
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


def test_pack_stdin0_rejects_repo_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["pack", "--repo", str(repo), "--stdin0"])

    assert excinfo.value.code == 2


def test_pack_stdin_requires_non_empty_input(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(sys, "stdin", io.StringIO("\n# comment\n  \n"))
    with pytest.raises(SystemExit) as excinfo:
        main(["pack", str(tmp_path), "--stdin"])

    assert excinfo.value.code == 2


def test_pack_stdin_ignores_blank_whitespace_and_comment_lines(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(sys, "stdin", io.StringIO("\n   \n# comment\na.py\n"))
    main(["pack", str(tmp_path), "--stdin", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "### `a.py`" in text


def test_pack_stdin_normalizes_dot_slash_paths(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(sys, "stdin", io.StringIO("./a.py\n"))
    main(["pack", str(tmp_path), "--stdin", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "### `a.py`" in text


def test_pack_stdin0_requires_non_empty_input(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8")
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["pack", str(tmp_path), "--stdin0"])

    assert excinfo.value.code == 2


def test_pack_stdin_and_stdin0_are_mutually_exclusive(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["pack", str(tmp_path), "--stdin", "--stdin0"])

    assert excinfo.value.code == 2


def test_pack_stdin0_uses_explicit_files_not_include_globs(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(b"notes.txt\x00"), encoding="utf-8"),
    )
    main(
        [
            "pack",
            str(tmp_path),
            "--stdin0",
            "--include",
            "**/*.py",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `notes.txt`" in text
    assert "### `a.py`" not in text


def test_pack_stdin0_applies_ignore_rules(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".gitignore").write_text("git_ignored.py\n", encoding="utf-8")
    (tmp_path / ".codecrateignore").write_text("cc_ignored.py\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "git_ignored.py").write_text(
        "def git_ignored():\n    return 2\n", encoding="utf-8"
    )
    (tmp_path / "cc_ignored.py").write_text(
        "def cc_ignored():\n    return 3\n", encoding="utf-8"
    )
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(
            io.BytesIO(b"ok.py\x00git_ignored.py\x00cc_ignored.py\x00"),
            encoding="utf-8",
        ),
    )
    main(["pack", str(tmp_path), "--stdin0", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "### `ok.py`" in text
    assert "### `git_ignored.py`" not in text
    assert "### `cc_ignored.py`" not in text


def test_pack_stdin0_normalizes_dot_slash_paths(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(b"./a.py\x00"), encoding="utf-8"),
    )
    main(["pack", str(tmp_path), "--stdin0", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "### `a.py`" in text


def test_pack_stdin_applies_excludes(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(sys, "stdin", io.StringIO("a.py\nb.py\n"))
    main(
        [
            "pack",
            str(tmp_path),
            "--stdin",
            "--exclude",
            "b.py",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `a.py`" in text
    assert "### `b.py`" not in text


def test_pack_stdin_applies_ignore_rules(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".gitignore").write_text("git_ignored.py\n", encoding="utf-8")
    (tmp_path / ".codecrateignore").write_text("cc_ignored.py\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "git_ignored.py").write_text(
        "def git_ignored():\n    return 2\n", encoding="utf-8"
    )
    (tmp_path / "cc_ignored.py").write_text(
        "def cc_ignored():\n    return 3\n", encoding="utf-8"
    )
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO("ok.py\ngit_ignored.py\ncc_ignored.py\n"),
    )
    main(["pack", str(tmp_path), "--stdin", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "### `ok.py`" in text
    assert "### `git_ignored.py`" not in text
    assert "### `cc_ignored.py`" not in text


def test_pack_stdin_rejects_paths_outside_root(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "inside.py").write_text("def inside():\n    return 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("def outside():\n    return 2\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(f"inside.py\n{outside.as_posix()}\n"),
    )
    main(["pack", str(repo), "--stdin", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "### `inside.py`" in text
    assert "### `outside.py`" not in text


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
    assert "Top files by tokens:" in captured.err


def test_pack_max_file_bytes_skips_large_files(tmp_path: Path, capsys) -> None:
    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = 1\n" * 400, encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--include",
            "**/*.py",
            "--max-file-bytes",
            "300",
        ]
    )

    captured = capsys.readouterr()
    text = out_path.read_text(encoding="utf-8")
    assert "Warning: skipped" in captured.err
    assert "big.py" in captured.err
    assert "### `small.py`" in text
    assert "### `big.py`" not in text


def test_pack_print_files_debug_lists_selected_files(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hello\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*.py",
            "--print-files",
            "-o",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert "Debug: selected files" in captured.err
    assert "a.py" in captured.err
    assert "b.txt" not in captured.err


def test_pack_print_skipped_debug_lists_reasons(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = 1\n" * 200, encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*",
            "--max-file-bytes",
            "100",
            "--print-skipped",
            "-o",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert "Debug: skipped files" in captured.err
    assert ".env (path:.env)" in captured.err
    assert "big.py (bytes>100)" in captured.err


def test_pack_print_skipped_includes_explicit_discovery_reasons(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    (tmp_path / ".codecrateignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "excluded.py").write_text("x = 3\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("x = 4\n", encoding="utf-8")

    out_path = tmp_path / "context.md"
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "keep.py\nkeep.py\nignored.py\nexcluded.py\nmissing.py\n"
            f"{outside.as_posix()}\n"
        ),
    )

    main(
        [
            "pack",
            str(tmp_path),
            "--stdin",
            "--exclude",
            "excluded.py",
            "--print-skipped",
            "-o",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert "keep.py (duplicate)" in captured.err
    assert "ignored.py (ignored)" in captured.err
    assert "excluded.py (excluded)" in captured.err
    assert "missing.py (not-a-file)" in captured.err
    assert f"{outside.as_posix()} (outside-root)" in captured.err


def test_pack_max_total_bytes_fails_when_exceeded(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n" * 200, encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 2\n" * 200, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "pack",
                str(tmp_path),
                "--include",
                "**/*.py",
                "--max-total-bytes",
                "500",
            ]
        )

    assert "max_total_bytes" in str(excinfo.value)


def test_pack_max_file_tokens_skips_large_token_files(tmp_path: Path, capsys) -> None:
    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = 1\n" * 600, encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--include",
            "**/*.py",
            "--max-file-tokens",
            "100",
            "--token-count-tree",
        ]
    )

    captured = capsys.readouterr()
    text = out_path.read_text(encoding="utf-8")
    assert "Warning: skipped" in captured.err
    assert "tokens>100" in captured.err
    assert "### `small.py`" in text
    assert "### `big.py`" not in text


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


def test_pack_cli_no_dedupe_overrides_config_true(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def same():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def same():\n    return 1\n", encoding="utf-8")
    (tmp_path / "codecrate.toml").write_text(
        '[codecrate]\ndedupe = true\nlayout = "auto"\n',
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "--no-dedupe", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "## Function Library" not in text
    assert "↪ FUNC:v1:" not in text


def test_pack_cli_dedupe_overrides_config_false(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def same():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def same():\n    return 1\n", encoding="utf-8")
    (tmp_path / "codecrate.toml").write_text(
        '[codecrate]\ndedupe = false\nlayout = "auto"\n',
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "--dedupe", "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "## Function Library" in text
    assert "↪ FUNC:v1:" in text


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


def test_pack_security_check_skips_sensitive_files(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "--include", "*", "-o", str(out_path)])

    captured = capsys.readouterr()
    text = out_path.read_text(encoding="utf-8")
    assert "### `a.py`" in text
    assert "### `.env`" not in text
    assert "Skipped for safety: 1 file(s)" in text
    assert "safety findings" in captured.err
    assert "skipped=1" in captured.err


def test_pack_no_security_check_keeps_sensitive_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*",
            "--no-security-check",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `.env`" in text
    assert "Skipped for safety:" not in text


def test_pack_security_content_sniff_skips_private_key(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "token.txt").write_text(
        "-----BEGIN PRIVATE KEY-----\nabc\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*.txt",
            "--security-content-sniff",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `token.txt`" not in text


def test_pack_security_redaction_masks_sensitive_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*",
            "--security-redaction",
            "--safety-report",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `.env`" in text
    assert "SECRET=123" not in text
    assert "Redacted for safety: 1 file(s)" in text
    assert "## Safety Report" in text
    assert "**redacted**" in text


def test_pack_security_redaction_masks_only_content_matches(tmp_path: Path) -> None:
    (tmp_path / "token.txt").write_text(
        "token=ABC123456789\nsafe=value\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*.txt",
            "--security-content-sniff",
            "--security-redaction",
            "--security-content-pattern",
            r"token-rule=token=[A-Za-z0-9]{8,}",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `token.txt`" in text
    assert "ABC123456789" not in text
    assert "safe=value" in text


def test_pack_skips_binary_files_with_explicit_report(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*",
            "--safety-report",
            "-o",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    text = out_path.read_text(encoding="utf-8")
    assert "likely-binary" in captured.err
    assert "Skipped as binary: 1 file(s)" in text
    assert "`blob.bin` - **skipped** (binary)" in text
    assert "### `blob.bin`" not in text


def test_pack_custom_security_path_pattern_overrides_defaults(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*",
            "--security-path-pattern",
            "*.nothing",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `.env`" in text


def test_pack_custom_security_content_pattern(tmp_path: Path) -> None:
    (tmp_path / "token.txt").write_text("token=ABC123456789\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(
        [
            "pack",
            str(tmp_path),
            "--include",
            "*.txt",
            "--security-content-sniff",
            "--security-content-pattern",
            r"token-rule=token=[A-Za-z0-9]{8,}",
            "-o",
            str(out_path),
        ]
    )

    text = out_path.read_text(encoding="utf-8")
    assert "### `token.txt`" not in text


def test_pack_invalid_security_content_pattern_fails(tmp_path: Path, capsys) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "pack",
                str(tmp_path),
                "--security-content-sniff",
                "--security-content-pattern",
                "bad=[",
            ]
        )

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "invalid security rule pattern" in captured.err
    assert "Invalid content regex 'bad'" in captured.err


def test_pack_encoding_errors_strict_fails_on_invalid_utf8(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "bad.py").write_bytes(b"def x():\n    return '\xff'\n")

    with pytest.raises(SystemExit) as excinfo:
        main(["pack", str(tmp_path), "--encoding-errors", "strict"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "Failed to decode UTF-8" in captured.err


def test_pack_manifest_json_default_path(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"

    main(["pack", str(tmp_path), "-o", str(out_path), "--manifest-json"])

    manifest_json_path = tmp_path / "context.manifest.json"
    assert manifest_json_path.exists()
    payload = json.loads(manifest_json_path.read_text(encoding="utf-8"))
    assert payload["format"] == "codecrate.manifest-json.v1"
    repos = payload.get("repositories")
    assert isinstance(repos, list)
    assert len(repos) == 1
    assert "manifest" in repos[0]
    assert "manifest_sha256" in repos[0]


def test_pack_manifest_json_explicit_path(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    out_path = tmp_path / "context.md"
    json_path = tmp_path / "manifests.json"

    main(
        [
            "pack",
            str(tmp_path),
            "-o",
            str(out_path),
            "--manifest-json",
            str(json_path),
        ]
    )

    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    repos = payload.get("repositories")
    assert isinstance(repos, list)
    assert len(repos) == 1
