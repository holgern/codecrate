from __future__ import annotations

from pathlib import Path

import pytest

from codecrate.packer import pack_repo


def test_pack_repo_encoding_errors_strict_fails_on_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_bytes(b"def x():\n    return '\xff'\n")

    with pytest.raises(ValueError, match="Failed to decode UTF-8"):
        pack_repo(tmp_path, [path], encoding_errors="strict")


def test_pack_repo_encoding_errors_replace_preserves_pack_behavior(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.py"
    path.write_bytes(b"def x():\n    return '\xff'\n")

    pack, canonical = pack_repo(tmp_path, [path], encoding_errors="replace")

    assert canonical
    assert "\ufffd" in pack.files[0].original_text
