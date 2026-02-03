from __future__ import annotations

from pathlib import Path

import pytest

from codecrate.cli import main


def _write_repo(root: Path, filename: str, content: str) -> None:
    root.mkdir()
    (root / filename).write_text(content, encoding="utf-8")


def test_pack_multi_repos(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, "a.py", "def alpha():\n    return 1\n")
    _write_repo(repo2, "b.py", "def beta():\n    return 2\n")

    out_path = tmp_path / "multi.md"
    main(["pack", "--repo", str(repo1), "--repo", str(repo2), "-o", str(out_path)])

    text = out_path.read_text(encoding="utf-8")
    assert "# Repository: repo1" in text
    assert "# Repository: repo2" in text
    assert "def alpha()" in text
    assert "def beta()" in text


def test_pack_rejects_root_and_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, "a.py", "def alpha():\n    return 1\n")

    out_path = tmp_path / "multi.md"
    with pytest.raises(SystemExit) as excinfo:
        main(["pack", str(repo), "--repo", str(repo), "-o", str(out_path)])

    assert excinfo.value.code == 2
