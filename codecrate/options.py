from __future__ import annotations

import argparse
from dataclasses import dataclass

from .config import Config, include_patterns_for_preset


@dataclass(frozen=True)
class PackOptions:
    include: list[str] | None
    include_source: str
    exclude: list[str] | None
    keep_docstrings: bool
    profile: str
    include_manifest: bool
    index_json_enabled: bool
    index_json_mode: str | None
    index_json_include_lookup: bool
    index_json_include_symbol_index_lines: bool
    analysis_metadata: bool
    focus_file: list[str]
    focus_symbol: list[str]
    include_import_neighbors: int
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
    return norm if norm in {"human", "agent", "hybrid", "portable"} else "human"


def resolve_index_json_mode(
    cfg: Config, args: argparse.Namespace, profile: str
) -> str | None:
    cli_value = getattr(args, "index_json_mode", None)
    if cli_value is not None:
        value = str(cli_value).strip().lower()
        return value if value in {"full", "compact", "minimal", "normalized"} else None

    cfg_value = getattr(cfg, "index_json_mode", None)
    if isinstance(cfg_value, str):
        value = cfg_value.strip().lower()
        if value in {"full", "compact", "minimal", "normalized"}:
            return value

    if args.index_json is not None:
        return "full"
    if profile == "agent":
        return "minimal"
    if profile == "hybrid":
        return "full"
    return None


def resolve_pack_options(cfg: Config, args: argparse.Namespace) -> PackOptions:
    if args.index_json is not None and bool(getattr(args, "no_index_json", False)):
        raise ValueError("cannot combine --index-json with --no-index-json")
    if getattr(args, "index_json_mode", None) is not None and bool(
        getattr(args, "no_index_json", False)
    ):
        raise ValueError("cannot combine --index-json-mode with --no-index-json")

    profile = resolve_profile(cfg, args.profile)
    index_json_mode = resolve_index_json_mode(cfg, args, profile)
    if args.include is not None:
        include = args.include
        include_source = "cli --include"
    elif args.include_preset is not None:
        include = include_patterns_for_preset(str(args.include_preset))
        include_source = f"cli --include-preset={args.include_preset}"
    else:
        include = cfg.include
        include_source = f"config include/include_preset={cfg.include_preset}"
    exclude = args.exclude if args.exclude is not None else cfg.exclude
    keep_docstrings = (
        cfg.keep_docstrings
        if args.keep_docstrings is None
        else bool(args.keep_docstrings)
    )
    if args.manifest is None:
        include_manifest = cfg.manifest if profile == "human" else True
    else:
        include_manifest = bool(args.manifest)
    if args.index_json is not None:
        index_json_enabled = True
    elif bool(getattr(args, "no_index_json", False)):
        index_json_enabled = False
    elif getattr(args, "index_json_mode", None) is not None:
        index_json_enabled = True
    elif getattr(cfg, "index_json_mode", None) is not None:
        index_json_enabled = True
    else:
        index_json_enabled = profile in {"agent", "hybrid"}
    index_json_include_lookup = (
        bool(getattr(cfg, "index_json_include_lookup", True))
        if getattr(args, "index_json_lookup", None) is None
        else bool(args.index_json_lookup)
    )
    index_json_include_symbol_index_lines = (
        bool(getattr(cfg, "index_json_include_symbol_index_lines", True))
        if getattr(args, "index_json_symbol_index_lines", None) is None
        else bool(args.index_json_symbol_index_lines)
    )
    analysis_metadata = (
        bool(getattr(cfg, "analysis_metadata", True))
        if getattr(args, "analysis_metadata", None) is None
        else bool(args.analysis_metadata)
    )
    focus_file = (
        list(getattr(cfg, "focus_file", []))
        if getattr(args, "focus_file", None) is None
        else [str(item) for item in args.focus_file]
    )
    focus_symbol = (
        list(getattr(cfg, "focus_symbol", []))
        if getattr(args, "focus_symbol", None) is None
        else [str(item) for item in args.focus_symbol]
    )
    include_import_neighbors = (
        int(getattr(cfg, "include_import_neighbors", 0) or 0)
        if getattr(args, "include_import_neighbors", None) is None
        else int(args.include_import_neighbors or 0)
    )
    include_import_neighbors = max(0, include_import_neighbors)
    include_tests = (
        bool(getattr(cfg, "include_tests", False))
        if getattr(args, "include_tests", None) is None
        else bool(args.include_tests)
    )
    respect_gitignore = (
        cfg.respect_gitignore
        if args.respect_gitignore is None
        else bool(args.respect_gitignore)
    )
    security_check = (
        bool(getattr(cfg, "security_check", True))
        if args.security_check is None
        else bool(args.security_check)
    )
    security_content_sniff = (
        bool(getattr(cfg, "security_content_sniff", False))
        if args.security_content_sniff is None
        else bool(args.security_content_sniff)
    )
    security_redaction = (
        bool(getattr(cfg, "security_redaction", False))
        if args.security_redaction is None
        else bool(args.security_redaction)
    )
    safety_report = (
        bool(getattr(cfg, "safety_report", False))
        if args.safety_report is None
        else bool(args.safety_report)
    )
    security_path_patterns = (
        list(getattr(cfg, "security_path_patterns", []))
        if args.security_path_pattern is None
        else [str(p) for p in args.security_path_pattern]
    )
    security_path_patterns_add = (
        list(getattr(cfg, "security_path_patterns_add", []))
        if args.security_path_pattern_add is None
        else [str(p) for p in args.security_path_pattern_add]
    )
    security_path_patterns_remove = (
        list(getattr(cfg, "security_path_patterns_remove", []))
        if args.security_path_pattern_remove is None
        else [str(p) for p in args.security_path_pattern_remove]
    )
    security_content_patterns = (
        list(getattr(cfg, "security_content_patterns", []))
        if args.security_content_pattern is None
        else [str(p) for p in args.security_content_pattern]
    )
    dedupe = bool(cfg.dedupe) if args.dedupe is None else bool(args.dedupe)
    split_max_chars = (
        cfg.split_max_chars
        if args.split_max_chars is None
        else int(args.split_max_chars or 0)
    )
    split_strict = (
        bool(getattr(cfg, "split_strict", False))
        if args.split_strict is None
        else bool(args.split_strict)
    )
    split_allow_cut_files = (
        bool(getattr(cfg, "split_allow_cut_files", False))
        if args.split_allow_cut_files is None
        else bool(args.split_allow_cut_files)
    )
    if args.layout is not None:
        layout = str(args.layout).strip().lower()
    else:
        cfg_layout = str(getattr(cfg, "layout", "auto")).strip().lower()
        layout = (
            "full" if profile == "portable" and cfg_layout == "auto" else cfg_layout
        )
    nav_mode = (
        str(args.nav_mode).strip().lower()
        if args.nav_mode is not None
        else (
            "compact"
            if profile == "agent"
            else str(getattr(cfg, "nav_mode", "auto")).strip().lower()
        )
    )
    symbol_backend = (
        str(args.symbol_backend).strip().lower()
        if args.symbol_backend is not None
        else str(getattr(cfg, "symbol_backend", "auto")).strip().lower()
    )
    encoding_errors = resolve_encoding_errors(cfg, args.encoding_errors)

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

    token_report = bool(
        token_count_tree
        or args.top_files_len is not None
        or args.token_count_encoding is not None
    )
    file_summary = (
        bool(getattr(cfg, "file_summary", True))
        if args.file_summary is None
        else bool(args.file_summary)
    )

    max_file_bytes = (
        int(getattr(cfg, "max_file_bytes", 0) or 0)
        if args.max_file_bytes is None
        else int(args.max_file_bytes or 0)
    )
    max_total_bytes = (
        int(getattr(cfg, "max_total_bytes", 0) or 0)
        if args.max_total_bytes is None
        else int(args.max_total_bytes or 0)
    )
    max_file_tokens = (
        int(getattr(cfg, "max_file_tokens", 0) or 0)
        if args.max_file_tokens is None
        else int(args.max_file_tokens or 0)
    )
    max_total_tokens = (
        int(getattr(cfg, "max_total_tokens", 0) or 0)
        if args.max_total_tokens is None
        else int(args.max_total_tokens or 0)
    )
    max_workers = (
        int(getattr(cfg, "max_workers", 0) or 0)
        if args.max_workers is None
        else int(args.max_workers or 0)
    )

    return PackOptions(
        include=include,
        include_source=include_source,
        exclude=exclude,
        keep_docstrings=keep_docstrings,
        profile=profile,
        include_manifest=include_manifest,
        index_json_enabled=index_json_enabled,
        index_json_mode=index_json_mode,
        index_json_include_lookup=index_json_include_lookup,
        index_json_include_symbol_index_lines=index_json_include_symbol_index_lines,
        analysis_metadata=analysis_metadata,
        focus_file=focus_file,
        focus_symbol=focus_symbol,
        include_import_neighbors=include_import_neighbors,
        include_tests=include_tests,
        respect_gitignore=respect_gitignore,
        security_check=security_check,
        security_content_sniff=security_content_sniff,
        security_redaction=security_redaction,
        safety_report=safety_report,
        security_path_patterns=security_path_patterns,
        security_path_patterns_add=security_path_patterns_add,
        security_path_patterns_remove=security_path_patterns_remove,
        security_content_patterns=security_content_patterns,
        dedupe=dedupe,
        split_max_chars=split_max_chars,
        split_strict=split_strict,
        split_allow_cut_files=split_allow_cut_files,
        layout=layout,
        nav_mode=nav_mode,
        symbol_backend=symbol_backend,
        encoding_errors=encoding_errors,
        token_report=token_report,
        token_count_tree=token_count_tree,
        token_count_tree_threshold=token_count_tree_threshold,
        top_files_len=top_files_len,
        token_count_encoding=token_count_encoding,
        file_summary=file_summary,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        max_file_tokens=max_file_tokens,
        max_total_tokens=max_total_tokens,
        max_workers=max_workers,
    )
