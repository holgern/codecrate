from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
from pathlib import Path

from .cli_parser_pack import _add_pack_parser


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
