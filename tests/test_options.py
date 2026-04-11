from __future__ import annotations

from pathlib import Path

import pytest

from codecrate.cli import build_parser
from codecrate.config import Config
from codecrate.options import resolve_pack_options


def _parse_pack_args(tmp_path: Path, *extra: str) -> object:
    parser = build_parser()
    return parser.parse_args(["pack", str(tmp_path), *extra])


def test_resolve_pack_options_uses_profile_defaults(tmp_path: Path) -> None:
    cfg = Config()

    options = resolve_pack_options(
        cfg,
        _parse_pack_args(tmp_path, "--profile", "agent"),
    )

    assert options.profile == "agent"
    assert options.nav_mode == "compact"
    assert options.index_json_enabled is True
    assert options.index_json_mode == "minimal"
    assert options.index_json_include_lookup is True
    assert options.index_json_include_symbol_index_lines is True
    assert options.include_manifest is True


def test_resolve_pack_options_cli_overrides_profile_defaults(tmp_path: Path) -> None:
    cfg = Config(profile="agent")

    options = resolve_pack_options(
        cfg,
        _parse_pack_args(tmp_path, "--nav-mode", "full", "--no-index-json"),
    )

    assert options.profile == "agent"
    assert options.nav_mode == "full"
    assert options.index_json_enabled is False


def test_resolve_pack_options_config_overrides_defaults(tmp_path: Path) -> None:
    cfg = Config(profile="hybrid", include_preset="python-only", include=["**/*.py"])

    options = resolve_pack_options(cfg, _parse_pack_args(tmp_path))

    assert options.profile == "hybrid"
    assert options.index_json_enabled is True
    assert options.index_json_mode == "full"
    assert options.include == ["**/*.py"]
    assert options.include_source == "config include/include_preset=python-only"


def test_resolve_pack_options_cli_overrides_config(tmp_path: Path) -> None:
    cfg = Config(profile="human", nav_mode="compact", include=["**/*.py"])

    options = resolve_pack_options(
        cfg,
        _parse_pack_args(
            tmp_path,
            "--profile",
            "agent",
            "--include-preset",
            "everything",
            "--nav-mode",
            "full",
        ),
    )

    assert options.profile == "agent"
    assert options.nav_mode == "full"
    assert options.include == ["**/*"]
    assert options.include_source == "cli --include-preset=everything"


def test_resolve_pack_options_explicit_index_json_defaults_to_full(
    tmp_path: Path,
) -> None:
    cfg = Config(profile="agent")

    options = resolve_pack_options(cfg, _parse_pack_args(tmp_path, "--index-json"))

    assert options.index_json_enabled is True
    assert options.index_json_mode == "full"


def test_resolve_pack_options_index_json_mode_enables_sidecar(tmp_path: Path) -> None:
    cfg = Config()

    options = resolve_pack_options(
        cfg,
        _parse_pack_args(tmp_path, "--index-json-mode", "minimal"),
    )

    assert options.index_json_enabled is True
    assert options.index_json_mode == "minimal"


def test_resolve_pack_options_portable_profile_defaults_to_full_without_index_json(
    tmp_path: Path,
) -> None:
    cfg = Config()

    options = resolve_pack_options(
        cfg,
        _parse_pack_args(tmp_path, "--profile", "portable"),
    )

    assert options.profile == "portable"
    assert options.layout == "full"
    assert options.include_manifest is True
    assert options.index_json_enabled is False


def test_resolve_pack_options_config_index_json_mode_enables_sidecar(
    tmp_path: Path,
) -> None:
    cfg = Config(index_json_mode="compact")

    options = resolve_pack_options(cfg, _parse_pack_args(tmp_path))

    assert options.index_json_enabled is True
    assert options.index_json_mode == "compact"


def test_resolve_pack_options_v2_trimming_flags_from_cli(tmp_path: Path) -> None:
    cfg = Config()

    options = resolve_pack_options(
        cfg,
        _parse_pack_args(
            tmp_path,
            "--index-json-mode",
            "compact",
            "--no-index-json-lookup",
            "--no-index-json-symbol-index-lines",
        ),
    )

    assert options.index_json_include_lookup is False
    assert options.index_json_include_symbol_index_lines is False


def test_resolve_pack_options_v2_trimming_flags_from_config(tmp_path: Path) -> None:
    cfg = Config(
        index_json_mode="compact",
        index_json_include_lookup=False,
        index_json_include_symbol_index_lines=False,
    )

    options = resolve_pack_options(cfg, _parse_pack_args(tmp_path))

    assert options.index_json_include_lookup is False
    assert options.index_json_include_symbol_index_lines is False


def test_resolve_pack_options_rejects_conflicting_index_json_flags(
    tmp_path: Path,
) -> None:
    cfg = Config()

    with pytest.raises(
        ValueError,
        match="cannot combine --index-json with --no-index-json",
    ):
        resolve_pack_options(
            cfg,
            _parse_pack_args(tmp_path, "--index-json", "--no-index-json"),
        )


def test_resolve_pack_options_rejects_conflicting_index_json_mode_flags(
    tmp_path: Path,
) -> None:
    cfg = Config()

    with pytest.raises(
        ValueError,
        match="cannot combine --index-json-mode with --no-index-json",
    ):
        resolve_pack_options(
            cfg,
            _parse_pack_args(
                tmp_path,
                "--index-json-mode",
                "compact",
                "--no-index-json",
            ),
        )
