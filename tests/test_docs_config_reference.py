from __future__ import annotations

from pathlib import Path

from codecrate.config import (
    DEFAULT_INCLUDE_PRESET,
    SUPPORTED_PROFILES,
    render_config_reference_rst,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_generated_config_reference_matches_renderer() -> None:
    docs_config = (REPO_ROOT / "docs" / "config.rst").read_text(encoding="utf-8")
    assert docs_config == render_config_reference_rst()


def test_readme_configuration_mentions_current_defaults() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f'default preset: "{DEFAULT_INCLUDE_PRESET}"' in readme
    assert "codecrate config schema --json" in readme


def test_cli_docs_reference_generated_config_and_schema() -> None:
    cli_docs = (REPO_ROOT / "docs" / "cli.rst").read_text(encoding="utf-8")
    assert ":doc:`config`" in cli_docs
    assert "codecrate config schema [--json]" in cli_docs


def test_handwritten_docs_list_all_supported_profiles() -> None:
    profile_docs = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "quickstart.rst",
        REPO_ROOT / "docs" / "format.rst",
    ]

    for path in profile_docs:
        text = path.read_text(encoding="utf-8")
        missing = [profile for profile in SUPPORTED_PROFILES if profile not in text]
        assert not missing, f"{path.relative_to(REPO_ROOT)} missing profiles: {missing}"
