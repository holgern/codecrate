from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .config import (
    PYPROJECT_FILENAME,
    Config,
    ConfigValueProvenance,
    ConfigWarning,
    EncodingErrorsValue,
    IncludePresetValue,
    IndexJsonModeValue,
    LayoutValue,
    LoadedConfig,
    LocatorSpaceValue,
    NavModeValue,
    ProfileValue,
    SymbolBackendValue,
    _config_source_name,
    _default_provenance,
    _extract_section,
    _find_config_path,
    _load_bool_value,
    _load_focus_list,
    _load_int_value,
    _load_non_empty_string,
    _load_optional_bool_value,
    _load_optional_output_value,
    _load_optional_string_choice,
    _load_string_choice,
    _load_string_list,
    _raw_section_value,
    _record_provenance,
    _warn_unknown_keys,
    include_patterns_for_preset,
)

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]


def _load_output_config(
    cfg: Config,
    section: dict[str, Any],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> None:
    output_key, output_value = _raw_section_value(section, "output")
    if output_key is None:
        return
    _record_provenance(
        provenance,
        field_name="output",
        source=source,
        config_key=output_key,
    )
    if isinstance(output_value, str) and output_value.strip():
        raw_output = output_value.strip()
        output_path = Path(raw_output)
        if output_path.suffix or raw_output.endswith(("/", "\\")):
            cfg.output = raw_output
        else:
            cfg.output = f"{raw_output}.md"
        return
    warnings.append(
        ConfigWarning(
            key=output_key,
            raw_value=output_value,
            fallback=cfg.output,
            message="Invalid output path value; using default.",
        )
    )


def _load_base_config(
    cfg: Config,
    section: dict[str, Any],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> None:
    cfg.keep_docstrings = _load_bool_value(
        section,
        "keep_docstrings",
        cfg.keep_docstrings,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.dedupe = _load_bool_value(
        section,
        "dedupe",
        cfg.dedupe,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.respect_gitignore = _load_bool_value(
        section,
        "respect_gitignore",
        cfg.respect_gitignore,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.manifest = _load_bool_value(
        section,
        "manifest",
        cfg.manifest,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.profile = cast(
        ProfileValue,
        _load_string_choice(
            section,
            "profile",
            cfg.profile,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    cfg.layout = cast(
        LayoutValue,
        _load_string_choice(
            section,
            "layout",
            cfg.layout,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    cfg.include_preset = cast(
        IncludePresetValue,
        _load_string_choice(
            section,
            "include_preset",
            cfg.include_preset,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    include_key, include_value = _raw_section_value(section, "include")
    if include_key is not None:
        _record_provenance(
            provenance,
            field_name="include",
            source=source,
            config_key=include_key,
        )
        if isinstance(include_value, list):
            cfg.include = [str(item) for item in include_value]
        else:
            warnings.append(
                ConfigWarning(
                    key=include_key,
                    raw_value=include_value,
                    fallback=list(cfg.include),
                    message="Invalid list value; using default.",
                )
            )
    else:
        cfg.include = include_patterns_for_preset(cfg.include_preset)
        if getattr(provenance["include_preset"], "config_key", None) is not None:
            _record_provenance(
                provenance,
                field_name="include",
                source=source,
                config_key=provenance["include_preset"].config_key,
            )
    cfg.exclude = _load_string_list(
        section,
        "exclude",
        cfg.exclude,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.split_max_chars = _load_int_value(
        section,
        "split_max_chars",
        cfg.split_max_chars,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.split_strict = _load_bool_value(
        section,
        "split_strict",
        cfg.split_strict,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.split_allow_cut_files = _load_bool_value(
        section,
        "split_allow_cut_files",
        cfg.split_allow_cut_files,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )


def _load_budget_and_safety_config(
    cfg: Config,
    section: dict[str, Any],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> None:
    cfg.token_count_encoding = _load_non_empty_string(
        section,
        "token_count_encoding",
        cfg.token_count_encoding,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.token_count_tree = _load_bool_value(
        section,
        "token_count_tree",
        cfg.token_count_tree,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.token_count_tree_threshold = _load_int_value(
        section,
        "token_count_tree_threshold",
        cfg.token_count_tree_threshold,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.top_files_len = _load_int_value(
        section,
        "top_files_len",
        cfg.top_files_len,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.max_file_bytes = _load_int_value(
        section,
        "max_file_bytes",
        cfg.max_file_bytes,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.max_total_bytes = _load_int_value(
        section,
        "max_total_bytes",
        cfg.max_total_bytes,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.max_file_tokens = _load_int_value(
        section,
        "max_file_tokens",
        cfg.max_file_tokens,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.max_total_tokens = _load_int_value(
        section,
        "max_total_tokens",
        cfg.max_total_tokens,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.max_workers = _load_int_value(
        section,
        "max_workers",
        cfg.max_workers,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.file_summary = _load_bool_value(
        section,
        "file_summary",
        cfg.file_summary,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_check = _load_bool_value(
        section,
        "security_check",
        cfg.security_check,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_content_sniff = _load_bool_value(
        section,
        "security_content_sniff",
        cfg.security_content_sniff,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_redaction = _load_bool_value(
        section,
        "security_redaction",
        cfg.security_redaction,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.safety_report = _load_bool_value(
        section,
        "safety_report",
        cfg.safety_report,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_path_patterns = _load_string_list(
        section,
        "security_path_patterns",
        cfg.security_path_patterns,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_path_patterns_add = _load_string_list(
        section,
        "security_path_patterns_add",
        cfg.security_path_patterns_add,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_path_patterns_remove = _load_string_list(
        section,
        "security_path_patterns_remove",
        cfg.security_path_patterns_remove,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.security_content_patterns = _load_string_list(
        section,
        "security_content_patterns",
        cfg.security_content_patterns,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )


def _load_sidecar_config(
    cfg: Config,
    section: dict[str, Any],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> None:
    cfg.nav_mode = cast(
        NavModeValue,
        _load_string_choice(
            section,
            "nav_mode",
            cfg.nav_mode,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    cfg.index_json_mode = cast(
        IndexJsonModeValue | None,
        _load_optional_string_choice(
            section,
            "index_json_mode",
            cfg.index_json_mode,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    cfg.index_json_enabled = _load_optional_bool_value(
        section,
        "index_json_enabled",
        cfg.index_json_enabled,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.manifest_json_output = _load_optional_output_value(
        section,
        "manifest_json_output",
        cfg.manifest_json_output,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_output = _load_optional_output_value(
        section,
        "index_json_output",
        cfg.index_json_output,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.emit_standalone_unpacker = _load_bool_value(
        section,
        "emit_standalone_unpacker",
        cfg.emit_standalone_unpacker,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.standalone_unpacker_output = _load_optional_output_value(
        section,
        "standalone_unpacker_output",
        cfg.standalone_unpacker_output,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.locator_space = cast(
        LocatorSpaceValue,
        _load_string_choice(
            section,
            "locator_space",
            cfg.locator_space,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    for field_name in (
        "index_json_pretty",
        "index_json_include_lookup",
        "index_json_include_symbol_index_lines",
        "index_json_include_graph",
        "index_json_include_test_links",
        "index_json_include_guide",
        "index_json_include_file_imports",
        "index_json_include_classes",
        "index_json_include_exports",
        "index_json_include_module_docstrings",
        "index_json_include_semantic",
        "index_json_include_purpose_text",
        "index_json_include_symbol_locators",
        "index_json_include_symbol_references",
        "index_json_include_file_summaries",
        "index_json_include_relationships",
        "analysis_metadata",
        "markdown_include_repository_guide",
        "markdown_include_symbol_index",
        "markdown_include_directory_tree",
        "markdown_include_environment_setup",
        "markdown_include_how_to_use",
    ):
        setattr(
            cfg,
            field_name,
            _load_optional_bool_value(
                section,
                field_name,
                getattr(cfg, field_name),
                warnings=warnings,
                provenance=provenance,
                source=source,
            ),
        )


def _load_focus_and_runtime_config(
    cfg: Config,
    section: dict[str, Any],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> None:
    cfg.focus_file = _load_focus_list(
        section,
        "focus_file",
        cfg.focus_file,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.focus_symbol = _load_focus_list(
        section,
        "focus_symbol",
        cfg.focus_symbol,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.include_import_neighbors = _load_int_value(
        section,
        "include_import_neighbors",
        cfg.include_import_neighbors,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.include_reverse_import_neighbors = _load_int_value(
        section,
        "include_reverse_import_neighbors",
        cfg.include_reverse_import_neighbors,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.include_same_package = _load_bool_value(
        section,
        "include_same_package",
        cfg.include_same_package,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.include_entrypoints = _load_bool_value(
        section,
        "include_entrypoints",
        cfg.include_entrypoints,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.include_tests = _load_bool_value(
        section,
        "include_tests",
        cfg.include_tests,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.symbol_backend = cast(
        SymbolBackendValue,
        _load_string_choice(
            section,
            "symbol_backend",
            cfg.symbol_backend,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )
    cfg.encoding_errors = cast(
        EncodingErrorsValue,
        _load_string_choice(
            section,
            "encoding_errors",
            cfg.encoding_errors,
            warnings=warnings,
            provenance=provenance,
            source=source,
        ),
    )


def load_config_details(root: Path) -> LoadedConfig:
    cfg_path = _find_config_path(root)
    cfg = Config()
    warnings: list[ConfigWarning] = []
    provenance = _default_provenance()
    source = _config_source_name(cfg_path)
    if cfg_path is None:
        return LoadedConfig(
            config=cfg,
            warnings=warnings,
            provenance=provenance,
            selected_path=None,
        )

    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    section = _extract_section(data, from_pyproject=cfg_path.name == PYPROJECT_FILENAME)
    _warn_unknown_keys(section, warnings)

    _load_output_config(
        cfg,
        section,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    _load_base_config(
        cfg,
        section,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    _load_budget_and_safety_config(
        cfg,
        section,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    _load_sidecar_config(
        cfg,
        section,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    _load_focus_and_runtime_config(
        cfg,
        section,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    return LoadedConfig(
        config=cfg,
        warnings=warnings,
        provenance=provenance,
        selected_path=cfg_path,
    )


def load_config_with_warnings(root: Path) -> tuple[Config, list[ConfigWarning]]:
    details = load_config_details(root)
    return details.config, details.warnings


def load_config(root: Path) -> Config:
    return load_config_details(root).config


__all__ = ["load_config", "load_config_details", "load_config_with_warnings"]
