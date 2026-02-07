from __future__ import annotations

from pathlib import Path

from codecrate.cli import main


def _write_repo(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_pack_output_is_deterministic_single_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def a():\n    return 1\n",
            "pkg/b.py": "def b():\n    return 2\n",
            "docs/readme.md": "# Notes\n",
        },
    )

    out1 = tmp_path / "out1.md"
    out2 = tmp_path / "out2.md"

    main(
        [
            "pack",
            str(repo),
            "-o",
            str(out1),
            "--include",
            "**/*",
            "--max-workers",
            "8",
        ]
    )
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(out2),
            "--include",
            "**/*",
            "--max-workers",
            "8",
        ]
    )

    assert out1.read_bytes() == out2.read_bytes()


def test_pack_output_is_deterministic_multi_repo(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, {"x.py": "def x():\n    return 1\n"})
    _write_repo(repo2, {"y.py": "def y():\n    return 2\n"})

    out1 = tmp_path / "multi1.md"
    out2 = tmp_path / "multi2.md"

    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "-o",
            str(out1),
            "--max-workers",
            "8",
        ]
    )
    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "-o",
            str(out2),
            "--max-workers",
            "8",
        ]
    )

    assert out1.read_bytes() == out2.read_bytes()
