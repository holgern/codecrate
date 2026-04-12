from __future__ import annotations

from pathlib import Path

from codecrate.model import (
    ClassRef,
    DefRef,
    FilePack,
    ImportRef,
    PackResult,
    ParseResult,
)


def test_defref_supports_semantic_fields() -> None:
    def_ref = DefRef(
        path=Path("test.py"),
        module="test",
        qualname="MyClass.func",
        id="ID123",
        local_id="LOCAL123",
        kind="function",
        decorator_start=1,
        def_line=2,
        body_start=3,
        end_line=4,
        doc_start=3,
        doc_end=3,
        is_single_line=False,
        decorators=["cached_property"],
        owner_class="MyClass",
    )

    assert def_ref.decorators == ["cached_property"]
    assert def_ref.owner_class == "MyClass"


def test_classref_supports_semantic_fields() -> None:
    class_ref = ClassRef(
        path=Path("test.py"),
        module="test",
        qualname="MyClass",
        id="CLASS123",
        decorator_start=1,
        class_line=2,
        end_line=6,
        base_classes=["Base"],
        decorators=["dataclass"],
    )

    assert class_ref.base_classes == ["Base"]
    assert class_ref.decorators == ["dataclass"]


def test_importref_fields() -> None:
    import_ref = ImportRef(
        module="pkg.sub",
        imported_name="thing",
        alias="alias",
        line=3,
        kind="from",
    )

    assert import_ref.module == "pkg.sub"
    assert import_ref.imported_name == "thing"
    assert import_ref.alias == "alias"
    assert import_ref.line == 3
    assert import_ref.kind == "from"


def test_filepack_and_parse_result_defaults() -> None:
    import_ref = ImportRef(
        module="os",
        imported_name=None,
        alias=None,
        line=1,
        kind="import",
    )
    def_ref = DefRef(
        path=Path("test.py"),
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
    class_ref = ClassRef(
        path=Path("test.py"),
        module="test",
        qualname="MyClass",
        id="CLASS123",
        decorator_start=1,
        class_line=3,
        end_line=5,
    )

    file_pack = FilePack(
        path=Path("test.py"),
        module="test",
        original_text="original",
        stubbed_text="stubbed",
        line_count=1,
        classes=[class_ref],
        defs=[def_ref],
        imports=[import_ref],
        exports=["func"],
        module_docstring=(1, 1),
    )
    parse_result = ParseResult(
        module="test",
        classes=[class_ref],
        defs=[def_ref],
        imports=[import_ref],
        exports=["func"],
        module_docstring=(1, 1),
    )

    assert file_pack.imports == [import_ref]
    assert file_pack.exports == ["func"]
    assert file_pack.module_docstring == (1, 1)
    assert parse_result.imports == [import_ref]
    assert parse_result.exports == ["func"]
    assert parse_result.module_docstring == (1, 1)


def test_packresult_dataclass_fields() -> None:
    pack = PackResult(root=Path("/"), files=[], classes=[], defs=[])

    assert pack.root == Path("/")
    assert pack.files == []
    assert pack.classes == []
    assert pack.defs == []
