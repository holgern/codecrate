from __future__ import annotations

from pathlib import Path

from codecrate.config import Config, load_config


def test_config_defaults() -> None:
    """Test that Config has correct default values."""
    cfg = Config()
    assert cfg.keep_docstrings is True
    assert cfg.dedupe is False
    assert cfg.respect_gitignore is True
    assert cfg.include == ["**/*.py"]
    assert cfg.exclude == []
    assert cfg.split_max_chars == 0


def test_load_config_missing_file(tmp_path: Path) -> None:
    """Test loading config when file doesn't exist."""
    cfg = load_config(tmp_path)
    assert cfg.keep_docstrings is True
    assert cfg.dedupe is False


def test_load_config_empty_file(tmp_path: Path) -> None:
    """Test loading config from empty file."""
    (tmp_path / "codecrate.toml").write_text("", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.keep_docstrings is True
    assert cfg.dedupe is False


def test_load_config_custom_values(tmp_path: Path) -> None:
    """Test loading config with custom values."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
keep_docstrings = false
dedupe = true
respect_gitignore = false
include = ["src/**/*.py"]
exclude = ["tests/**"]
split_max_chars = 100000
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.keep_docstrings is False
    assert cfg.dedupe is True
    assert cfg.respect_gitignore is False
    assert cfg.include == ["src/**/*.py"]
    assert cfg.exclude == ["tests/**"]
    assert cfg.split_max_chars == 100000


def test_load_config_partial_values(tmp_path: Path) -> None:
    """Test loading config with only some values overridden."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
keep_docstrings = false
split_max_chars = 50000
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.keep_docstrings is False
    assert cfg.dedupe is False  # Should use default
    assert cfg.respect_gitignore is True  # Should use default
    assert cfg.split_max_chars == 50000


def test_load_config_invalid_include_exclude(tmp_path: Path) -> None:
    """Test loading config with invalid include/exclude types."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
include = "not a list"
exclude = 123
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    # Should fall back to defaults when invalid
    assert cfg.include == ["**/*.py"]
    assert cfg.exclude == []


def test_load_config_invalid_split_max_chars(tmp_path: Path) -> None:
    """Test loading config with invalid split_max_chars value."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
split_max_chars = "not a number"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.split_max_chars == 0  # Should use default


def test_load_config_toml_without_codecrate_section(tmp_path: Path) -> None:
    """Test loading config from TOML without codecrate section."""
    (tmp_path / "codecrate.toml").write_text(
        """[other_section]
value = "something"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.keep_docstrings is True  # Should use defaults
