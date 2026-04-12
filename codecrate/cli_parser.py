from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
from pathlib import Path

from .config import INCLUDE_PRESETS


def _codecrate_version() -> str:
    try:
        return importlib_metadata.version("codecrate")
    except importlib_metadata.PackageNotFoundError:
        try:
            from ._version import __version__ as fallback

            return str(fallback)
        except Exception:
            return "0+unknown"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codecrate",
        description="Pack/unpack/patch/apply for repositories  (Python + text files).",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"codecrate {_codecrate_version()}",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    _add_pack_parser(sub)
    _add_unpack_parser(sub)
    _add_patch_parser(sub)
    _add_apply_parser(sub)
    _add_validate_parser(sub)
    _add_doctor_parser(sub)
    _add_config_parser(sub)
    return p


def _add_pack_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    pack = subparsers.add_parser(
        "pack", help="Pack one or more repositories/directories into Markdown."
    )
    pack.add_argument(
        "root",
        type=Path,
        nargs="?",
        help="Root directory to scan (omit when using --repo)",
    )
    pack.add_argument(
        "--repo",
        action="append",
        default=None,
        type=Path,
        help="Additional repo root to pack (repeatable; use instead of ROOT)",
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
    pack.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output markdown path (default: config 'output' or context.md)",
    )
    pack.add_argument(
        "--profile",
        choices=["human", "agent", "lean-agent", "hybrid", "portable"],
        default=None,
        help=(
            "Output defaults profile: human keeps current behavior, "
            "agent implies compact nav + normalized v3 index-json, "
            "lean-agent implies compact nav + lean normalized v3 index-json, "
            "hybrid implies full index-json, "
            "portable implies full layout with manifest for standalone unpack."
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
        "--manifest",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include Manifest section (default: true via config)",
    )
    pack.add_argument(
        "--include", action="append", default=None, help="Include glob (repeatable)"
    )
    pack.add_argument(
        "--include-preset",
        choices=sorted(INCLUDE_PRESETS),
        default=None,
        help="Include preset: python-only | python+docs | everything",
    )
    pack.add_argument(
        "--exclude", action="append", default=None, help="Exclude glob (repeatable)"
    )
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
            "--index-json defaults to full mode unless --index-json-mode overrides it."
        ),
    )
    pack.add_argument(
        "--index-json-mode",
        choices=["full", "compact", "minimal", "normalized"],
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


def _add_unpack_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    unpack = subparsers.add_parser(
        "unpack", help="Reconstruct files from a packed context Markdown."
    )
    unpack.add_argument(
        "markdown",
        type=Path,
        help="Packed Markdown file from `pack`",
    )
    unpack.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        required=True,
        help="Output directory for reconstructed files",
    )
    unpack.add_argument(
        "--strict",
        action="store_true",
        help="Fail when marker-based reconstruction cannot be fully resolved.",
    )
    unpack.add_argument(
        "--encoding-errors",
        choices=["replace", "strict"],
        default=None,
        help="UTF-8 decode policy when reading packed markdown",
    )


def _add_patch_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    patch = subparsers.add_parser(
        "patch",
        help="Generate a diff-only patch Markdown from old pack + current repo.",
    )
    patch.add_argument(
        "old_markdown", type=Path, help="Older packed Markdown (baseline)"
    )
    patch.add_argument("root", type=Path, help="Current repo root to compare against")
    patch.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Repository label or slug when old_markdown contains multiple repos",
    )
    patch.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("patch.md"),
        help="Output patch markdown",
    )
    patch.add_argument(
        "--encoding-errors",
        choices=["replace", "strict"],
        default=None,
        help="UTF-8 decode policy for baseline/current files",
    )


def _add_apply_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    apply = subparsers.add_parser(
        "apply", help="Apply a diff-only patch Markdown to a repo."
    )
    apply.add_argument(
        "patch_markdown", type=Path, help="Patch Markdown containing ```diff blocks"
    )
    apply.add_argument("root", type=Path, help="Repo root to apply patch to")
    apply.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Repository label or slug when patch_markdown contains multiple repos",
    )
    apply.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + validate patch hunks without writing files.",
    )
    baseline_mode = apply.add_mutually_exclusive_group()
    baseline_mode.add_argument(
        "--check-baseline",
        action="store_true",
        help="Require and verify baseline metadata before applying patch.",
    )
    baseline_mode.add_argument(
        "--ignore-baseline",
        action="store_true",
        help="Skip baseline metadata verification.",
    )
    apply.add_argument(
        "--encoding-errors",
        choices=["replace", "strict"],
        default=None,
        help="UTF-8 decode policy for patch and repository files",
    )


def _add_validate_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    vpack = subparsers.add_parser(
        "validate-pack",
        help="Validate a packed context Markdown (sha/markers/canonical consistency).",
    )
    vpack.add_argument(
        "markdown",
        type=Path,
        help="Packed Markdown to validate",
    )
    vpack.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Optional repo root to compare reconstructed files against",
    )
    vpack.add_argument(
        "--strict",
        action="store_true",
        help="Treat unresolved marker mapping as validation errors.",
    )
    vpack.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON validation report.",
    )
    vpack.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero when validation emits any warnings.",
    )
    vpack.add_argument(
        "--fail-on-root-drift",
        action="store_true",
        help="Exit non-zero when on-disk files differ from the pack; requires --root.",
    )
    vpack.add_argument(
        "--fail-on-redaction",
        action="store_true",
        help="Exit non-zero when the pack reports any redacted files.",
    )
    vpack.add_argument(
        "--fail-on-safety-skip",
        action="store_true",
        help="Exit non-zero when the pack reports any safety-skipped files.",
    )
    vpack.add_argument(
        "--encoding-errors",
        choices=["replace", "strict"],
        default=None,
        help="UTF-8 decode policy when reading pack and root files",
    )


def _add_doctor_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    doctor = subparsers.add_parser(
        "doctor", help="Run repository diagnostics and capability checks."
    )
    doctor.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Repository root to inspect (default: .)",
    )


def _add_config_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    config = subparsers.add_parser(
        "config", help="Inspect resolved configuration values."
    )
    config_sub = config.add_subparsers(dest="config_cmd", required=True)
    config_show = config_sub.add_parser(
        "show", help="Show effective configuration for a repository root."
    )
    config_show.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Repository root to inspect (default: .)",
    )
    config_show.add_argument(
        "--effective",
        action="store_true",
        help="Show effective values after config precedence resolution (default).",
    )
    config_show.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON config output.",
    )
    config_schema = config_sub.add_parser(
        "schema", help="Show the supported config keys and metadata."
    )
    config_schema.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON schema output.",
    )


def _print_top_level_help(parser: argparse.ArgumentParser) -> None:
    parser.print_help()
    print()
    print("Quick start examples:")
    print("  codecrate pack . -o context.md")
    print("  codecrate unpack context.md -o out/ --strict")
    print("  codecrate patch baseline.md . -o changes.md")
    print("  codecrate apply changes.md .")
    print("  codecrate validate-pack context.md --strict")
    print("  codecrate doctor .")
    print("  codecrate config show . --effective")
    print()
    print("Explicit-file mode notes:")
    print("  --stdin/--stdin0 treat stdin paths as the candidate set.")
    print("  Include globs are bypassed; exclude + ignore rules still apply.")
    print("  Outside-root and missing files are skipped (see --print-skipped).")
