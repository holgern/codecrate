from __future__ import annotations

from pathlib import Path

from codecrate.parse import module_name_for, parse_symbols


def _parse(
    code: str, *, path: Path = Path("test.py"), root: Path = Path("/")
):
    return parse_symbols(path, root, code)


def test_module_name_for_simple() -> None:
    root = Path("/project")
    path = Path("/project/module.py")

    assert module_name_for(path, root) == "module"


def test_module_name_for_nested() -> None:
    root = Path("/project")
    path = Path("/project/sub1/sub2/module.py")

    assert module_name_for(path, root) == "sub1.sub2.module"


def test_module_name_for_init() -> None:
    root = Path("/project")
    path = Path("/project/sub/__init__.py")

    assert module_name_for(path, root) == "sub"


def test_module_name_for_root_init() -> None:
    root = Path("/project")
    path = Path("/project/__init__.py")

    assert module_name_for(path, root) == ""


def test_parse_symbols_simple_function() -> None:
    result = _parse("def f(x):\n    return x\n")

    assert result.classes == []
    assert len(result.defs) == 1
    assert result.defs[0].qualname == "f"
    assert result.defs[0].kind == "function"
    assert result.defs[0].def_line == 1
    assert result.defs[0].body_start == 2
    assert result.defs[0].end_line == 2
    assert result.defs[0].owner_class is None


def test_parse_symbols_function_with_docstring() -> None:
    result = _parse('def f(x):\n    """A docstring."""\n    return x\n')

    assert len(result.defs) == 1
    assert result.defs[0].doc_start == 2
    assert result.defs[0].doc_end == 2


def test_parse_symbols_class_with_method() -> None:
    result = _parse("class C:\n    def m(self):\n        return 42\n")

    assert len(result.classes) == 1
    assert len(result.defs) == 1
    assert result.classes[0].qualname == "C"
    assert result.defs[0].qualname == "C.m"
    assert result.defs[0].kind == "function"
    assert result.defs[0].owner_class == "C"


def test_parse_symbols_multiple_functions() -> None:
    result = _parse("def f1(): pass\ndef f2(): pass\ndef f3(): pass\n")

    assert len(result.defs) == 3
    assert [d.qualname for d in result.defs] == ["f1", "f2", "f3"]


def test_parse_symbols_async_function() -> None:
    result = _parse("async def f(): pass\n")

    assert len(result.defs) == 1
    assert result.defs[0].kind == "async_function"


def test_parse_symbols_decorated_function() -> None:
    result = _parse("@cache\n@property\ndef f(self): return 42\n")

    assert len(result.defs) == 1
    assert result.defs[0].decorator_start == 1
    assert result.defs[0].def_line == 3
    assert result.defs[0].decorators == ["cache", "property"]


def test_parse_symbols_single_line_function() -> None:
    result = _parse("def f(): return 42\n")

    assert len(result.defs) == 1
    assert result.defs[0].is_single_line is True


def test_parse_symbols_nested_classes() -> None:
    result = _parse("class Outer:\n    class Inner:\n        def m(self): pass\n")

    assert len(result.classes) == 2
    assert len(result.defs) == 1
    assert [c.qualname for c in result.classes] == ["Outer", "Outer.Inner"]
    assert result.defs[0].qualname == "Outer.Inner.m"
    assert result.defs[0].owner_class == "Outer.Inner"


def test_parse_symbols_module_name() -> None:
    root = Path("/project")
    path = Path("/project/sub/module.py")
    result = _parse("def f(): pass\n", path=path, root=root)

    assert result.module == "sub.module"
    assert result.defs[0].module == "sub.module"


def test_parse_symbols_empty_file() -> None:
    result = _parse("")

    assert result.classes == []
    assert result.defs == []
    assert result.imports == []
    assert result.exports == []
    assert result.module_docstring is None


def test_parse_symbols_only_imports() -> None:
    result = _parse("import os\nfrom pkg import name as alias\n")

    assert result.classes == []
    assert result.defs == []
    assert result.imports == [
        result.imports[0].__class__(
            module="os",
            imported_name=None,
            alias=None,
            line=1,
            kind="import",
        ),
        result.imports[1].__class__(
            module="pkg",
            imported_name="name",
            alias="alias",
            line=2,
            kind="from",
        ),
    ]


def test_parse_symbols_complex_docstring() -> None:
    result = _parse('def f():\n    """Line 1.\n    Line 2.\n    Line 3."""\n    pass\n')

    assert len(result.defs) == 1
    assert result.defs[0].doc_start == 2
    assert result.defs[0].doc_end == 4


def test_parse_symbols_decorated_class() -> None:
    result = _parse("@dataclass\nclass C:\n    pass\n")

    assert len(result.classes) == 1
    assert result.classes[0].qualname == "C"
    assert result.classes[0].decorator_start == 1
    assert result.classes[0].decorators == ["dataclass"]


def test_parse_symbols_module_semantics() -> None:
    result = _parse(
        '"""Module docs."""\n'
        "import os\n"
        "from .pkg import thing as alias\n"
        '__all__ = ["alpha"] + ("beta",)\n'
        "@decorator\n"
        "class C(BaseOne, pkg.BaseTwo):\n"
        "    pass\n"
    )

    assert result.module_docstring == (1, 1)
    assert result.exports == ["alpha", "beta"]
    assert [imp.module for imp in result.imports] == ["os", ".pkg"]
    assert result.imports[1].imported_name == "thing"
    assert result.imports[1].alias == "alias"
    assert result.classes[0].base_classes == ["BaseOne", "pkg.BaseTwo"]
    assert result.classes[0].decorators == ["decorator"]
