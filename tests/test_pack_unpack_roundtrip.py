from __future__ import annotations

import re
from pathlib import Path

import pytest

from codecrate.cli import main
from codecrate.discover import discover_python_files
from codecrate.markdown import render_markdown
from codecrate.packer import pack_repo
from codecrate.unpacker import unpack_to_dir


def test_pack_unpack_roundtrip(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(
        "def f(x):\n"
        "    return x + 1\n"
        "\n"
        "class C:\n"
        "    def m(self):\n"
        "        return 42\n",
        encoding="utf-8",
    )

    disc = discover_python_files(
        root, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    md = render_markdown(pack, canon)

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)

    assert (out_dir / "a.py").read_text(encoding="utf-8") == (root / "a.py").read_text(
        encoding="utf-8"
    )


def test_unpack_checks_machine_header_when_requested(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(root), "-o", str(packed), "--profile", "portable"])

    out_dir = tmp_path / "out"
    unpack_to_dir(
        packed.read_text(encoding="utf-8"),
        out_dir,
        check_machine_header=True,
    )

    assert (out_dir / "a.py").read_text(encoding="utf-8") == (root / "a.py").read_text(
        encoding="utf-8"
    )


def test_unpack_rejects_corrupt_machine_header_before_writing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(root), "-o", str(packed), "--profile", "portable"])
    text = packed.read_text(encoding="utf-8")
    match = re.search(r'"manifest_sha256":\s*"([0-9a-f]{64})"', text)
    assert match is not None
    tampered = text.replace(match.group(1), "0" * 64, 1)

    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="Machine header checksum mismatch"):
        unpack_to_dir(tampered, out_dir, check_machine_header=True)

    assert not out_dir.exists()


def test_cli_unpack_rejects_missing_machine_header_when_requested(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(root), "-o", str(packed), "--profile", "portable"])
    packed.write_text(
        packed.read_text(encoding="utf-8").replace(
            "```codecrate-machine-header", "```json", 1
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="no machine header found"):
        main(
            [
                "unpack",
                str(packed),
                "-o",
                str(out_dir),
                "--check-machine-header",
            ]
        )

    assert not out_dir.exists()


def test_pack_unpack_roundtrip_nested_defs(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(
        "def outer(x):\n"
        "    def inner(y):\n"
        "        return y + 1\n"
        "    return inner(x)\n"
        "\n"
        "def after(z):\n"
        "    return z * 2\n",
        encoding="utf-8",
    )

    disc = discover_python_files(
        root, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    md = render_markdown(pack, canon)

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)

    assert (out_dir / "a.py").read_text(encoding="utf-8") == (root / "a.py").read_text(
        encoding="utf-8"
    )


def test_pack_unpack_roundtrip_dedupe_duplicate_funcs(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text(
        "def f():\n    return 1\n\ndef g():\n    return 1\n",
        encoding="utf-8",
    )

    disc = discover_python_files(
        root, include=["**/*.py"], exclude=[], respect_gitignore=False
    )
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=True)
    md = render_markdown(pack, canon)

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)

    assert (out_dir / "a.py").read_text(encoding="utf-8") == (root / "a.py").read_text(
        encoding="utf-8"
    )


def test_pack_unpack_roundtrip_with_embedded_backticks(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# Title\n\n````\ninside\n````\n",
        encoding="utf-8",
    )

    pack, canon = pack_repo(
        root,
        [root / "a.py", root / "README.md"],
        keep_docstrings=True,
        dedupe=False,
    )
    md = render_markdown(pack, canon)

    # The wrapper fence must be longer than the longest run in content.
    assert "`````markdown" in md

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)

    assert (out_dir / "README.md").read_text(encoding="utf-8") == (
        root / "README.md"
    ).read_text(encoding="utf-8")


def test_unpack_portable_roundtrip_with_markdown_headings_in_file_content(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "# AGENTS.md\n\n"
        "## Repository Overview\n\n"
        "- Project: codecrate\n\n"
        "## Build, Lint, Format, Test Commands\n\n"
        "- pytest\n",
        encoding="utf-8",
    )

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(root),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--include",
            "**/*.py",
            "--include",
            "**/*.md",
        ]
    )

    out_dir = tmp_path / "out"
    unpack_to_dir(packed.read_text(encoding="utf-8"), out_dir)

    assert (out_dir / "a.py").read_text(encoding="utf-8") == (root / "a.py").read_text(
        encoding="utf-8"
    )
    assert (out_dir / "AGENTS.md").read_text(encoding="utf-8") == (
        root / "AGENTS.md"
    ).read_text(encoding="utf-8")
