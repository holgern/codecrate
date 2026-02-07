from __future__ import annotations

from pathlib import Path

from codecrate.cli import main
from codecrate.validate import validate_pack_markdown


def _mutate_fence_openers(text: str) -> str:
    out = text
    out = out.replace(
        "```codecrate-machine-header",
        "```   codecrate-machine-header extra",
        1,
    )
    out = out.replace(
        "```codecrate-manifest",
        "```   codecrate-manifest extra-tokens",
        1,
    )
    out = out.replace("```python", "```   python extra", 1)
    return out


def test_unpack_tolerates_fence_whitespace_and_extra_tokens(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--layout", "stubs"])

    text = packed.read_text(encoding="utf-8")
    packed.write_text(_mutate_fence_openers(text), encoding="utf-8")

    out_dir = tmp_path / "out"
    main(["unpack", str(packed), "-o", str(out_dir)])
    assert (out_dir / "a.py").read_text(encoding="utf-8") == (repo / "a.py").read_text(
        encoding="utf-8"
    )


def test_validate_tolerates_fence_whitespace_and_extra_tokens(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--layout", "stubs"])

    text = packed.read_text(encoding="utf-8")
    report = validate_pack_markdown(_mutate_fence_openers(text))
    assert report.errors == []


def test_apply_tolerates_diff_fence_whitespace_and_extra_tokens(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "a.py"
    target.write_text("a\nb\n", encoding="utf-8")

    patch_md = tmp_path / "patch.md"
    patch_md.write_text(
        "# Codecrate Patch\n\n"
        "```   diff extra\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,2 +1,2 @@\n"
        " a\n"
        "-b\n"
        "+B\n"
        "```\n",
        encoding="utf-8",
    )

    main(["apply", str(patch_md), str(root)])
    assert target.read_text(encoding="utf-8") == "a\nB\n"


def test_patch_tolerates_fence_whitespace_and_extra_tokens(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--layout", "stubs"])
    text = packed.read_text(encoding="utf-8")
    packed.write_text(_mutate_fence_openers(text), encoding="utf-8")

    (repo / "a.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    patch_md = tmp_path / "patch.md"
    main(["patch", str(packed), str(repo), "-o", str(patch_md)])

    patch_text = patch_md.read_text(encoding="utf-8")
    assert "```diff" in patch_text
    assert "+    return 2" in patch_text
