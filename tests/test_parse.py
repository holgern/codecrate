from __future__ import annotations

from pathlib import Path

from codecrate.parse import module_name_for, parse_defs


def test_module_name_for_simple() -> None:
    """Test module name for simple file."""
    root = Path("/project")
    path = Path("/project/module.py")

    name = module_name_for(path, root)

    assert name == "module"


def test_module_name_for_nested() -> None:
    """Test module name for nested file."""
    root = Path("/project")
    path = Path("/project/sub1/sub2/module.py")

    name = module_name_for(path, root)

    assert name == "sub1.sub2.module"


def test_module_name_for_init() -> None:
    """Test module name for __init__.py."""
    root = Path("/project")
    path = Path("/project/sub/__init__.py")

    name = module_name_for(path, root)

    assert name == "sub"


def test_module_name_for_root_init() -> None:
    """Test module name for root __init__.py."""
    root = Path("/project")
    path = Path("/project/__init__.py")

    name = module_name_for(path, root)

    assert name == ""


def test_parse_defs_simple_function() -> None:
    """Test parsing a simple function."""
    code = "def f(x):\n    return x\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].qualname == "f"
    assert defs[0].kind == "function"
    assert defs[0].def_line == 1
    assert defs[0].body_start == 2
    assert defs[0].end_line == 2


def test_parse_defs_function_with_docstring() -> None:
    """Test parsing a function with docstring."""
    code = 'def f(x):\n    """A docstring."""\n    return x\n'
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].doc_start == 2
    assert defs[0].doc_end == 2


def test_parse_defs_class_with_method() -> None:
    """Test parsing a class with a method."""
    code = "class C:\n    def m(self):\n        return 42\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].qualname == "C.m"
    assert defs[0].kind == "function"


def test_parse_defs_multiple_functions() -> None:
    """Test parsing multiple functions."""
    code = "def f1(): pass\ndef f2(): pass\ndef f3(): pass\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 3
    assert [d.qualname for d in defs] == ["f1", "f2", "f3"]


def test_parse_defs_async_function() -> None:
    """Test parsing async function."""
    code = "async def f(): pass\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].kind == "async_function"


def test_parse_defs_decorated_function() -> None:
    """Test parsing decorated function."""
    code = "@property\ndef f(self): return 42\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].decorator_start == 1
    assert defs[0].def_line == 2


def test_parse_defs_single_line_function() -> None:
    """Test parsing single-line function."""
    code = "def f(): return 42\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].is_single_line is True


def test_parse_defs_nested_classes() -> None:
    """Test parsing nested classes."""
    code = "class Outer:\n    class Inner:\n        def m(self): pass\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].qualname == "Outer.Inner.m"


def test_parse_defs_module_name() -> None:
    """Test that module name is correctly derived."""
    root = Path("/project")
    path = Path("/project/sub/module.py")
    code = "def f(): pass\n"

    defs = parse_defs(path, root, code)

    assert defs[0].module == "sub.module"


def test_parse_defs_empty_file() -> None:
    """Test parsing empty file."""
    defs = parse_defs(Path("test.py"), Path("/"), "")

    assert len(defs) == 0


def test_parse_defs_only_imports() -> None:
    """Test parsing file with only imports."""
    code = "import os\nimport sys\n"
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 0


def test_parse_defs_complex_docstring() -> None:
    """Test parsing function with multi-line docstring."""
    code = 'def f():\n    """Line 1.\n    Line 2.\n    Line 3."""\n    pass\n'
    defs = parse_defs(Path("test.py"), Path("/"), code)

    assert len(defs) == 1
    assert defs[0].doc_start == 2
    assert defs[0].doc_end == 4
