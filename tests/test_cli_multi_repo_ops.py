from __future__ import annotations

import json
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


def _count_fence_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.startswith("```"))


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


def test_unpack_combined_pack_crlf_markdown_is_stable(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    # Simulate Windows-style line endings in the combined markdown file.
    text = packed.read_text(encoding="utf-8")
    packed.write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="")

    out_dir = tmp_path / "out"
    main(["unpack", str(packed), "-o", str(out_dir)])

    assert (out_dir / "repo1" / "a.py").read_text(encoding="utf-8") == (
        repo1 / "a.py"
    ).read_text(encoding="utf-8")
    assert (out_dir / "repo2" / "b.py").read_text(encoding="utf-8") == (
        repo2 / "b.py"
    ).read_text(encoding="utf-8")


def test_unpack_combined_pack_duplicate_labels_use_unique_slug_dirs(
    tmp_path: Path,
) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    packed = tmp_path / "combined.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(packed)])

    text = packed.read_text(encoding="utf-8")
    text = text.replace("# Repository: repo1", "# Repository: shared", 1)
    text = text.replace("# Repository: repo2", "# Repository: shared", 1)
    packed.write_text(text, encoding="utf-8")

    out_dir = tmp_path / "out"
    main(["unpack", str(packed), "-o", str(out_dir)])

    assert (out_dir / "shared" / "a.py").read_text(encoding="utf-8") == (
        repo1 / "a.py"
    ).read_text(encoding="utf-8")
    assert (out_dir / "shared-2" / "b.py").read_text(encoding="utf-8") == (
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
    assert "[repo 'repo2' (repo2)]" in captured.out
    assert "expected exactly one codecrate-manifest block" in captured.out
    assert "hint:" in captured.out
    assert "Cross-repo anchor collision" in captured.out


def test_validate_pack_detects_machine_header_manifest_checksum_mismatch(
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, "a.py", "def alpha():\n    return 1\n")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed)])

    text = packed.read_text(encoding="utf-8")
    tampered = text.replace('"manifest_sha256":"', '"manifest_sha256":"BAD', 1)
    packed.write_text(tampered, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed)])
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "Machine header checksum mismatch" in captured.out
    assert "hint: manifest content changed" in captured.out


def test_validate_pack_json_output(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, "a.py", "def alpha():\n    return 1\n")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed)])

    main(["validate-pack", str(packed), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["error_count"] == 0
    assert payload["warning_count"] == 0


def test_validate_pack_json_output_on_error(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, "a.py", "def alpha():\n    return 1\n")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed)])

    text = packed.read_text(encoding="utf-8")
    tampered = text.replace('"format": "codecrate.v4"', '"format": "codecrate.v0"', 1)
    packed.write_text(tampered, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed), "--json"])
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["error_count"] >= 1


def test_pack_multi_repo_manifest_json_contains_all_sections(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    out_md = tmp_path / "combined.md"
    out_json = tmp_path / "combined.manifest.json"
    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "-o",
            str(out_md),
            "--manifest-json",
            str(out_json),
        ]
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["format"] == "codecrate.manifest-json.v1"
    repos = payload.get("repositories")
    assert isinstance(repos, list)
    assert len(repos) == 2
    assert {repo.get("slug") for repo in repos} == {"repo1", "repo2"}


def test_pack_multi_repo_split_preserves_repo_boundaries_and_fences(
    tmp_path: Path,
) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(
        repo1,
        "a.py",
        "def alpha():\n    return 1\n\n" + "# comment\n" * 40,
    )
    _write_repo(
        repo2,
        "b.py",
        "def beta():\n    return 2\n\n" + "# note\n" * 40,
    )

    packed = tmp_path / "combined.md"
    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "--split-max-chars",
            "500",
            "-o",
            str(packed),
        ]
    )

    repo1_parts = sorted(tmp_path.glob("combined.repo1.part*.md"))
    repo2_parts = sorted(tmp_path.glob("combined.repo2.part*.md"))
    assert repo1_parts
    assert repo2_parts

    repo1_text = "\n".join(p.read_text(encoding="utf-8") for p in repo1_parts)
    repo2_text = "\n".join(p.read_text(encoding="utf-8") for p in repo2_parts)
    assert "`a.py`" in repo1_text
    assert "`b.py`" not in repo1_text
    assert "`b.py`" in repo2_text
    assert "`a.py`" not in repo2_text

    for part in repo1_parts + repo2_parts:
        assert _count_fence_lines(part.read_text(encoding="utf-8")) % 2 == 0
