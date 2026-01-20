from __future__ import annotations

from pathlib import Path

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

    disc = discover_python_files(root, include=["**/*.py"], exclude=[], respect_gitignore=False)
    pack, canon = pack_repo(disc.root, disc.files, keep_docstrings=True, dedupe=False)
    md = render_markdown(pack, canon)

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)

    assert (out_dir / "a.py").read_text(encoding="utf-8") == (root / "a.py").read_text(encoding="utf-8")

