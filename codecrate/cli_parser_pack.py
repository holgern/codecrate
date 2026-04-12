from __future__ import annotations

import argparse
from pathlib import Path

from .config import INCLUDE_PRESETS, INDEX_JSON_MODES, SUPPORTED_PROFILES


def _add_pack_inputs(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "root",
        type=Path,
        nargs="*",
        help="One or more root directories to scan",
    )
    pack.add_argument(
        "--repo",
        action="append",
        default=None,
        type=Path,
        help=(
            "Additional repo root to pack "
            "(repeatable; alternative to positional ROOTs)"
        ),
    )
    stdin_group = pack.add_mutually_exclusive_group()
    stdin_group.add_argument(
        "--stdin",
        action="store_true",
        help=(
            "Read explicit file paths from stdin (one per line). "
            "Include globs are not applied; excludes/ignore files still apply."
        ),
    )
    stdin_group.add_argument(
        "--stdin0",
        action="store_true",
        help=(
            "Read explicit file paths from stdin as NUL-separated entries. "
            "Include globs are not applied; excludes/ignore files still apply."
        ),
    )
    pack.add_argument(
        "--print-files",
        action="store_true",
        help="Debug: print selected files after filtering",
    )
    pack.add_argument(
        "--print-skipped",
        action="store_true",
        help="Debug: print skipped files with reasons",
    )
    pack.add_argument(
        "--print-rules",
        action="store_true",
        help="Debug: print effective include/exclude/ignore/safety rules",
    )


def _add_pack_output_args(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output markdown path (default: config 'output' or context.md)",
    )
    pack.add_argument(
        "--profile",
        choices=list(SUPPORTED_PROFILES),
        default=None,
        help=(
            "Output defaults profile: human keeps current behavior, "
            "agent implies compact nav + normalized v3 index-json, "
            "lean-agent implies compact nav + lean normalized v3 index-json, "
            "hybrid implies full index-json, "
            "portable implies full layout with manifest for standalone unpack, "
            "portable-agent implies full layout plus standalone unpacker and "
            "normalized index-json."
        ),
    )
    pack.add_argument(
        "--dedupe",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Deduplicate identical function bodies (default: off via config)",
    )
    pack.add_argument(
        "--encoding-errors",
        choices=["replace", "strict"],
        default=None,
        help="UTF-8 decode policy for input files (default: replace via config)",
    )
    pack.add_argument(
        "--layout",
        choices=["auto", "stubs", "full"],
        default=None,
        help="Output layout: auto|stubs|full (default: auto via config)",
    )
    pack.add_argument(
        "--nav-mode",
        choices=["auto", "compact", "full"],
        default=None,
        help=(
            "Navigation density: auto|compact|full "
            "(auto: compact unsplit, full when split outputs are requested)."
        ),
    )
    pack.add_argument(
        "--symbol-backend",
        choices=["auto", "python", "tree-sitter", "none"],
        default=None,
        help=(
            "Optional non-Python symbol backend: auto|python|tree-sitter|none "
            "(Python files always use AST)."
        ),
    )
    pack.add_argument(
        "--keep-docstrings",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Keep docstrings in stubbed file view (default: true via config)",
    )
    pack.add_argument(
        "--manifest",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include Manifest section (default: true via config)",
    )


def _add_pack_safety_args(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "--respect-gitignore",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Respect .gitignore (default: true via config)",
    )
    pack.add_argument(
        "--security-check",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Scan files with safety filters (default: on). "
            "Use --no-security-check to skip scanning for sensitive data like "
            "API keys and passwords."
        ),
    )
    pack.add_argument(
        "--security-content-sniff",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable content sniffing for sensitive patterns (default: off via config)."
        ),
    )
    pack.add_argument(
        "--security-redaction",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Redact sensitive content instead of skipping flagged files.",
    )
    pack.add_argument(
        "--safety-report",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include an in-pack Safety Report section with file-level reasons.",
    )
    pack.add_argument(
        "--security-path-pattern",
        action="append",
        default=None,
        help="Override sensitive path rule set (repeatable glob patterns).",
    )
    pack.add_argument(
        "--security-path-pattern-add",
        action="append",
        default=None,
        help="Add sensitive path rules without replacing the base set.",
    )
    pack.add_argument(
        "--security-path-pattern-remove",
        action="append",
        default=None,
        help="Remove sensitive path rules from the base set.",
    )
    pack.add_argument(
        "--security-content-pattern",
        action="append",
        default=None,
        help=(
            "Override sensitive content rule set (repeatable regex; "
            "optional name=regex form)."
        ),
    )
    pack.add_argument(
        "--include",
        action="append",
        default=None,
        help="Include glob (repeatable)",
    )
    pack.add_argument(
        "--include-preset",
        choices=sorted(INCLUDE_PRESETS),
        default=None,
        help="Include preset: python-only | python+docs | everything",
    )
    pack.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Exclude glob (repeatable)",
    )


def _add_pack_focus_args(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "--analysis-metadata",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Include analysis-oriented metadata such as repository guide, import "
            "graph, test links, and richer file/symbol facts (default: on via config)."
        ),
    )
    pack.add_argument(
        "--focus-file",
        action="append",
        default=None,
        help=(
            "Focus packing on a repo-relative file path. Repeatable. Can be combined "
            "with import-neighbor and test expansion."
        ),
    )
    pack.add_argument(
        "--focus-symbol",
        action="append",
        default=None,
        help=(
            "Focus packing on a symbol, typically MODULE:QUALNAME (for example "
            "codecrate.cli:main). Repeatable."
        ),
    )
    pack.add_argument(
        "--include-import-neighbors",
        type=int,
        default=None,
        help="Expand focused packs by this many local import-graph hops (default: 0).",
    )
    pack.add_argument(
        "--include-reverse-import-neighbors",
        type=int,
        default=None,
        help=(
            "Expand focused packs by this many reverse local import hops "
            "(callers/dependents only; default: 0)."
        ),
    )
    pack.add_argument(
        "--include-same-package",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include same-package sibling files when focus options are used.",
    )
    pack.add_argument(
        "--include-entrypoints",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include entrypoint files that transitively reach focused files.",
    )
    pack.add_argument(
        "--include-tests",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include heuristically related test files when focus options are used.",
    )


def _add_pack_budget_args(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "--split-max-chars",
        type=int,
        default=None,
        help=(
            "Max chars per split part. Oversized logical blocks remain intact by "
            "default unless --split-strict is set."
        ),
    )
    pack.add_argument(
        "--split-strict",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Fail when a logical split block exceeds --split-max-chars.",
    )
    pack.add_argument(
        "--split-allow-cut-files",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Explicitly allow cutting oversized file blocks into multiple parts.",
    )
    pack.add_argument(
        "--token-count-tree",
        nargs="?",
        metavar="threshold",
        const="-1",
        default=None,
        help=(
            "Show file tree with token counts; optional threshold to show only "
            "files with >=N tokens (e.g., --token-count-tree 100)."
        ),
    )
    pack.add_argument(
        "--top-files-len",
        type=int,
        default=None,
        help=(
            "When printing token counts, show this many largest files "
            "(default: 5 via config)."
        ),
    )
    pack.add_argument(
        "--token-count-encoding",
        type=str,
        default=None,
        help=(
            "Tokenizer encoding for token counting "
            "(tiktoken; default: o200k_base via config)."
        ),
    )
    pack.add_argument(
        "--file-summary",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print pack summary (default: on via config).",
    )
    pack.add_argument(
        "--max-file-bytes",
        type=int,
        default=None,
        help="Skip files larger than this byte limit (<=0 disables).",
    )
    pack.add_argument(
        "--max-total-bytes",
        type=int,
        default=None,
        help="Fail if included files exceed this total byte limit (<=0 disables).",
    )
    pack.add_argument(
        "--max-file-tokens",
        type=int,
        default=None,
        help="Skip files above this token limit (<=0 disables).",
    )
    pack.add_argument(
        "--max-total-tokens",
        type=int,
        default=None,
        help="Fail if included files exceed this total token limit (<=0 disables).",
    )
    pack.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max worker threads for IO/parsing/token counting (<=0 uses auto).",
    )


def _add_pack_sidecar_args(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "--manifest-json",
        nargs="?",
        const="",
        default=None,
        help=(
            "Write manifest JSON for tooling. Optionally pass output path; "
            "without a path writes <output>.manifest.json"
        ),
    )
    pack.add_argument(
        "--index-json",
        nargs="?",
        const="",
        default=None,
        help=(
            "Write index JSON for agent/tooling lookup. Optionally pass output "
            "path; without a path writes <output>.index.json. Explicit "
            "--index-json preserves profile/config sidecar mode defaults unless "
            "--index-json-mode overrides them."
        ),
    )
    pack.add_argument(
        "--index-json-mode",
        choices=list(INDEX_JSON_MODES),
        default=None,
        help=(
            "Index JSON mode: full (v1-compatible), compact/minimal (v2), or "
            "normalized (v3). "
            "Specifying a mode enables index-json output."
        ),
    )
    pack.add_argument(
        "--index-json-pretty",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Pretty-print index-json output instead of minifying it.",
    )
    pack.add_argument(
        "--index-json-lookup",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Include lookup maps in compact/minimal v2 sidecars "
            "(default: on via config)."
        ),
    )
    pack.add_argument(
        "--index-json-symbol-index-lines",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Include unsplit symbol index line ranges in compact v2 sidecars "
            "(default: on via config)."
        ),
    )
    pack.add_argument(
        "--index-json-graph",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include import-graph metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-test-links",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include source-to-test linkage metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-guide",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include repository guide and architecture metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-file-imports",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include per-file import metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-classes",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include class payloads in index-json output.",
    )
    pack.add_argument(
        "--index-json-exports",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include per-file export metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-module-docstrings",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include module docstring ranges in index-json output.",
    )
    pack.add_argument(
        "--index-json-semantic",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include semantic signature metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-purpose-text",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include human-readable purpose text in index-json output.",
    )
    pack.add_argument(
        "--index-json-symbol-locators",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include symbol locator payloads in index-json output.",
    )
    pack.add_argument(
        "--index-json-symbol-references",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include symbol reference and call-like metadata in index-json output.",
    )
    pack.add_argument(
        "--index-json-file-summaries",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include per-file summary payloads in index-json output.",
    )
    pack.add_argument(
        "--index-json-relationships",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include per-file relationship payloads in index-json output.",
    )
    pack.add_argument(
        "--no-index-json",
        action="store_true",
        help="Disable index JSON output, including profile-implied defaults.",
    )
    pack.add_argument(
        "--emit-standalone-unpacker",
        action="store_true",
        default=None,
        help=(
            "Write a standard-library-only <output>.unpack.py next to the pack. "
            "Requires a manifest-enabled pack."
        ),
    )
    pack.add_argument(
        "--locator-space",
        choices=["auto", "markdown", "reconstructed", "dual"],
        default=None,
        help=(
            "Locator targets for index-json: auto resolves to reconstructed when "
            "--emit-standalone-unpacker is enabled, otherwise markdown."
        ),
    )


def _add_pack_markdown_args(pack: argparse.ArgumentParser) -> None:
    pack.add_argument(
        "--markdown-repository-guide",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include the Repository Guide section in markdown output.",
    )
    pack.add_argument(
        "--markdown-symbol-index",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include the Symbol Index section in markdown output.",
    )
    pack.add_argument(
        "--markdown-directory-tree",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include the Directory Tree section in markdown output.",
    )
    pack.add_argument(
        "--markdown-environment-setup",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include the Environment Setup section in markdown output.",
    )
    pack.add_argument(
        "--markdown-how-to-use",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include the How to Use This Pack section in markdown output.",
    )


def _add_pack_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    pack = subparsers.add_parser(
        "pack", help="Pack one or more repositories/directories into Markdown."
    )
    _add_pack_inputs(pack)
    _add_pack_output_args(pack)
    _add_pack_safety_args(pack)
    _add_pack_focus_args(pack)
    _add_pack_budget_args(pack)
    _add_pack_sidecar_args(pack)
    _add_pack_markdown_args(pack)


__all__ = ["_add_pack_parser"]
