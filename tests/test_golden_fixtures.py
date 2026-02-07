from __future__ import annotations

from pathlib import Path

from codecrate.mdparse import parse_packed_markdown
from codecrate.unpacker import unpack_to_dir
from codecrate.validate import validate_pack_markdown

FIXTURES = Path(__file__).parent / "fixtures"
PACKS = FIXTURES / "packs"
REPOS = FIXTURES / "repos"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_golden_full_pack_parse_validate_unpack(tmp_path: Path) -> None:
    md = _read(PACKS / "golden_full.md")

    packed = parse_packed_markdown(md)
    assert packed.manifest["format"] == "codecrate.v4"

    report = validate_pack_markdown(md)
    assert report.errors == []

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)
    assert _read(out_dir / "a.py") == _read(REPOS / "golden_single" / "a.py")


def test_golden_stub_compat_pack_parse_validate_unpack(tmp_path: Path) -> None:
    md = _read(PACKS / "golden_stub_compat.md")

    packed = parse_packed_markdown(md)
    assert "DEADBEEF" in packed.canonical_sources

    report = validate_pack_markdown(md, strict=True)
    assert report.errors == []

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir, strict=True)
    assert _read(out_dir / "a.py") == _read(REPOS / "golden_stub" / "a.py")


def test_golden_combined_pack_parse_validate_unpack(tmp_path: Path) -> None:
    md = _read(PACKS / "golden_combined_multi.md")

    report = validate_pack_markdown(md)
    assert report.errors == []

    out_dir = tmp_path / "out"
    unpack_to_dir(md, out_dir)

    assert _read(out_dir / "golden-multi-repo1" / "a.py") == _read(
        REPOS / "golden_multi_repo1" / "a.py"
    )
    assert _read(out_dir / "golden-multi-repo2" / "b.py") == _read(
        REPOS / "golden_multi_repo2" / "b.py"
    )
