from __future__ import annotations

import json
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal, cast

from .security import (
    DEFAULT_SENSITIVE_CONTENT_PATTERNS,
    DEFAULT_SENSITIVE_PATH_PATTERNS,
)

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

CONFIG_FILENAMES: tuple[str, ...] = (".codecrate.toml", "codecrate.toml")
PYPROJECT_FILENAME = "pyproject.toml"

DEFAULT_INCLUDES: list[str] = [
    "**/*.py",
    # Common packaging + repo metadata
    "pyproject.toml",
    "project.toml",
    "setup.cfg",
    "README*",
    "LICENSE*",
    # Docs
    "docs/**/*.rst",
    "docs/**/*.md",
]

INCLUDE_PRESETS: dict[str, list[str]] = {
    "python-only": ["**/*.py"],
    "python+docs": DEFAULT_INCLUDES,
    "everything": ["**/*"],
}
DEFAULT_INCLUDE_PRESET: Literal["python+docs"] = "python+docs"

ProfileValue = Literal[
    "human",
    "agent",
    "lean-agent",
    "hybrid",
    "portable",
    "portable-agent",
]
LayoutValue = Literal["auto", "stubs", "full"]
IncludePresetValue = Literal["python-only", "python+docs", "everything"]
NavModeValue = Literal["auto", "compact", "full"]
IndexJsonModeValue = Literal["full", "compact", "minimal", "normalized"]
LocatorSpaceValue = Literal["auto", "markdown", "reconstructed", "dual"]
SymbolBackendValue = Literal["auto", "python", "tree-sitter", "none"]
EncodingErrorsValue = Literal["replace", "strict"]

_SECTION_MISSING = object()


def include_patterns_for_preset(name: str) -> list[str]:
    return list(INCLUDE_PRESETS.get(name, INCLUDE_PRESETS[DEFAULT_INCLUDE_PRESET]))


@dataclass
class Config:
    # Default output path for `codecrate pack` when CLI does not specify -o/--output
    output: str = "context.md"
    keep_docstrings: bool = True
    dedupe: bool = False
    respect_gitignore: bool = True
    include: list[str] = field(default_factory=lambda: DEFAULT_INCLUDES.copy())
    include_preset: IncludePresetValue = DEFAULT_INCLUDE_PRESET
    exclude: list[str] = field(default_factory=list)
    split_max_chars: int = 0  # 0 means no splitting
    # Split policy for oversized logical blocks.
    # By default, oversized file/function blocks stay intact in an oversize part.
    split_strict: bool = False
    split_allow_cut_files: bool = False
    # Emit the `## Manifest` section (required for unpack/patch/validate-pack).
    # Disable only for LLM-only packs to save tokens.
    manifest: bool = True
    # Output defaults profile.
    # - "human": preserve current markdown-first behavior
    # - "agent": emit compact navigation and normalized v3 sidecar defaults
    # - "lean-agent": emit the leanest recommended agent defaults
    # - "hybrid": preserve current markdown behavior but emit index-json by default
    # - "portable": prefer manifest-enabled full-layout output for standalone unpack
    # - "portable-agent": reconstructable full layout plus normalized sidecar defaults
    profile: ProfileValue = "human"
    # Output layout:
    # - "stubs": always emit stubbed files + Function Library (current format)
    # - "full":  emit full file contents (no Function Library)
    # - "auto":  use "stubs" only if dedupe actually collapses something,
    #            otherwise use "full" (best token efficiency when no duplicates)
    layout: LayoutValue = "auto"
    # Token counting (CLI diagnostics; not included in pack output).
    token_count_encoding: str = "o200k_base"
    token_count_tree: bool = False
    token_count_tree_threshold: int = 0
    top_files_len: int = 5
    # Pack-size budgets; <=0 disables each limit.
    max_file_bytes: int = 0
    max_total_bytes: int = 0
    max_file_tokens: int = 0
    max_total_tokens: int = 0
    # Worker pool size for file IO/parsing/token diagnostics. <=0 means auto.
    max_workers: int = 0
    file_summary: bool = True
    # Safety filter for potentially sensitive files.
    security_check: bool = True
    security_content_sniff: bool = False
    security_redaction: bool = False
    safety_report: bool = False
    security_path_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_PATH_PATTERNS)
    )
    security_path_patterns_add: list[str] = field(default_factory=list)
    security_path_patterns_remove: list[str] = field(default_factory=list)
    security_content_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_CONTENT_PATTERNS)
    )
    # Navigation density for markdown pack output.
    # - "compact": omit file-level jump anchors/back-links to save tokens
    # - "full": keep all navigation helpers
    # - "auto": compact for unsplit packs, full when split outputs are requested
    nav_mode: NavModeValue = "auto"
    # Retrieval sidecar mode for index-json output.
    # - None: let profile/default behavior decide whether to emit it
    # - "full": current v1-compatible sidecar
    # - "compact": slimmer v2 retrieval sidecar
    # - "minimal": smallest v2-compatible retrieval sidecar
    index_json_mode: IndexJsonModeValue | None = None
    # Optional explicit sidecar enablement, independent of mode/profile defaults.
    index_json_enabled: bool | None = None
    # Optional config-driven sidecar output paths.
    # - None: do not force a sidecar
    # - "": use the default sibling path
    # - "<path>": write to the explicit path
    manifest_json_output: str | None = None
    index_json_output: str | None = None
    # Write a standard-library-only <output>.unpack.py next to the pack.
    emit_standalone_unpacker: bool = False
    standalone_unpacker_output: str | None = None
    # Preferred locator targets for index-json output.
    # - "auto": reconstructed when a standalone unpacker is emitted, else markdown
    # - "markdown": locators target the rendered markdown pack
    # - "reconstructed": locators target reconstructed output files
    # - "dual": emit both locator families
    locator_space: LocatorSpaceValue = "auto"
    # Optional sidecar payload trimming controls.
    index_json_pretty: bool | None = None
    # - index_json_include_lookup: include lookup maps in v2 sidecars
    # - index_json_include_symbol_index_lines: include unsplit symbol index lines
    index_json_include_lookup: bool | None = None
    index_json_include_symbol_index_lines: bool | None = None
    index_json_include_graph: bool | None = None
    index_json_include_test_links: bool | None = None
    index_json_include_guide: bool | None = None
    index_json_include_file_imports: bool | None = None
    index_json_include_classes: bool | None = None
    index_json_include_exports: bool | None = None
    index_json_include_module_docstrings: bool | None = None
    index_json_include_semantic: bool | None = None
    index_json_include_purpose_text: bool | None = None
    index_json_include_symbol_locators: bool | None = None
    index_json_include_symbol_references: bool | None = None
    index_json_include_file_summaries: bool | None = None
    index_json_include_relationships: bool | None = None
    # Analysis metadata and focused packing controls.
    analysis_metadata: bool | None = None
    markdown_include_repository_guide: bool | None = None
    markdown_include_symbol_index: bool | None = None
    markdown_include_directory_tree: bool | None = None
    markdown_include_environment_setup: bool | None = None
    markdown_include_how_to_use: bool | None = None
    focus_file: list[str] = field(default_factory=list)
    focus_symbol: list[str] = field(default_factory=list)
    include_import_neighbors: int = 0
    include_reverse_import_neighbors: int = 0
    include_same_package: bool = False
    include_entrypoints: bool = False
    include_tests: bool = False
    # Optional symbol extraction backend for non-Python files.
    # Python files always use the built-in AST parser.
    symbol_backend: SymbolBackendValue = "auto"
    # Text decoding behavior when reading repository/markdown files.
    # - "replace": preserve operation by replacing invalid bytes (default)
    # - "strict": fail on invalid UTF-8 bytes
    encoding_errors: EncodingErrorsValue = "replace"


@dataclass(frozen=True)
class ConfigWarning:
    key: str
    raw_value: Any
    fallback: Any
    message: str


@dataclass(frozen=True)
class ConfigValueProvenance:
    source: str
    config_key: str | None


@dataclass(frozen=True)
class LoadedConfig:
    config: Config
    warnings: list[ConfigWarning]
    provenance: dict[str, ConfigValueProvenance]
    selected_path: Path | None


@dataclass(frozen=True)
class ConfigFieldMetadata:
    type_name: str
    description: str
    cli_flags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    access: Literal["both", "config-only", "cli-only"] = "both"
    choices: tuple[str, ...] = ()


CONFIG_FIELD_METADATA: dict[str, ConfigFieldMetadata] = {
    "output": ConfigFieldMetadata(
        type_name="string",
        description="Default markdown output path for pack runs.",
        cli_flags=("-o", "--output"),
    ),
    "keep_docstrings": ConfigFieldMetadata(
        type_name="boolean",
        description="Keep docstrings in stubbed file output.",
        cli_flags=("--keep-docstrings", "--no-keep-docstrings"),
    ),
    "dedupe": ConfigFieldMetadata(
        type_name="boolean",
        description="Deduplicate identical function bodies.",
        cli_flags=("--dedupe", "--no-dedupe"),
    ),
    "respect_gitignore": ConfigFieldMetadata(
        type_name="boolean",
        description="Respect .gitignore during file discovery.",
        cli_flags=("--respect-gitignore", "--no-respect-gitignore"),
    ),
    "include": ConfigFieldMetadata(
        type_name="list[string]",
        description="Include glob patterns.",
        cli_flags=("--include",),
    ),
    "include_preset": ConfigFieldMetadata(
        type_name="enum",
        description="Fallback include preset when include is not set.",
        cli_flags=("--include-preset",),
        choices=("python-only", "python+docs", "everything"),
    ),
    "exclude": ConfigFieldMetadata(
        type_name="list[string]",
        description="Exclude glob patterns.",
        cli_flags=("--exclude",),
    ),
    "split_max_chars": ConfigFieldMetadata(
        type_name="integer",
        description="Split markdown output when it exceeds this many characters.",
        cli_flags=("--split-max-chars",),
    ),
    "split_strict": ConfigFieldMetadata(
        type_name="boolean",
        description="Fail when a logical split block exceeds split_max_chars.",
        cli_flags=("--split-strict", "--no-split-strict"),
    ),
    "split_allow_cut_files": ConfigFieldMetadata(
        type_name="boolean",
        description="Allow oversized files to be cut across split parts.",
        cli_flags=("--split-allow-cut-files", "--no-split-allow-cut-files"),
    ),
    "manifest": ConfigFieldMetadata(
        type_name="boolean",
        description="Include the Manifest section in generated markdown.",
        cli_flags=("--manifest", "--no-manifest"),
        aliases=("include_manifest",),
    ),
    "profile": ConfigFieldMetadata(
        type_name="enum",
        description="Output defaults profile.",
        cli_flags=("--profile",),
        choices=(
            "human",
            "agent",
            "lean-agent",
            "hybrid",
            "portable",
            "portable-agent",
        ),
    ),
    "layout": ConfigFieldMetadata(
        type_name="enum",
        description="Markdown layout mode.",
        cli_flags=("--layout",),
        choices=("auto", "stubs", "full"),
    ),
    "token_count_encoding": ConfigFieldMetadata(
        type_name="string",
        description="Tokenizer encoding for CLI token diagnostics.",
        cli_flags=("--token-count-encoding",),
    ),
    "token_count_tree": ConfigFieldMetadata(
        type_name="boolean",
        description="Enable CLI token tree reporting.",
        cli_flags=("--token-count-tree",),
    ),
    "token_count_tree_threshold": ConfigFieldMetadata(
        type_name="integer",
        description="Minimum token threshold for token tree reporting.",
    ),
    "top_files_len": ConfigFieldMetadata(
        type_name="integer",
        description="Number of largest files to print in CLI token diagnostics.",
        cli_flags=("--top-files-len",),
    ),
    "max_file_bytes": ConfigFieldMetadata(
        type_name="integer",
        description="Skip files larger than this many bytes.",
        cli_flags=("--max-file-bytes",),
    ),
    "max_total_bytes": ConfigFieldMetadata(
        type_name="integer",
        description="Fail if the included file set exceeds this many bytes.",
        cli_flags=("--max-total-bytes",),
    ),
    "max_file_tokens": ConfigFieldMetadata(
        type_name="integer",
        description="Skip files larger than this many tokens.",
        cli_flags=("--max-file-tokens",),
    ),
    "max_total_tokens": ConfigFieldMetadata(
        type_name="integer",
        description="Fail if the included file set exceeds this many tokens.",
        cli_flags=("--max-total-tokens",),
    ),
    "max_workers": ConfigFieldMetadata(
        type_name="integer",
        description="Worker count for IO, parsing, and token counting.",
        cli_flags=("--max-workers",),
    ),
    "file_summary": ConfigFieldMetadata(
        type_name="boolean",
        description="Print the CLI pack summary block.",
        cli_flags=("--file-summary", "--no-file-summary"),
    ),
    "security_check": ConfigFieldMetadata(
        type_name="boolean",
        description="Enable sensitive-file safety checks.",
        cli_flags=("--security-check", "--no-security-check"),
    ),
    "security_content_sniff": ConfigFieldMetadata(
        type_name="boolean",
        description="Scan file content for sensitive patterns.",
        cli_flags=("--security-content-sniff", "--no-security-content-sniff"),
    ),
    "security_redaction": ConfigFieldMetadata(
        type_name="boolean",
        description="Redact flagged files instead of skipping them.",
        cli_flags=("--security-redaction", "--no-security-redaction"),
    ),
    "safety_report": ConfigFieldMetadata(
        type_name="boolean",
        description="Include the Safety Report section in generated markdown.",
        cli_flags=("--safety-report", "--no-safety-report"),
    ),
    "security_path_patterns": ConfigFieldMetadata(
        type_name="list[string]",
        description="Base sensitive-path glob rules.",
        cli_flags=("--security-path-pattern",),
    ),
    "security_path_patterns_add": ConfigFieldMetadata(
        type_name="list[string]",
        description="Additional sensitive-path glob rules.",
        cli_flags=("--security-path-pattern-add",),
    ),
    "security_path_patterns_remove": ConfigFieldMetadata(
        type_name="list[string]",
        description="Sensitive-path glob rules to remove from the base set.",
        cli_flags=("--security-path-pattern-remove",),
    ),
    "security_content_patterns": ConfigFieldMetadata(
        type_name="list[string]",
        description="Sensitive-content regex rules.",
        cli_flags=("--security-content-pattern",),
    ),
    "nav_mode": ConfigFieldMetadata(
        type_name="enum",
        description="Navigation density in generated markdown.",
        cli_flags=("--nav-mode",),
        choices=("auto", "compact", "full"),
    ),
    "index_json_mode": ConfigFieldMetadata(
        type_name="enum|null",
        description="Index-json format mode.",
        cli_flags=("--index-json-mode",),
        choices=("full", "compact", "minimal", "normalized"),
    ),
    "index_json_enabled": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Explicitly enable or disable index-json output.",
        cli_flags=("--index-json", "--no-index-json"),
    ),
    "manifest_json_output": ConfigFieldMetadata(
        type_name="string|null",
        description=(
            "Optional manifest JSON output path; empty string uses the "
            "default sibling path."
        ),
        cli_flags=("--manifest-json",),
    ),
    "index_json_output": ConfigFieldMetadata(
        type_name="string|null",
        description=(
            "Optional index-json output path; empty string uses the default "
            "sibling path."
        ),
        cli_flags=("--index-json",),
    ),
    "emit_standalone_unpacker": ConfigFieldMetadata(
        type_name="boolean",
        description="Write a standalone unpacker next to the markdown output.",
        cli_flags=("--emit-standalone-unpacker",),
    ),
    "standalone_unpacker_output": ConfigFieldMetadata(
        type_name="string|null",
        description=(
            "Optional standalone unpacker output path; empty string uses the "
            "default sibling path."
        ),
        access="config-only",
    ),
    "locator_space": ConfigFieldMetadata(
        type_name="enum",
        description="Locator target space for index-json payloads.",
        cli_flags=("--locator-space",),
        choices=("auto", "markdown", "reconstructed", "dual"),
    ),
    "index_json_pretty": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Pretty-print index-json output instead of minifying it.",
        cli_flags=("--index-json-pretty", "--no-index-json-pretty"),
    ),
    "index_json_include_lookup": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include lookup tables in compact/minimal v2 index-json output.",
        cli_flags=("--index-json-lookup", "--no-index-json-lookup"),
    ),
    "index_json_include_symbol_index_lines": ConfigFieldMetadata(
        type_name="boolean|null",
        description=(
            "Include unsplit symbol index line ranges in compact v2 index-json output."
        ),
        cli_flags=(
            "--index-json-symbol-index-lines",
            "--no-index-json-symbol-index-lines",
        ),
    ),
    "index_json_include_graph": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include import-graph metadata in index-json output.",
        cli_flags=("--index-json-graph", "--no-index-json-graph"),
    ),
    "index_json_include_test_links": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include source-to-test links in index-json output.",
        cli_flags=("--index-json-test-links", "--no-index-json-test-links"),
    ),
    "index_json_include_guide": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include repository guide metadata in index-json output.",
        cli_flags=("--index-json-guide", "--no-index-json-guide"),
    ),
    "index_json_include_file_imports": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include per-file import metadata in index-json output.",
        cli_flags=("--index-json-file-imports", "--no-index-json-file-imports"),
    ),
    "index_json_include_classes": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include class payloads in index-json output.",
        cli_flags=("--index-json-classes", "--no-index-json-classes"),
    ),
    "index_json_include_exports": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include per-file export metadata in index-json output.",
        cli_flags=("--index-json-exports", "--no-index-json-exports"),
    ),
    "index_json_include_module_docstrings": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include module docstring line ranges in index-json output.",
        cli_flags=(
            "--index-json-module-docstrings",
            "--no-index-json-module-docstrings",
        ),
    ),
    "index_json_include_semantic": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include semantic signature metadata in index-json output.",
        cli_flags=("--index-json-semantic", "--no-index-json-semantic"),
    ),
    "index_json_include_purpose_text": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include human-readable purpose text in index-json output.",
        cli_flags=("--index-json-purpose-text", "--no-index-json-purpose-text"),
    ),
    "index_json_include_symbol_locators": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include symbol locator payloads in index-json output.",
        cli_flags=("--index-json-symbol-locators", "--no-index-json-symbol-locators"),
    ),
    "index_json_include_symbol_references": ConfigFieldMetadata(
        type_name="boolean|null",
        description=(
            "Include symbol reference and call-like metadata in index-json output."
        ),
        cli_flags=(
            "--index-json-symbol-references",
            "--no-index-json-symbol-references",
        ),
    ),
    "index_json_include_file_summaries": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include per-file summary payloads in index-json output.",
        cli_flags=(
            "--index-json-file-summaries",
            "--no-index-json-file-summaries",
        ),
    ),
    "index_json_include_relationships": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include per-file relationship payloads in index-json output.",
        cli_flags=(
            "--index-json-relationships",
            "--no-index-json-relationships",
        ),
    ),
    "analysis_metadata": ConfigFieldMetadata(
        type_name="boolean|null",
        description=(
            "Default on/off switch for analysis-oriented metadata in generated outputs."
        ),
        cli_flags=("--analysis-metadata", "--no-analysis-metadata"),
    ),
    "markdown_include_repository_guide": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include the Repository Guide section in generated markdown.",
        cli_flags=(
            "--markdown-repository-guide",
            "--no-markdown-repository-guide",
        ),
    ),
    "markdown_include_symbol_index": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include the Symbol Index section in generated markdown.",
        cli_flags=("--markdown-symbol-index", "--no-markdown-symbol-index"),
    ),
    "markdown_include_directory_tree": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include the Directory Tree section in generated markdown.",
        cli_flags=("--markdown-directory-tree", "--no-markdown-directory-tree"),
    ),
    "markdown_include_environment_setup": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include the Environment Setup section in generated markdown.",
        cli_flags=(
            "--markdown-environment-setup",
            "--no-markdown-environment-setup",
        ),
    ),
    "markdown_include_how_to_use": ConfigFieldMetadata(
        type_name="boolean|null",
        description="Include the How to Use This Pack section in generated markdown.",
        cli_flags=("--markdown-how-to-use", "--no-markdown-how-to-use"),
    ),
    "focus_file": ConfigFieldMetadata(
        type_name="list[string]",
        description="Focus pack generation on specific repo-relative files.",
        cli_flags=("--focus-file",),
    ),
    "focus_symbol": ConfigFieldMetadata(
        type_name="list[string]",
        description="Focus pack generation on specific symbols.",
        cli_flags=("--focus-symbol",),
    ),
    "include_import_neighbors": ConfigFieldMetadata(
        type_name="integer",
        description=(
            "Include this many local import-neighbor hops around focused files."
        ),
        cli_flags=("--include-import-neighbors",),
    ),
    "include_reverse_import_neighbors": ConfigFieldMetadata(
        type_name="integer",
        description=(
            "Include this many reverse local import-neighbor hops around focused files."
        ),
        cli_flags=("--include-reverse-import-neighbors",),
    ),
    "include_same_package": ConfigFieldMetadata(
        type_name="boolean",
        description="Include same-package neighbors in focused packs.",
        cli_flags=("--include-same-package", "--no-include-same-package"),
    ),
    "include_entrypoints": ConfigFieldMetadata(
        type_name="boolean",
        description="Include entrypoints that reach focused files.",
        cli_flags=("--include-entrypoints", "--no-include-entrypoints"),
    ),
    "include_tests": ConfigFieldMetadata(
        type_name="boolean",
        description="Include heuristically related tests in focused packs.",
        cli_flags=("--include-tests", "--no-include-tests"),
    ),
    "symbol_backend": ConfigFieldMetadata(
        type_name="enum",
        description="Optional non-Python symbol extraction backend.",
        cli_flags=("--symbol-backend",),
        choices=("auto", "python", "tree-sitter", "none"),
    ),
    "encoding_errors": ConfigFieldMetadata(
        type_name="enum",
        description="UTF-8 decoding policy for repository and markdown reads.",
        cli_flags=("--encoding-errors",),
        choices=("replace", "strict"),
    ),
}


def _config_default(field_name: str) -> Any:
    field_info = next(item for item in fields(Config) if item.name == field_name)
    if field_info.default_factory is not MISSING:
        return field_info.default_factory()
    return field_info.default


def config_field_names() -> tuple[str, ...]:
    return tuple(field_info.name for field_info in fields(Config))


def config_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for name, metadata in CONFIG_FIELD_METADATA.items():
        for alias in metadata.aliases:
            aliases[alias] = name
    return aliases


def config_field_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name in config_field_names():
        metadata = CONFIG_FIELD_METADATA[name]
        specs.append(
            {
                "name": name,
                "type": metadata.type_name,
                "default": _config_default(name),
                "description": metadata.description,
                "cli_flags": list(metadata.cli_flags),
                "aliases": list(metadata.aliases),
                "access": metadata.access,
                "choices": list(metadata.choices),
            }
        )
    return specs


def config_schema_payload() -> dict[str, Any]:
    return {
        "format": "codecrate.config-schema.v1",
        "precedence": [
            "CLI flags",
            ".codecrate.toml",
            "codecrate.toml",
            "pyproject.toml[tool.codecrate]",
        ],
        "fields": config_field_specs(),
    }


def render_config_reference_rst() -> str:
    def _csv_cell(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    lines = [
        "Configuration Reference",
        "=======================",
        "",
        ".. NOTE:: This page is generated from ``codecrate.config``. Update the",
        "   config metadata in code and regenerate the file instead of editing it",
        "   by hand.",
        "",
        "Precedence",
        "----------",
        "",
        "1. CLI flags",
        "2. ``.codecrate.toml`` / ``codecrate.toml``",
        "3. ``pyproject.toml`` under ``[tool.codecrate]``",
        "",
        "Profile chooser",
        "---------------",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        "",
        "   * - Use case",
        "     - Profile",
        "     - Notes",
        "   * - Review-only markdown",
        "     - ``human``",
        "     - Markdown-first output without profile-implied index-json sidecars.",
        "   * - Retrieval and agent lookup",
        "     - ``agent``",
        "     - Compact navigation plus normalized v3 index-json output.",
        "   * - Lean agent retrieval",
        "     - ``lean-agent``",
        (
            "     - Compact navigation plus minified normalized v3 sidecars with "
            "lean analysis defaults."
        ),
        "   * - Review plus tooling",
        "     - ``hybrid``",
        "     - Rich markdown plus the full v1-compatible index-json sidecar.",
        "   * - Portable reconstruction",
        "     - ``portable``",
        "     - Manifest-enabled ``full`` layout tuned for standalone unpacking.",
        "   * - Portable retrieval + reconstruction",
        "     - ``portable-agent``",
        (
            "     - Full layout, standalone unpacker, dual locators, and "
            "normalized sidecar defaults."
        ),
        "",
        "TOML versus CLI",
        "---------------",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        "",
        "   * - Capability",
        "     - TOML",
        "     - CLI",
        "     - Notes",
        "   * - Pack-shaping settings below",
        "     - Yes",
        "     - Yes",
        "     - Shared config and CLI support.",
        "   * - Explicit file lists (``--stdin`` / ``--stdin0``)",
        "     - No",
        "     - Yes",
        "     - Operational input mode, not stored in TOML.",
        (
            "   * - Debug printing (``--print-files``, ``--print-skipped``, "
            "``--print-rules``)"
        ),
        "     - No",
        "     - Yes",
        "     - Operational diagnostics only.",
        "   * - Root / multi-repo selection",
        "     - No",
        "     - Yes",
        "     - Runtime repository selection stays CLI-only.",
        "",
        "Supported keys",
        "--------------",
        "",
        ".. csv-table::",
        (
            '   :header: "Key", "Type", "Default", "Access", "CLI", '
            '"Aliases", "Choices", "Description"'
        ),
        "",
    ]
    for field_spec in config_field_specs():
        row = [
            field_spec["name"],
            field_spec["type"],
            json.dumps(field_spec["default"], ensure_ascii=True),
            field_spec["access"],
            ", ".join(field_spec["cli_flags"]) or "none",
            ", ".join(field_spec["aliases"]) or "none",
            ", ".join(field_spec["choices"]) or "none",
            field_spec["description"],
        ]
        lines.append("   " + ", ".join(_csv_cell(str(value)) for value in row))
    return "\n".join(lines).rstrip() + "\n"


def _find_config_path(root: Path) -> Path | None:
    root = root.resolve()
    for name in CONFIG_FILENAMES:
        p = root / name
        if p.exists():
            return p
    pyproject = root / PYPROJECT_FILENAME
    if pyproject.exists():
        return pyproject
    return None


def _config_source_name(path: Path | None) -> str:
    if path is None:
        return "default"
    if path.name == PYPROJECT_FILENAME:
        return "pyproject.toml[tool.codecrate]"
    return path.name


def _extract_section(data: Any, *, from_pyproject: bool) -> dict[str, Any]:
    section: dict[str, Any] = {}
    if not isinstance(data, dict):
        return section

    if not from_pyproject:
        # Preferred for dedicated config files: [codecrate]
        cc = data.get("codecrate")
        if isinstance(cc, dict):
            return cc

    # Supported in all files; required for pyproject.toml.
    tool = data.get("tool")
    if isinstance(tool, dict):
        cc2 = tool.get("codecrate")
        if isinstance(cc2, dict):
            return cc2

    return section


def _default_provenance() -> dict[str, ConfigValueProvenance]:
    return {
        name: ConfigValueProvenance(source="default", config_key=None)
        for name in config_field_names()
    }


def _record_provenance(
    provenance: dict[str, ConfigValueProvenance],
    *,
    field_name: str,
    source: str,
    config_key: str | None,
) -> None:
    provenance[field_name] = ConfigValueProvenance(
        source=source if config_key is not None else "default",
        config_key=config_key,
    )


def _raw_section_value(
    section: dict[str, Any], field_name: str
) -> tuple[str | None, Any]:
    metadata = CONFIG_FIELD_METADATA[field_name]
    if field_name in section:
        return field_name, section[field_name]
    for alias in metadata.aliases:
        if alias in section:
            return alias, section[alias]
    return None, _SECTION_MISSING


def _warn_unknown_keys(section: dict[str, Any], warnings: list[ConfigWarning]) -> None:
    known_keys = set(config_field_names()) | set(config_alias_map())
    for key in sorted(section):
        if key in known_keys:
            continue
        warnings.append(
            ConfigWarning(
                key=key,
                raw_value=section[key],
                fallback=None,
                message="Unknown config key; ignoring.",
            )
        )


def _load_bool_value(
    section: dict[str, Any],
    field_name: str,
    fallback: bool,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> bool:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, bool):
        return raw_value
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=fallback,
            message="Invalid boolean value; using default.",
        )
    )
    return fallback


def _load_optional_bool_value(
    section: dict[str, Any],
    field_name: str,
    fallback: bool | None,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> bool | None:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, bool):
        return raw_value
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=fallback,
            message="Invalid boolean value; using default.",
        )
    )
    return fallback


def _load_int_value(
    section: dict[str, Any],
    field_name: str,
    fallback: int,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> int:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, bool):
        raw_value = str(raw_value)
    try:
        return int(raw_value)
    except (ValueError, TypeError):
        warnings.append(
            ConfigWarning(
                key=config_key,
                raw_value=raw_value,
                fallback=fallback,
                message="Invalid integer value; using default.",
            )
        )
        return fallback


def _load_string_choice(
    section: dict[str, Any],
    field_name: str,
    fallback: str,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> str:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    metadata = CONFIG_FIELD_METADATA[field_name]
    if isinstance(raw_value, str):
        value = raw_value.strip().lower()
        if value in metadata.choices:
            return value
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=fallback,
            message="Invalid string choice; using default.",
        )
    )
    return fallback


def _load_optional_string_choice(
    section: dict[str, Any],
    field_name: str,
    fallback: str | None,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> str | None:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    metadata = CONFIG_FIELD_METADATA[field_name]
    if isinstance(raw_value, str):
        value = raw_value.strip().lower()
        if value in metadata.choices:
            return value
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=fallback,
            message="Invalid string choice; using default.",
        )
    )
    return fallback


def _load_non_empty_string(
    section: dict[str, Any],
    field_name: str,
    fallback: str,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> str:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=fallback,
            message="Invalid string value; using default.",
        )
    )
    return fallback


def _load_optional_output_value(
    section: dict[str, Any],
    field_name: str,
    fallback: str | None,
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> str | None:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return fallback
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, str):
        return raw_value
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=fallback,
            message="Invalid output path value; using default.",
        )
    )
    return fallback


def _load_string_list(
    section: dict[str, Any],
    field_name: str,
    fallback: list[str],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> list[str]:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return list(fallback)
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, list):
        return [str(item) for item in raw_value]
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=list(fallback),
            message="Invalid list value; using default.",
        )
    )
    return list(fallback)


def _load_focus_list(
    section: dict[str, Any],
    field_name: str,
    fallback: list[str],
    *,
    warnings: list[ConfigWarning],
    provenance: dict[str, ConfigValueProvenance],
    source: str,
) -> list[str]:
    config_key, raw_value = _raw_section_value(section, field_name)
    if config_key is None:
        return list(fallback)
    _record_provenance(
        provenance,
        field_name=field_name,
        source=source,
        config_key=config_key,
    )
    if isinstance(raw_value, list):
        return [str(item) for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str) and raw_value.strip():
        return [raw_value.strip()]
    warnings.append(
        ConfigWarning(
            key=config_key,
            raw_value=raw_value,
            fallback=list(fallback),
            message="Invalid focus value; using default.",
        )
    )
    return list(fallback)


def load_config_details(root: Path) -> LoadedConfig:  # noqa: C901
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

    output_key, output_value = _raw_section_value(section, "output")
    if output_key is not None:
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
        else:
            warnings.append(
                ConfigWarning(
                    key=output_key,
                    raw_value=output_value,
                    fallback=cfg.output,
                    message="Invalid output path value; using default.",
                )
            )

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
        if provenance["include_preset"].config_key is not None:
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
    cfg.index_json_pretty = _load_optional_bool_value(
        section,
        "index_json_pretty",
        cfg.index_json_pretty,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_lookup = _load_optional_bool_value(
        section,
        "index_json_include_lookup",
        cfg.index_json_include_lookup,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_symbol_index_lines = _load_optional_bool_value(
        section,
        "index_json_include_symbol_index_lines",
        cfg.index_json_include_symbol_index_lines,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_graph = _load_optional_bool_value(
        section,
        "index_json_include_graph",
        cfg.index_json_include_graph,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_test_links = _load_optional_bool_value(
        section,
        "index_json_include_test_links",
        cfg.index_json_include_test_links,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_guide = _load_optional_bool_value(
        section,
        "index_json_include_guide",
        cfg.index_json_include_guide,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_file_imports = _load_optional_bool_value(
        section,
        "index_json_include_file_imports",
        cfg.index_json_include_file_imports,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_classes = _load_optional_bool_value(
        section,
        "index_json_include_classes",
        cfg.index_json_include_classes,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_exports = _load_optional_bool_value(
        section,
        "index_json_include_exports",
        cfg.index_json_include_exports,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_module_docstrings = _load_optional_bool_value(
        section,
        "index_json_include_module_docstrings",
        cfg.index_json_include_module_docstrings,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_semantic = _load_optional_bool_value(
        section,
        "index_json_include_semantic",
        cfg.index_json_include_semantic,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_purpose_text = _load_optional_bool_value(
        section,
        "index_json_include_purpose_text",
        cfg.index_json_include_purpose_text,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_symbol_locators = _load_optional_bool_value(
        section,
        "index_json_include_symbol_locators",
        cfg.index_json_include_symbol_locators,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_symbol_references = _load_optional_bool_value(
        section,
        "index_json_include_symbol_references",
        cfg.index_json_include_symbol_references,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_file_summaries = _load_optional_bool_value(
        section,
        "index_json_include_file_summaries",
        cfg.index_json_include_file_summaries,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.index_json_include_relationships = _load_optional_bool_value(
        section,
        "index_json_include_relationships",
        cfg.index_json_include_relationships,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.analysis_metadata = _load_optional_bool_value(
        section,
        "analysis_metadata",
        cfg.analysis_metadata,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.markdown_include_repository_guide = _load_optional_bool_value(
        section,
        "markdown_include_repository_guide",
        cfg.markdown_include_repository_guide,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.markdown_include_symbol_index = _load_optional_bool_value(
        section,
        "markdown_include_symbol_index",
        cfg.markdown_include_symbol_index,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.markdown_include_directory_tree = _load_optional_bool_value(
        section,
        "markdown_include_directory_tree",
        cfg.markdown_include_directory_tree,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.markdown_include_environment_setup = _load_optional_bool_value(
        section,
        "markdown_include_environment_setup",
        cfg.markdown_include_environment_setup,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
    cfg.markdown_include_how_to_use = _load_optional_bool_value(
        section,
        "markdown_include_how_to_use",
        cfg.markdown_include_how_to_use,
        warnings=warnings,
        provenance=provenance,
        source=source,
    )
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
