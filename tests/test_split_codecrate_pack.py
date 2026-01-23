from __future__ import annotations

from pathlib import Path

from codecrate.packer import pack_repo
from codecrate.markdown import render_markdown
from codecrate.token_budget import split_by_max_chars


def _count_fence_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.startswith("```"))


def test_split_codecrate_pack_rewrites_symbol_index_links(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    (root / "a.py").write_text(
        "def alpha():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (root / "b.py").write_text(
        "def beta():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    pack, canonical = pack_repo(root, [root / "a.py", root / "b.py"])
    md = render_markdown(pack, canonical, layout="full")

    out_path = tmp_path / "context.md"
    parts = split_by_max_chars(md, out_path, max_chars=400)

    assert len(parts) >= 2
    index = parts[0].content

    assert "(L" not in index
    assert ".part" in index and "#src-" in index

    content = "\n".join(p.content for p in parts[1:])
    assert "jump to index](" in content
    assert parts[0].path.name in content

    for p in parts:
        assert _count_fence_lines(p.content) % 2 == 0


def test_split_codecrate_pack_rewrites_func_links_in_stub_layout(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    (root / "x.py").write_text(
        "def f():\n"
        "    return 123\n\n"
        "def g():\n"
        "    return 456\n",
        encoding="utf-8",
    )

    pack, canonical = pack_repo(root, [root / "x.py"])
    md = render_markdown(pack, canonical, layout="stubs")

    out_path = tmp_path / "context.md"
    parts = split_by_max_chars(md, out_path, max_chars=350)

    assert len(parts) >= 2
    index = parts[0].content

    assert "(#func-" not in index
    assert ".part" in index and "#func-" in index

    content = "\n".join(p.content for p in parts[1:])
    assert "(#func-" not in content
    assert ".part" in content and "#func-" in content

    for p in parts:
        assert _count_fence_lines(p.content) % 2 == 0
