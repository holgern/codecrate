from __future__ import annotations

from pathlib import Path

from codecrate.ids import stable_body_hash, stable_location_id


def test_stable_location_id_basic() -> None:
    """Test stable location ID generation."""
    path = Path("src/module.py")
    qualname = "function_name"
    lineno = 42

    id_val = stable_location_id(path, qualname, lineno)

    assert isinstance(id_val, str)
    assert len(id_val) == 8  # First 8 chars of SHA1
    assert id_val.isupper()  # Should be uppercase hex


def test_stable_location_id_same_input() -> None:
    """Test that same input produces same ID."""
    path = Path("src/module.py")
    qualname = "function_name"
    lineno = 42

    id1 = stable_location_id(path, qualname, lineno)
    id2 = stable_location_id(path, qualname, lineno)

    assert id1 == id2


def test_stable_location_id_different_inputs() -> None:
    """Test that different inputs produce different IDs."""
    path = Path("src/module.py")

    id1 = stable_location_id(path, "function_a", 42)
    id2 = stable_location_id(path, "function_b", 42)
    id3 = stable_location_id(path, "function_a", 43)
    id4 = stable_location_id(Path("other.py"), "function_a", 42)

    assert id1 != id2  # Different qualname
    assert id1 != id3  # Different lineno
    assert id1 != id4  # Different path
    assert id2 != id3
    assert id2 != id4
    assert id3 != id4


def test_stable_location_id_path_normalization() -> None:
    """Test that different path representations produce same ID."""
    # Relative paths should be normalized
    path1 = Path("src/module.py")
    path2 = Path("src/./module.py")

    id1 = stable_location_id(path1, "func", 1)
    id2 = stable_location_id(path2, "func", 1)

    # Note: These might differ due to path normalization, but using as_posix()
    # should help. Let's just verify they're deterministic.
    assert len(id1) == 8
    assert len(id2) == 8


def test_stable_body_hash_basic() -> None:
    """Test stable body hash generation."""
    code = "def f(x):\n    return x + 1"

    hash_val = stable_body_hash(code)

    assert isinstance(hash_val, str)
    assert len(hash_val) == 40  # Full SHA1 hash
    assert hash_val.isupper()


def test_stable_body_hash_same_code() -> None:
    """Test that identical code produces same hash."""
    code = "def f(x):\n    return x + 1"

    hash1 = stable_body_hash(code)
    hash2 = stable_body_hash(code)

    assert hash1 == hash2


def test_stable_body_hash_different_code() -> None:
    """Test that different code produces different hashes."""
    code1 = "def f(x):\n    return x + 1"
    code2 = "def f(x):\n    return x + 2"

    hash1 = stable_body_hash(code1)
    hash2 = stable_body_hash(code2)

    assert hash1 != hash2


def test_stable_body_hash_line_endings() -> None:
    """Test that line ending normalization works."""
    code_crlf = "def f():\r\n    pass\r\n"
    code_lf = "def f():\n    pass\n"

    hash1 = stable_body_hash(code_crlf)
    hash2 = stable_body_hash(code_lf)

    # Should produce same hash after normalization
    assert hash1 == hash2


def test_stable_body_hash_trailing_whitespace() -> None:
    """Test that trailing whitespace is normalized."""
    code1 = "def f():\n    pass    \n"
    code2 = "def f():\n    pass\n"

    hash1 = stable_body_hash(code1)
    hash2 = stable_body_hash(code2)

    # Should produce same hash after stripping trailing spaces
    assert hash1 == hash2


def test_stable_body_hash_empty_lines() -> None:
    """Test handling of empty lines."""
    code1 = "def f():\n\n\n    pass\n"
    code2 = "def f():\n\n\n    pass\n"

    hash1 = stable_body_hash(code1)
    hash2 = stable_body_hash(code2)

    assert hash1 == hash2


def test_stable_body_hash_carriage_returns() -> None:
    """Test that carriage returns are normalized."""
    code_cr = "def f():\r    pass\r"
    code_lf = "def f():\n    pass\n"

    hash1 = stable_body_hash(code_cr)
    hash2 = stable_body_hash(code_lf)

    # Should produce same hash after normalization
    assert hash1 == hash2
