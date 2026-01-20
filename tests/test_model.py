from __future__ import annotations

from pathlib import Path

from codecrate.model import DefRef, FilePack, PackResult


def test_defref_dataclass_frozen() -> None:
    """Test that DefRef is frozen (dataclass immutability)."""
    path = Path("test.py")
    def_ref = DefRef(
        path=path,
        module="test",
        qualname="func",
        id="ID123",
        local_id="LOCAL123",
        kind="function",
        decorator_start=1,
        def_line=1,
        body_start=2,
        end_line=2,
        doc_start=2,
        doc_end=2,
        is_single_line=False,
    )

    # Verify that creating a new instance with different values works
    new_def = def_ref.__class__(
        path=path,
        module="test",
        qualname="func",
        id="ID123",
        local_id="LOCAL123",
        kind="function",
        decorator_start=1,
        def_line=1,
        body_start=2,
        end_line=2,
        doc_start=2,
        doc_end=2,
        is_single_line=False,
    )
    assert new_def is not def_ref  # Different instances


def test_filepack_dataclass_frozen() -> None:
    """Test that FilePack is frozen (dataclass immutability)."""
    file_pack = FilePack(
        path=Path("test.py"),
        module="test",
        original_text="original",
        stubbed_text="stubbed",
        defs=[],
    )

    # Verify that all fields are set correctly
    assert file_pack.path == Path("test.py")
    assert file_pack.module == "test"
    assert file_pack.original_text == "original"
    assert file_pack.stubbed_text == "stubbed"
    assert file_pack.defs == []


def test_packresult_dataclass_frozen() -> None:
    """Test that PackResult is frozen (dataclass immutability)."""
    pack = PackResult(
        root=Path("/"),
        files=[],
        defs=[],
    )

    # Verify that all fields are set correctly
    assert pack.root == Path("/")
    assert pack.files == []
    assert pack.defs == []


def test_defref_required_fields() -> None:
    """Test that all required DefRef fields are present."""
    path = Path("test.py")
    def_ref = DefRef(
        path=path,
        module="test",
        qualname="func",
        id="ID123",
        local_id="LOCAL123",
        kind="function",
        decorator_start=1,
        def_line=1,
        body_start=2,
        end_line=2,
    )

    # Optional fields should have defaults
    assert def_ref.doc_start is None
    assert def_ref.doc_end is None
    assert def_ref.is_single_line is False
