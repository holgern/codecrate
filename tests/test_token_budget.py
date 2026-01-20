from __future__ import annotations

from pathlib import Path

from codecrate.token_budget import Part, split_by_max_chars


def test_split_by_max_chars_no_split(tmp_path: Path) -> None:
    """Test splitting when content fits in one part."""
    markdown = "Short content"
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 1000)

    assert len(parts) == 1
    assert parts[0].path == out_path
    assert parts[0].content == markdown


def test_split_by_max_chars_zero_limit(tmp_path: Path) -> None:
    """Test that zero limit means no splitting."""
    markdown = "Some content"
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 0)

    assert len(parts) == 1
    assert parts[0].content == markdown


def test_split_by_max_chars_negative_limit(tmp_path: Path) -> None:
    """Test that negative limit means no splitting."""
    markdown = "Some content"
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, -10)

    assert len(parts) == 1


def test_split_by_max_chars_requires_splitting(tmp_path: Path) -> None:
    """Test actual splitting by paragraph."""
    markdown = "Para 1\n\nPara 2\n\nPara 3\n\nPara 4"
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 10)

    assert len(parts) > 1


def test_split_by_max_chars_filenames(tmp_path: Path) -> None:
    """Test that output filenames are correct."""
    markdown = "Para 1\n\n" + "Para 2\n\n" * 10
    out_path = tmp_path / "context.md"

    parts = split_by_max_chars(markdown, out_path, 50)

    # First part is context.part1.md when splitting
    assert parts[0].path == tmp_path / "context.part1.md"
    assert parts[1].path == tmp_path / "context.part2.md"

    # Verify filename pattern
    assert ".part" in parts[0].path.name
    assert parts[1].path.name.endswith(".part2.md")


def test_split_by_max_chars_preserves_content(tmp_path: Path) -> None:
    """Test that content is preserved when joining back."""
    markdown = "Para 1\n\n" + "Para 2\n\n" * 10
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 50)

    # Join all parts back together
    reconstructed = "\n\n".join(p.content.rstrip() for p in parts)
    # Account for trailing newlines
    assert reconstructed == markdown.rstrip()


def test_split_by_max_chars_empty_content(tmp_path: Path) -> None:
    """Test splitting empty content."""
    markdown = ""
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 100)

    assert len(parts) == 1
    assert parts[0].content == ""


def test_split_by_max_chars_large_block(tmp_path: Path) -> None:
    """Test that large blocks are not split mid-block."""
    # Create a block larger than the limit
    large_block = "x" * 100
    markdown = f"Small\n\n{large_block}\\n\nSmall"
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 50)

    # The large block should stay together
    assert any(large_block in p.content for p in parts)


def test_split_by_max_chars_exact_size(tmp_path: Path) -> None:
    """Test when content exactly matches the limit."""
    markdown = "a" * 10 + "\n\n" + "b" * 10
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 13)  # "a" * 10 + \n\n

    assert len(parts) == 2


def test_part_dataclass() -> None:
    """Test Part dataclass."""
    path = Path("test.md")
    content = "content"

    part = Part(path=path, content=content)

    assert part.path == path
    assert part.content == content


def test_split_removes_trailing_whitespace(tmp_path: Path) -> None:
    """Test that trailing whitespace is removed from parts."""
    markdown = "Para 1\n\n   \n\nPara 2"
    out_path = tmp_path / "out.md"

    parts = split_by_max_chars(markdown, out_path, 100)

    for part in parts:
        assert part.content.endswith("\n") or not part.content.endswith(" ")
