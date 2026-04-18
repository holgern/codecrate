from __future__ import annotations

from dataclasses import dataclass

from .options import PackOptions


@dataclass(frozen=True)
class OutputOptions:
    profile: str
    emit_standalone_unpacker: bool
    standalone_unpacker_output: str | None
    locator_space: str
    include_manifest: bool
    layout: str
    nav_mode: str


@dataclass(frozen=True)
class SidecarOptions:
    enabled: bool
    mode: str | None
    output: str | None
    pretty: bool
    include_lookup: bool
    include_symbol_index_lines: bool
    include_graph: bool
    include_test_links: bool
    include_guide: bool
    include_file_imports: bool
    include_classes: bool
    include_exports: bool
    include_module_docstrings: bool
    include_semantic: bool
    include_purpose_text: bool
    include_symbol_locators: bool
    include_symbol_references: bool
    include_file_summaries: bool
    include_relationships: bool


@dataclass(frozen=True)
class FocusOptions:
    focus_file: list[str]
    focus_symbol: list[str]
    include_import_neighbors: int
    include_reverse_import_neighbors: int
    include_same_package: bool
    include_entrypoints: bool
    include_tests: bool


@dataclass(frozen=True)
class SafetyOptions:
    respect_gitignore: bool
    gitignore_allow: list[str]
    security_check: bool
    security_content_sniff: bool
    security_redaction: bool
    safety_report: bool
    security_path_patterns: list[str]
    security_path_patterns_add: list[str]
    security_path_patterns_remove: list[str]
    security_content_patterns: list[str]


@dataclass(frozen=True)
class BudgetOptions:
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


def output_options_from_pack(options: PackOptions) -> OutputOptions:
    return OutputOptions(
        profile=options.profile,
        emit_standalone_unpacker=options.emit_standalone_unpacker,
        standalone_unpacker_output=options.standalone_unpacker_output,
        locator_space=options.locator_space,
        include_manifest=options.include_manifest,
        layout=options.layout,
        nav_mode=options.nav_mode,
    )


def sidecar_options_from_pack(options: PackOptions) -> SidecarOptions:
    return SidecarOptions(
        enabled=options.index_json_enabled,
        mode=options.index_json_mode,
        output=options.index_json_output,
        pretty=options.index_json_pretty,
        include_lookup=options.index_json_include_lookup,
        include_symbol_index_lines=options.index_json_include_symbol_index_lines,
        include_graph=options.index_json_include_graph,
        include_test_links=options.index_json_include_test_links,
        include_guide=options.index_json_include_guide,
        include_file_imports=options.index_json_include_file_imports,
        include_classes=options.index_json_include_classes,
        include_exports=options.index_json_include_exports,
        include_module_docstrings=options.index_json_include_module_docstrings,
        include_semantic=options.index_json_include_semantic,
        include_purpose_text=options.index_json_include_purpose_text,
        include_symbol_locators=options.index_json_include_symbol_locators,
        include_symbol_references=options.index_json_include_symbol_references,
        include_file_summaries=options.index_json_include_file_summaries,
        include_relationships=options.index_json_include_relationships,
    )


def focus_options_from_pack(options: PackOptions) -> FocusOptions:
    return FocusOptions(
        focus_file=options.focus_file,
        focus_symbol=options.focus_symbol,
        include_import_neighbors=options.include_import_neighbors,
        include_reverse_import_neighbors=options.include_reverse_import_neighbors,
        include_same_package=options.include_same_package,
        include_entrypoints=options.include_entrypoints,
        include_tests=options.include_tests,
    )


def safety_options_from_pack(options: PackOptions) -> SafetyOptions:
    return SafetyOptions(
        respect_gitignore=options.respect_gitignore,
        gitignore_allow=options.gitignore_allow,
        security_check=options.security_check,
        security_content_sniff=options.security_content_sniff,
        security_redaction=options.security_redaction,
        safety_report=options.safety_report,
        security_path_patterns=options.security_path_patterns,
        security_path_patterns_add=options.security_path_patterns_add,
        security_path_patterns_remove=options.security_path_patterns_remove,
        security_content_patterns=options.security_content_patterns,
    )


def budget_options_from_pack(options: PackOptions) -> BudgetOptions:
    return BudgetOptions(
        token_report=options.token_report,
        token_count_tree=options.token_count_tree,
        token_count_tree_threshold=options.token_count_tree_threshold,
        top_files_len=options.top_files_len,
        token_count_encoding=options.token_count_encoding,
        file_summary=options.file_summary,
        max_file_bytes=options.max_file_bytes,
        max_total_bytes=options.max_total_bytes,
        max_file_tokens=options.max_file_tokens,
        max_total_tokens=options.max_total_tokens,
        max_workers=options.max_workers,
    )


__all__ = [
    "BudgetOptions",
    "FocusOptions",
    "OutputOptions",
    "SafetyOptions",
    "SidecarOptions",
    "budget_options_from_pack",
    "focus_options_from_pack",
    "output_options_from_pack",
    "safety_options_from_pack",
    "sidecar_options_from_pack",
]
