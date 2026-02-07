from __future__ import annotations

from pathlib import Path

from codecrate.config import DEFAULT_INCLUDES, Config, load_config


def test_config_defaults() -> None:
    """Test that Config has correct default values."""
    cfg = Config()
    assert cfg.output == "context.md"
    assert cfg.keep_docstrings is True
    assert cfg.dedupe is False
    assert cfg.respect_gitignore is True
    assert cfg.include == DEFAULT_INCLUDES
    assert cfg.exclude == []
    assert cfg.split_max_chars == 0
    assert cfg.manifest is True
    assert cfg.layout == "auto"
    assert cfg.token_count_encoding == "o200k_base"
    assert cfg.token_count_tree is False
    assert cfg.token_count_tree_threshold == 0
    assert cfg.top_files_len == 5
    assert cfg.max_file_bytes == 0
    assert cfg.max_total_bytes == 0
    assert cfg.max_file_tokens == 0
    assert cfg.max_total_tokens == 0
    assert cfg.max_workers == 0
    assert cfg.file_summary is True
    assert cfg.security_check is True
    assert cfg.security_content_sniff is False
    assert cfg.nav_mode == "auto"
    assert cfg.symbol_backend == "auto"


def test_load_config_missing_file(tmp_path: Path) -> None:
    """Test loading config when file doesn't exist."""
    cfg = load_config(tmp_path)
    assert cfg.output == "context.md"
    assert cfg.keep_docstrings is True
    assert cfg.dedupe is False


def test_load_config_empty_file(tmp_path: Path) -> None:
    """Test loading config from empty file."""
    (tmp_path / "codecrate.toml").write_text("", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.output == "context.md"
    assert cfg.keep_docstrings is True
    assert cfg.dedupe is False


def test_load_config_custom_values(tmp_path: Path) -> None:
    """Test loading config with custom values."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
output = "my_context.md"
keep_docstrings = false
dedupe = true
manifest = false
respect_gitignore = false
include = ["src/**/*.py"]
exclude = ["tests/**"]
split_max_chars = 100000
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.output == "my_context.md"
    assert cfg.keep_docstrings is False
    assert cfg.dedupe is True
    assert cfg.manifest is False
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


def test_load_config_token_count_values(tmp_path: Path) -> None:
    """Test loading config with token diagnostics values."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
token_count_encoding = "cl100k_base"
token_count_tree = true
token_count_tree_threshold = 42
top_files_len = 12
max_file_bytes = 1000
max_total_bytes = 5000
max_file_tokens = 300
max_total_tokens = 1200
max_workers = 6
file_summary = false
security_check = false
security_content_sniff = true
nav_mode = "compact"
symbol_backend = "tree-sitter"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.token_count_encoding == "cl100k_base"
    assert cfg.token_count_tree is True
    assert cfg.token_count_tree_threshold == 42
    assert cfg.top_files_len == 12
    assert cfg.max_file_bytes == 1000
    assert cfg.max_total_bytes == 5000
    assert cfg.max_file_tokens == 300
    assert cfg.max_total_tokens == 1200
    assert cfg.max_workers == 6
    assert cfg.file_summary is False
    assert cfg.security_check is False
    assert cfg.security_content_sniff is True
    assert cfg.nav_mode == "compact"
    assert cfg.symbol_backend == "tree-sitter"


def test_load_config_invalid_nav_mode_keeps_default(tmp_path: Path) -> None:
    """Invalid nav mode should keep default."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
nav_mode = "invalid"
symbol_backend = "bad"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.nav_mode == "auto"
    assert cfg.symbol_backend == "auto"


def test_load_config_invalid_token_count_numeric_values(tmp_path: Path) -> None:
    """Invalid numeric token values should keep defaults."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
token_count_tree_threshold = "not a number"
top_files_len = "also bad"
max_file_bytes = "bad"
max_total_bytes = "bad"
max_file_tokens = "bad"
max_total_tokens = "bad"
max_workers = "bad"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.token_count_tree_threshold == 0
    assert cfg.top_files_len == 5
    assert cfg.max_file_bytes == 0
    assert cfg.max_total_bytes == 0
    assert cfg.max_file_tokens == 0
    assert cfg.max_total_tokens == 0
    assert cfg.max_workers == 0


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
    assert cfg.include == DEFAULT_INCLUDES
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


def test_load_config_supports_dotfile(tmp_path: Path) -> None:
    """Test loading config from .codecrate.toml."""
    (tmp_path / ".codecrate.toml").write_text(
        """[codecrate]
output = "dot_context.md"
dedupe = true
""",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.output == "dot_context.md"
    assert cfg.dedupe is True


def test_load_config_dotfile_takes_precedence(tmp_path: Path) -> None:
    """If both config files exist, .codecrate.toml should win."""
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
output = "plain_context.md"
""",
        encoding="utf-8",
    )
    (tmp_path / ".codecrate.toml").write_text(
        """[codecrate]
output = "dot_context.md"
""",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.output == "dot_context.md"


def test_load_config_supports_pyproject_tool_codecrate(tmp_path: Path) -> None:
    """Load config from [tool.codecrate] in pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        """[tool.codecrate]
output = "pyproject_context.md"
dedupe = true
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.output == "pyproject_context.md"
    assert cfg.dedupe is True


def test_load_config_pyproject_requires_tool_section(tmp_path: Path) -> None:
    """[codecrate] in pyproject.toml should be ignored."""
    (tmp_path / "pyproject.toml").write_text(
        """[codecrate]
output = "wrong_context.md"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.output == "context.md"


def test_load_config_codecrate_toml_takes_precedence_over_pyproject(
    tmp_path: Path,
) -> None:
    """Dedicated config files should win over pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        """[tool.codecrate]
output = "pyproject_context.md"
""",
        encoding="utf-8",
    )
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
output = "codecrate_context.md"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.output == "codecrate_context.md"


def test_load_config_dotfile_takes_precedence_over_pyproject(tmp_path: Path) -> None:
    """.codecrate.toml should have highest precedence over pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        """[tool.codecrate]
output = "pyproject_context.md"
""",
        encoding="utf-8",
    )
    (tmp_path / ".codecrate.toml").write_text(
        """[codecrate]
output = "dot_context.md"
""",
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    assert cfg.output == "dot_context.md"
