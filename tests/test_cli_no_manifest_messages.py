from __future__ import annotations

from pathlib import Path

import pytest

from codecrate.cli import main


def _make_pack_without_manifest(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "--no-manifest", "-o", str(packed)])
    return repo, packed


def test_unpack_reports_consistent_no_manifest_error(tmp_path: Path, capsys) -> None:
    _repo, packed = _make_pack_without_manifest(tmp_path)
    out_dir = tmp_path / "out"

    with pytest.raises(SystemExit) as excinfo:
        main(["unpack", str(packed), "-o", str(out_dir)])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "unpack: packed markdown is missing a Manifest section" in captured.err


def test_patch_reports_consistent_no_manifest_error(tmp_path: Path, capsys) -> None:
    repo, packed = _make_pack_without_manifest(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        main(["patch", str(packed), str(repo), "-o", str(tmp_path / "patch.md")])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "patch: packed markdown is missing a Manifest section" in captured.err


def test_validate_pack_reports_consistent_no_manifest_error(
    tmp_path: Path, capsys
) -> None:
    _repo, packed = _make_pack_without_manifest(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed)])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert (
        "validate-pack: packed markdown is missing a Manifest section" in captured.err
    )
