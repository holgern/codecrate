from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, cast

from .config import Config, include_patterns_for_preset


@dataclass(frozen=True)
class PackOptions:
    include: list[str] | None
    include_source: str
    exclude: list[str] | None
    keep_docstrings: bool
    profile: str
    emit_standalone_unpacker: bool
    standalone_unpacker_output: str | None
    locator_space: str
    include_manifest: bool
    index_json_enabled: bool
    index_json_mode: str | None
    manifest_json_output: str | None
    index_json_output: str | None
    index_json_pretty: bool
    index_json_include_lookup: bool
    index_json_include_symbol_index_lines: bool
    analysis_metadata: bool
    index_json_include_graph: bool
    index_json_include_test_links: bool
    index_json_include_guide: bool
    index_json_include_file_imports: bool
    index_json_include_classes: bool
    index_json_include_exports: bool
    index_json_include_module_docstrings: bool
    index_json_include_semantic: bool
    index_json_include_purpose_text: bool
    index_json_include_symbol_locators: bool
    index_json_include_symbol_references: bool
    index_json_include_file_summaries: bool
    index_json_include_relationships: bool
    markdown_include_repository_guide: bool
    markdown_include_symbol_index: bool
    markdown_include_directory_tree: bool
    markdown_include_environment_setup: bool
    markdown_include_how_to_use: bool
    focus_file: list[str]
    focus_symbol: list[str]
    include_import_neighbors: int
    include_reverse_import_neighbors: int
    include_same_package: bool
    include_entrypoints: bool
    include_tests: bool
    respect_gitignore: bool
    security_check: bool
    security_content_sniff: bool
    security_redaction: bool
    safety_report: bool
    security_path_patterns: list[str]
    security_path_patterns_add: list[str]
    security_path_patterns_remove: list[str]
    security_content_patterns: list[str]
    dedupe: bool
    split_max_chars: int
    split_strict: bool
    split_allow_cut_files: bool
    layout: str
    nav_mode: str
    symbol_backend: str
    encoding_errors: str

    # CLI-only diagnostics
    token_report: bool
    token_count_tree: bool
    token_count_tree_threshold: int
    top_files_len: int
    token_count_encoding: str
    file_summary: bool
    max_file_bytes: int
    max_total_bytes: int
    max_file_tokens: int
    max_total_tokens: int
    max_workers: int


def resolve_encoding_errors(cfg: Config, cli_value: str | None) -> str:
    if cli_value is not None:
        value = str(cli_value).strip().lower()
    else:
        value = str(getattr(cfg, "encoding_errors", "replace")).strip().lower()
    return value if value in {"replace", "strict"} else "replace"


def resolve_profile(cfg: Config, cli_value: str | None) -> str:
    value = (
        cli_value if cli_value is not None else str(getattr(cfg, "profile", "human"))
    )
    norm = str(value).strip().lower()
    return (
        norm
        if norm
        in {"human", "agent", "lean-agent", "hybrid", "portable", "portable-agent"}
        else "human"
    )


def _resolve_optional_bool(
    cli_value: bool | None,
    cfg_value: bool | None,
    *,
    default: bool,
) -> bool:
    if cli_value is not None:
        return bool(cli_value)
    if cfg_value is not None:
        return bool(cfg_value)
    return default


def resolve_index_json_mode(
    cfg: Config, args: argparse.Namespace, profile: str
) -> str | None:
    index_json_requested = args.index_json is not None
    cli_value = getattr(args, "index_json_mode", None)
    if cli_value is not None:
        value = str(cli_value).strip().lower()
        return value if value in {"full", "compact", "minimal", "normalized"} else None

    cfg_value = getattr(cfg, "index_json_mode", None)
    if isinstance(cfg_value, str):
        value = cfg_value.strip().lower()
        if value in {"full", "compact", "minimal", "normalized"}:
            return value

    if profile in {"agent", "lean-agent", "portable-agent"}:
        return "normalized"
    if profile == "hybrid":
        return "full"
    if index_json_requested:
        return "full"
    return None


def resolve_emit_standalone_unpacker(
    cfg: Config, args: argparse.Namespace, profile: str
) -> bool:
    cli_value = getattr(args, "emit_standalone_unpacker", None)
    if cli_value is not None:
        return bool(cli_value)
    if profile == "portable-agent":
        return True
    return bool(getattr(cfg, "emit_standalone_unpacker", False)) or (
        getattr(cfg, "standalone_unpacker_output", None) is not None
    )


def resolve_locator_space(
    cfg: Config,
    args: argparse.Namespace,
    *,
    profile: str,
    emit_standalone_unpacker: bool,
) -> str:
    cli_value = getattr(args, "locator_space", None)
    if cli_value is not None:
        value = str(cli_value).strip().lower()
    else:
        value = str(getattr(cfg, "locator_space", "auto")).strip().lower()
    if value not in {"auto", "markdown", "reconstructed", "dual"}:
        value = "auto"
    if value == "auto":
        if profile == "portable-agent":
            return "dual"
        return "reconstructed" if emit_standalone_unpacker else "markdown"
    return value


def _validate_index_json_args(args: argparse.Namespace) -> None:
    if args.index_json is not None and bool(getattr(args, "no_index_json", False)):
        raise ValueError("cannot combine --index-json with --no-index-json")
    if getattr(args, "index_json_mode", None) is not None and bool(
        getattr(args, "no_index_json", False)
    ):
        raise ValueError("cannot combine --index-json-mode with --no-index-json")


def _resolve_selection_options(
    cfg: Config, args: argparse.Namespace
) -> dict[str, object]:
    if args.include is not None:
        include = args.include
        include_source = "cli --include"
    elif args.include_preset is not None:
        include = include_patterns_for_preset(str(args.include_preset))
        include_source = f"cli --include-preset={args.include_preset}"
    else:
        include = cfg.include
        include_source = f"config include/include_preset={cfg.include_preset}"
    keep_docstrings = (
        cfg.keep_docstrings
        if args.keep_docstrings is None
        else bool(args.keep_docstrings)
    )
    return {
        "include": include,
        "include_source": include_source,
        "exclude": args.exclude if args.exclude is not None else cfg.exclude,
        "keep_docstrings": keep_docstrings,
    }


def _resolve_output_targets(
    cfg: Config,
    args: argparse.Namespace,
    *,
    profile: str,
    index_json_mode: str | None,
) -> dict[str, object]:
    if args.manifest is None:
        include_manifest = cfg.manifest if profile == "human" else True
    else:
        include_manifest = bool(args.manifest)
    manifest_json_output = getattr(cfg, "manifest_json_output", None)
    index_json_output = getattr(cfg, "index_json_output", None)
    standalone_unpacker_output = getattr(cfg, "standalone_unpacker_output", None)
    if args.index_json is not None:
        index_json_enabled = True
    elif bool(getattr(args, "no_index_json", False)):
        index_json_enabled = False
    elif getattr(cfg, "index_json_enabled", None) is not None:
        index_json_enabled = bool(cfg.index_json_enabled)
    elif getattr(args, "index_json_mode", None) is not None:
        index_json_enabled = True
    elif index_json_output is not None:
        index_json_enabled = True
    elif getattr(cfg, "index_json_mode", None) is not None:
        index_json_enabled = True
    else:
        index_json_enabled = profile in {
            "agent",
            "lean-agent",
            "hybrid",
            "portable-agent",
        }
    return {
        "include_manifest": include_manifest,
        "manifest_json_output": manifest_json_output,
        "index_json_output": index_json_output,
        "standalone_unpacker_output": standalone_unpacker_output,
        "index_json_enabled": index_json_enabled,
        "index_json_mode": index_json_mode,
    }


def _resolve_sidecar_and_markdown_options(
    cfg: Config,
    args: argparse.Namespace,
    *,
    profile: str,
    index_json_mode: str | None,
) -> dict[str, object]:
    default_analysis_metadata = not (
        index_json_mode == "minimal" or profile == "lean-agent"
    )
    portable_agent_trimmed = profile == "portable-agent"
    analysis_metadata = _resolve_optional_bool(
        getattr(args, "analysis_metadata", None),
        getattr(cfg, "analysis_metadata", None),
        default=default_analysis_metadata,
    )
    index_json_pretty = _resolve_optional_bool(
        getattr(args, "index_json_pretty", None),
        getattr(cfg, "index_json_pretty", None),
        default=not (
            index_json_mode == "minimal"
            or profile == "lean-agent"
            or portable_agent_trimmed
        ),
    )
    index_json_include_lookup = _resolve_optional_bool(
        getattr(args, "index_json_lookup", None),
        getattr(cfg, "index_json_include_lookup", None),
        default=index_json_mode != "minimal",
    )
    index_json_include_symbol_index_lines = _resolve_optional_bool(
        getattr(args, "index_json_symbol_index_lines", None),
        getattr(cfg, "index_json_include_symbol_index_lines", None),
        default=index_json_mode != "minimal",
    )
    default_compact_analysis = analysis_metadata and not (
        index_json_mode == "minimal" or profile == "lean-agent"
    )

    def _resolve_analysis_toggle(name: str, arg_name: str) -> bool:
        return _resolve_optional_bool(
            getattr(args, arg_name, None),
            getattr(cfg, name, None),
            default=analysis_metadata,
        )

    return {
        "analysis_metadata": analysis_metadata,
        "index_json_pretty": index_json_pretty,
        "index_json_include_lookup": index_json_include_lookup,
        "index_json_include_symbol_index_lines": index_json_include_symbol_index_lines,
        "index_json_include_graph": _resolve_optional_bool(
            getattr(args, "index_json_graph", None),
            getattr(cfg, "index_json_include_graph", None),
            default=analysis_metadata and not portable_agent_trimmed,
        ),
        "index_json_include_test_links": _resolve_analysis_toggle(
            "index_json_include_test_links", "index_json_test_links"
        ),
        "index_json_include_guide": _resolve_analysis_toggle(
            "index_json_include_guide", "index_json_guide"
        ),
        "index_json_include_file_imports": _resolve_analysis_toggle(
            "index_json_include_file_imports", "index_json_file_imports"
        ),
        "index_json_include_classes": _resolve_analysis_toggle(
            "index_json_include_classes", "index_json_classes"
        ),
        "index_json_include_exports": _resolve_analysis_toggle(
            "index_json_include_exports", "index_json_exports"
        ),
        "index_json_include_module_docstrings": _resolve_analysis_toggle(
            "index_json_include_module_docstrings",
            "index_json_module_docstrings",
        ),
        "index_json_include_semantic": _resolve_optional_bool(
            getattr(args, "index_json_semantic", None),
            getattr(cfg, "index_json_include_semantic", None),
            default=default_compact_analysis,
        ),
        "index_json_include_purpose_text": _resolve_optional_bool(
            getattr(args, "index_json_purpose_text", None),
            getattr(cfg, "index_json_include_purpose_text", None),
            default=default_compact_analysis,
        ),
        "index_json_include_symbol_locators": _resolve_optional_bool(
            getattr(args, "index_json_symbol_locators", None),
            getattr(cfg, "index_json_include_symbol_locators", None),
            default=profile != "lean-agent",
        ),
        "index_json_include_symbol_references": _resolve_optional_bool(
            getattr(args, "index_json_symbol_references", None),
            getattr(cfg, "index_json_include_symbol_references", None),
            default=default_compact_analysis and not portable_agent_trimmed,
        ),
        "index_json_include_file_summaries": _resolve_optional_bool(
            getattr(args, "index_json_file_summaries", None),
            getattr(cfg, "index_json_include_file_summaries", None),
            default=default_compact_analysis,
        ),
        "index_json_include_relationships": _resolve_optional_bool(
            getattr(args, "index_json_relationships", None),
            getattr(cfg, "index_json_include_relationships", None),
            default=default_compact_analysis,
        ),
        "markdown_include_repository_guide": _resolve_optional_bool(
            getattr(args, "markdown_repository_guide", None),
            getattr(cfg, "markdown_include_repository_guide", None),
            default=analysis_metadata and profile != "lean-agent",
        ),
        "markdown_include_symbol_index": _resolve_optional_bool(
            getattr(args, "markdown_symbol_index", None),
            getattr(cfg, "markdown_include_symbol_index", None),
            default=True,
        ),
        "markdown_include_directory_tree": _resolve_optional_bool(
            getattr(args, "markdown_directory_tree", None),
            getattr(cfg, "markdown_include_directory_tree", None),
            default=True,
        ),
        "markdown_include_environment_setup": _resolve_optional_bool(
            getattr(args, "markdown_environment_setup", None),
            getattr(cfg, "markdown_include_environment_setup", None),
            default=profile != "lean-agent",
        ),
        "markdown_include_how_to_use": _resolve_optional_bool(
            getattr(args, "markdown_how_to_use", None),
            getattr(cfg, "markdown_include_how_to_use", None),
            default=profile != "lean-agent",
        ),
    }


def _resolve_focus_options(cfg: Config, args: argparse.Namespace) -> dict[str, object]:
    include_import_neighbors = (
        int(getattr(cfg, "include_import_neighbors", 0) or 0)
        if getattr(args, "include_import_neighbors", None) is None
        else int(args.include_import_neighbors or 0)
    )
    include_reverse_import_neighbors = (
        int(getattr(cfg, "include_reverse_import_neighbors", 0) or 0)
        if getattr(args, "include_reverse_import_neighbors", None) is None
        else int(args.include_reverse_import_neighbors or 0)
    )
    return {
        "focus_file": (
            list(getattr(cfg, "focus_file", []))
            if getattr(args, "focus_file", None) is None
            else [str(item) for item in args.focus_file]
        ),
        "focus_symbol": (
            list(getattr(cfg, "focus_symbol", []))
            if getattr(args, "focus_symbol", None) is None
            else [str(item) for item in args.focus_symbol]
        ),
        "include_import_neighbors": max(0, include_import_neighbors),
        "include_reverse_import_neighbors": max(0, include_reverse_import_neighbors),
        "include_same_package": (
            bool(getattr(cfg, "include_same_package", False))
            if getattr(args, "include_same_package", None) is None
            else bool(args.include_same_package)
        ),
        "include_entrypoints": (
            bool(getattr(cfg, "include_entrypoints", False))
            if getattr(args, "include_entrypoints", None) is None
            else bool(args.include_entrypoints)
        ),
        "include_tests": (
            bool(getattr(cfg, "include_tests", False))
            if getattr(args, "include_tests", None) is None
            else bool(args.include_tests)
        ),
    }


def _resolve_safety_options(cfg: Config, args: argparse.Namespace) -> dict[str, object]:
    return {
        "respect_gitignore": (
            cfg.respect_gitignore
            if args.respect_gitignore is None
            else bool(args.respect_gitignore)
        ),
        "security_check": (
            bool(getattr(cfg, "security_check", True))
            if args.security_check is None
            else bool(args.security_check)
        ),
        "security_content_sniff": (
            bool(getattr(cfg, "security_content_sniff", False))
            if args.security_content_sniff is None
            else bool(args.security_content_sniff)
        ),
        "security_redaction": (
            bool(getattr(cfg, "security_redaction", False))
            if args.security_redaction is None
            else bool(args.security_redaction)
        ),
        "safety_report": (
            bool(getattr(cfg, "safety_report", False))
            if args.safety_report is None
            else bool(args.safety_report)
        ),
        "security_path_patterns": (
            list(getattr(cfg, "security_path_patterns", []))
            if args.security_path_pattern is None
            else [str(p) for p in args.security_path_pattern]
        ),
        "security_path_patterns_add": (
            list(getattr(cfg, "security_path_patterns_add", []))
            if args.security_path_pattern_add is None
            else [str(p) for p in args.security_path_pattern_add]
        ),
        "security_path_patterns_remove": (
            list(getattr(cfg, "security_path_patterns_remove", []))
            if args.security_path_pattern_remove is None
            else [str(p) for p in args.security_path_pattern_remove]
        ),
        "security_content_patterns": (
            list(getattr(cfg, "security_content_patterns", []))
            if args.security_content_pattern is None
            else [str(p) for p in args.security_content_pattern]
        ),
    }


def _resolve_render_options(
    cfg: Config, args: argparse.Namespace, *, profile: str
) -> dict[str, object]:
    if args.layout is not None:
        layout = str(args.layout).strip().lower()
    else:
        cfg_layout = str(getattr(cfg, "layout", "auto")).strip().lower()
        layout = (
            "full"
            if profile in {"portable", "portable-agent"} and cfg_layout == "auto"
            else cfg_layout
        )
    nav_mode = (
        str(args.nav_mode).strip().lower()
        if args.nav_mode is not None
        else (
            "compact"
            if profile in {"agent", "lean-agent", "portable-agent"}
            else str(getattr(cfg, "nav_mode", "auto")).strip().lower()
        )
    )
    return {
        "dedupe": bool(cfg.dedupe) if args.dedupe is None else bool(args.dedupe),
        "split_max_chars": (
            cfg.split_max_chars
            if args.split_max_chars is None
            else int(args.split_max_chars or 0)
        ),
        "split_strict": (
            bool(getattr(cfg, "split_strict", False))
            if args.split_strict is None
            else bool(args.split_strict)
        ),
        "split_allow_cut_files": (
            bool(getattr(cfg, "split_allow_cut_files", False))
            if args.split_allow_cut_files is None
            else bool(args.split_allow_cut_files)
        ),
        "layout": layout,
        "nav_mode": nav_mode,
        "symbol_backend": (
            str(args.symbol_backend).strip().lower()
            if args.symbol_backend is not None
            else str(getattr(cfg, "symbol_backend", "auto")).strip().lower()
        ),
        "encoding_errors": resolve_encoding_errors(cfg, args.encoding_errors),
    }


def _resolve_budget_options(cfg: Config, args: argparse.Namespace) -> dict[str, object]:
    token_count_encoding = (
        str(args.token_count_encoding).strip()
        if args.token_count_encoding is not None
        else str(getattr(cfg, "token_count_encoding", "o200k_base")).strip()
    ) or "o200k_base"
    cfg_tree = bool(getattr(cfg, "token_count_tree", False))
    cfg_thr = int(getattr(cfg, "token_count_tree_threshold", 0) or 0)
    cfg_top = int(getattr(cfg, "top_files_len", 5) or 5)
    token_count_tree = cfg_tree
    token_count_tree_threshold = cfg_thr
    if args.token_count_tree is not None:
        token_count_tree = True
        raw = str(args.token_count_tree).strip()
        if raw and raw != "-1":
            try:
                token_count_tree_threshold = int(raw)
            except Exception:
                token_count_tree_threshold = cfg_thr
    top_files_len = cfg_top
    if args.top_files_len is not None:
        top_files_len = int(args.top_files_len)
    return {
        "token_report": bool(
            token_count_tree
            or args.top_files_len is not None
            or args.token_count_encoding is not None
        ),
        "token_count_tree": token_count_tree,
        "token_count_tree_threshold": token_count_tree_threshold,
        "top_files_len": top_files_len,
        "token_count_encoding": token_count_encoding,
        "file_summary": (
            bool(getattr(cfg, "file_summary", True))
            if args.file_summary is None
            else bool(args.file_summary)
        ),
        "max_file_bytes": (
            int(getattr(cfg, "max_file_bytes", 0) or 0)
            if args.max_file_bytes is None
            else int(args.max_file_bytes or 0)
        ),
        "max_total_bytes": (
            int(getattr(cfg, "max_total_bytes", 0) or 0)
            if args.max_total_bytes is None
            else int(args.max_total_bytes or 0)
        ),
        "max_file_tokens": (
            int(getattr(cfg, "max_file_tokens", 0) or 0)
            if args.max_file_tokens is None
            else int(args.max_file_tokens or 0)
        ),
        "max_total_tokens": (
            int(getattr(cfg, "max_total_tokens", 0) or 0)
            if args.max_total_tokens is None
            else int(args.max_total_tokens or 0)
        ),
        "max_workers": (
            int(getattr(cfg, "max_workers", 0) or 0)
            if args.max_workers is None
            else int(args.max_workers or 0)
        ),
    }


def resolve_pack_options(cfg: Config, args: argparse.Namespace) -> PackOptions:
    _validate_index_json_args(args)
    profile = resolve_profile(cfg, args.profile)
    emit_standalone_unpacker = resolve_emit_standalone_unpacker(cfg, args, profile)
    locator_space = resolve_locator_space(
        cfg,
        args,
        profile=profile,
        emit_standalone_unpacker=emit_standalone_unpacker,
    )
    index_json_mode = resolve_index_json_mode(cfg, args, profile)
    selection_options = _resolve_selection_options(cfg, args)
    output_targets = _resolve_output_targets(
        cfg,
        args,
        profile=profile,
        index_json_mode=index_json_mode,
    )
    sidecar_and_markdown = _resolve_sidecar_and_markdown_options(
        cfg,
        args,
        profile=profile,
        index_json_mode=index_json_mode,
    )
    focus_options = _resolve_focus_options(cfg, args)
    safety_options = _resolve_safety_options(cfg, args)
    render_options = _resolve_render_options(cfg, args, profile=profile)
    budget_options = _resolve_budget_options(cfg, args)

    return PackOptions(
        profile=profile,
        emit_standalone_unpacker=emit_standalone_unpacker,
        locator_space=locator_space,
        **cast(dict[str, Any], selection_options),
        **cast(dict[str, Any], output_targets),
        **cast(dict[str, Any], sidecar_and_markdown),
        **cast(dict[str, Any], focus_options),
        **cast(dict[str, Any], safety_options),
        **cast(dict[str, Any], render_options),
        **cast(dict[str, Any], budget_options),
    )
