from __future__ import annotations

from pathlib import Path

import pytest

from codecrate.cli import main
from codecrate.repositories import split_repository_sections


def _write_repo(root: Path, filename: str, content: str) -> None:
    root.mkdir()
    (root / filename).write_text(content, encoding="utf-8")


def _rebuild_combined(sections: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    for idx, (label, content) in enumerate(sections):
        if idx:
            parts.append("\n\n")
        parts.append(f"# Repository: {label}\n\n")
        parts.append(content.rstrip() + "\n")
    return "".join(parts)


def test_unpack_combined_pack_writes_slug_subdirs(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    out_dir = tmp_path / "out"
    main(["unpack", str(packed), "-o", str(out_dir)])

    assert (out_dir / "repo1" / "a.py").read_text(encoding="utf-8") == (
        repo1 / "a.py"
    ).read_text(encoding="utf-8")
    assert (out_dir / "repo2" / "b.py").read_text(encoding="utf-8") == (
        repo2 / "b.py"
    ).read_text(encoding="utf-8")


def test_patch_combined_requires_repo(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    (repo1 / "a.py").write_text("def alpha():\n    return 10\n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        main(["patch", str(packed), str(repo1), "-o", str(tmp_path / "p1.md")])
    assert excinfo.value.code == 2


def test_patch_combined_accepts_slug_selector(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    text = packed.read_text(encoding="utf-8")
    text = text.replace("# Repository: repo1", "# Repository: repo one", 1)
    packed.write_text(text, encoding="utf-8")

    (repo1 / "a.py").write_text("def alpha():\n    return 11\n", encoding="utf-8")

    patch_path = tmp_path / "repo1.patch.md"
    main(
        [
            "patch",
            str(packed),
            str(repo1),
            "--repo",
            "repo-one",
            "-o",
            str(patch_path),
        ]
    )

    patch_text = patch_path.read_text(encoding="utf-8")
    assert patch_text.startswith("# Repository: repo one")
    assert "--- a/a.py" in patch_text
    assert "--- a/b.py" not in patch_text


def test_apply_combined_patch_requires_repo_and_applies_selected(
    tmp_path: Path,
) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    (repo1 / "a.py").write_text("def alpha():\n    return 11\n", encoding="utf-8")
    repo1_patch = tmp_path / "repo1.patch.md"
    main(
        [
            "patch",
            str(packed),
            str(repo1),
            "--repo",
            "repo1",
            "-o",
            str(repo1_patch),
        ]
    )

    (repo2 / "b.py").write_text("def beta():\n    return 22\n", encoding="utf-8")
    repo2_patch = tmp_path / "repo2.patch.md"
    main(
        [
            "patch",
            str(packed),
            str(repo2),
            "--repo",
            "repo2",
            "-o",
            str(repo2_patch),
        ]
    )

    combined_patch = tmp_path / "combined.patch.md"
    combined_patch.write_text(
        repo1_patch.read_text(encoding="utf-8").rstrip()
        + "\n\n"
        + repo2_patch.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    apply_root = tmp_path / "apply-repo1"
    _write_repo(apply_root, "a.py", "def alpha():\n    return 1\n")

    with pytest.raises(SystemExit) as excinfo:
        main(["apply", str(combined_patch), str(apply_root)])
    assert excinfo.value.code == 2

    main(["apply", str(combined_patch), str(apply_root), "--repo", "repo1"])
    assert (apply_root / "a.py").read_text(encoding="utf-8") == (
        "def alpha():\n    return 11\n"
    )
    assert not (apply_root / "b.py").exists()


def test_validate_pack_combined_scopes_errors_and_checks_anchor_collisions(
    tmp_path: Path,
    capsys,
) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    sections = split_repository_sections(packed.read_text(encoding="utf-8"))
    assert len(sections) == 2
    repo1_md = '<a id="dup-anchor"></a>\n' + sections[0].content
    repo2_md = '<a id="dup-anchor"></a>\n' + sections[1].content.replace(
        "```codecrate-manifest", "```not-a-manifest", 1
    )
    invalid = _rebuild_combined(
        [(sections[0].label, repo1_md), (sections[1].label, repo2_md)]
    )

    invalid_path = tmp_path / "invalid.md"
    invalid_path.write_text(invalid, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(invalid_path)])
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "repo 'repo2' (repo2): expected exactly one codecrate-manifest block" in (
        captured.out
    )
    assert "Cross-repo anchor collision" in captured.out
