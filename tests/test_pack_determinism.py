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


def test_split_outputs_are_deterministic_across_runs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def a():\n    return 1\n\n" + "# a\n" * 30,
            "b.py": "def b():\n    return 2\n\n" + "# b\n" * 30,
        },
    )

    out = tmp_path / "context.md"

    def run_pack() -> dict[str, bytes]:
        main(
            [
                "pack",
                str(repo),
                "-o",
                str(out),
                "--split-max-chars",
                "500",
                "--max-workers",
                "8",
            ]
        )
        part_files = sorted(tmp_path.glob("context.part*.md"))
        return {p.name: p.read_bytes() for p in part_files}

    first = run_pack()
    second = run_pack()

    assert first == second


def test_pack_output_is_deterministic_with_safety_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def a():\n    return 1\n",
            ".env": "SECRET=1\n",
            "notes.txt": "ok\n",
        },
    )

    out1 = tmp_path / "s1.md"
    out2 = tmp_path / "s2.md"

    args = [
        "pack",
        str(repo),
        "--include",
        "*",
        "--safety-report",
        "--max-workers",
        "8",
    ]
    main([*args, "-o", str(out1)])
    main([*args, "-o", str(out2)])

    assert out1.read_bytes() == out2.read_bytes()


def test_multi_repo_slug_collision_output_is_deterministic(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo one"
    repo2 = tmp_path / "repo-one"
    _write_repo(repo1, {"x.py": "def x():\n    return 1\n"})
    _write_repo(repo2, {"y.py": "def y():\n    return 2\n"})

    out1 = tmp_path / "c1.md"
    out2 = tmp_path / "c2.md"

    cmd = [
        "pack",
        "--repo",
        str(repo1),
        "--repo",
        str(repo2),
        "--max-workers",
        "8",
    ]
    main([*cmd, "-o", str(out1)])
    main([*cmd, "-o", str(out2)])

    text = out1.read_text(encoding="utf-8")
    assert "# Repository: repo one" in text
    assert "# Repository: repo-one" in text
    assert out1.read_bytes() == out2.read_bytes()
