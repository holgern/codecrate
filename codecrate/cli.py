from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata as importlib_metadata
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from .config import (
    CONFIG_FILENAMES,
    INCLUDE_PRESETS,
    PYPROJECT_FILENAME,
    Config,
    include_patterns_for_preset,
    load_config,
)
from .diffgen import generate_patch_markdown
from .discover import DEFAULT_EXCLUDES, discover_files
from .fences import is_fence_close, parse_fence_open
from .formats import (
    FENCE_PATCH_META,
    MANIFEST_JSON_FORMAT_VERSION,
    MISSING_MANIFEST_ERROR,
)
from .manifest import manifest_sha256, to_manifest
from .markdown import render_markdown
from .packer import pack_repo
from .repositories import (
    select_repository_section,
    slugify_repo_label,
    split_repository_sections,
)
from .security import SafetyFinding, apply_safety_filters, build_ruleset
from .token_budget import Part, split_by_max_chars
from .tokens import (
    TokenCounter,
    approx_token_count,
    format_token_count_tree,
    format_top_files,
    format_top_files_by_size,
)
from .udiff import apply_file_diffs, normalize_newlines, parse_unified_diff
from .unpacker import unpack_to_dir
from .validate import validate_pack_markdown


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

    # pack
    pack = sub.add_parser(
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
        "--split-max-chars",
        type=int,
        default=None,
        help=(
            "Max chars per part file. Oversize single-file parts remain intact by "
            "default unless --split-strict is set."
        ),
    )
    pack.add_argument(
        "--split-strict",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Fail when a single file part exceeds --split-max-chars.",
    )
    pack.add_argument(
        "--split-allow-cut-files",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Explicitly allow cutting oversized files into multiple part files.",
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

    # unpack
    unpack = sub.add_parser(
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

    # patch
    patch = sub.add_parser(
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

    # apply
    apply = sub.add_parser("apply", help="Apply a diff-only patch Markdown to a repo.")
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
    # validate-pack
    vpack = sub.add_parser(
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
        "--encoding-errors",
        choices=["replace", "strict"],
        default=None,
        help="UTF-8 decode policy when reading pack and root files",
    )

    # doctor
    doctor = sub.add_parser(
        "doctor", help="Run repository diagnostics and capability checks."
    )
    doctor.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Repository root to inspect (default: .)",
    )

    return p


@dataclass(frozen=True)
class PackOptions:
    include: list[str] | None
    include_source: str
    exclude: list[str] | None
    keep_docstrings: bool
    include_manifest: bool
    respect_gitignore: bool
    security_check: bool
    security_content_sniff: bool
    security_redaction: bool
    safety_report: bool
    security_path_patterns: list[str]
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


@dataclass(frozen=True)
class PackRun:
    root: Path
    label: str
    slug: str
    markdown: str
    options: PackOptions
    default_output: Path
    file_count: int
    skipped_for_safety_count: int
    redacted_for_safety_count: int
    safety_findings: list[SafetyFinding]

    # Token diagnostics (optional)
    effective_layout: str
    output_tokens: int
    total_file_tokens: int
    file_tokens: dict[str, int]
    file_bytes: dict[str, int]
    token_backend: str
    manifest: dict[str, object]
    manifest_sha256: str


@dataclass(frozen=True)
class _MeasuredFile:
    path: Path
    rel: str
    text: str
    size_bytes: int
    is_binary: bool = False


def _resolve_encoding_errors(cfg: Config, cli_value: str | None) -> str:
    if cli_value is not None:
        value = str(cli_value).strip().lower()
    else:
        value = str(getattr(cfg, "encoding_errors", "replace")).strip().lower()
    return value if value in {"replace", "strict"} else "replace"


def _resolve_pack_options(cfg: Config, args: argparse.Namespace) -> PackOptions:
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
    include_manifest = cfg.manifest if args.manifest is None else bool(args.manifest)
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
    layout = (
        str(args.layout).strip().lower()
        if args.layout is not None
        else str(getattr(cfg, "layout", "auto")).strip().lower()
    )
    nav_mode = (
        str(args.nav_mode).strip().lower()
        if args.nav_mode is not None
        else str(getattr(cfg, "nav_mode", "auto")).strip().lower()
    )
    symbol_backend = (
        str(args.symbol_backend).strip().lower()
        if args.symbol_backend is not None
        else str(getattr(cfg, "symbol_backend", "auto")).strip().lower()
    )
    encoding_errors = _resolve_encoding_errors(cfg, args.encoding_errors)

    # Token diagnostics (CLI-only)
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
        include_manifest=include_manifest,
        respect_gitignore=respect_gitignore,
        security_check=security_check,
        security_content_sniff=security_content_sniff,
        security_redaction=security_redaction,
        safety_report=safety_report,
        security_path_patterns=security_path_patterns,
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


def _resolve_output_path(cfg: Config, args: argparse.Namespace, root: Path) -> Path:
    if args.output is not None:
        return Path(args.output)
    out_path = Path(cfg.output)
    if not out_path.is_absolute():
        out_path = root / out_path
    return out_path


def _resolve_output_dir_and_prefix(output_path: Path) -> tuple[Path, str]:
    if output_path.suffix:
        return output_path.parent.resolve(), output_path.stem or "context"
    return output_path.resolve(), "context"


def _default_repo_label(root: Path) -> str:
    cwd = Path.cwd().resolve()
    resolved = root.resolve()
    try:
        rel = resolved.relative_to(cwd).as_posix()
        return rel or resolved.name or resolved.as_posix()
    except ValueError:
        return root.name or resolved.name or resolved.as_posix()


def _unique_label(root: Path, used: set[str]) -> str:
    base = _default_repo_label(root)
    label = base
    idx = 2
    while label in used:
        label = f"{base}-{idx}"
        idx += 1
    used.add(label)
    return label


def _slugify(label: str) -> str:
    return slugify_repo_label(label)


def _unique_slug(label: str, used: set[str]) -> str:
    base = _slugify(label)
    slug = base
    idx = 2
    while slug in used:
        slug = f"{base}-{idx}"
        idx += 1
    used.add(slug)
    return slug


def _prefix_repo_header(text: str, label: str) -> str:
    header = f"# Repository: {label}\n\n"
    if text.startswith(header):
        return text
    return header + text


def _combine_pack_markdown(packs: list[PackRun]) -> str:
    out: list[str] = []
    for i, pack in enumerate(packs):
        if i:
            out.append("\n\n")
        out.append(_prefix_repo_header(pack.markdown.rstrip() + "\n", pack.label))
    return "".join(out).rstrip() + "\n"


def _rewrite_split_part_links(text: str, filename_map: dict[str, str]) -> str:
    if not filename_map:
        return text
    pattern = re.compile("|".join(re.escape(name) for name in filename_map))
    return pattern.sub(lambda m: filename_map[m.group(0)], text)


def _index_and_part_paths(base_path: Path, count: int) -> list[Path]:
    paths = [base_path.with_name(f"{base_path.stem}.index{base_path.suffix}")]
    paths.extend(
        base_path.with_name(f"{base_path.stem}.part{i}{base_path.suffix}")
        for i in range(1, count)
    )
    return paths


def _rename_split_parts(
    parts: Sequence[Part], base_path: Path
) -> list[tuple[Path, str]]:
    if len(parts) <= 1:
        return [(base_path, parts[0].content)]

    new_paths = _index_and_part_paths(base_path, len(parts))
    old_names = [Path(p.path).name for p in parts]
    new_names = [p.name for p in new_paths]
    filename_map = {old: new for old, new in zip(old_names, new_names, strict=True)}

    out: list[tuple[Path, str]] = []
    for old, new_path in zip(parts, new_paths, strict=True):
        content = old.content
        out.append((new_path, _rewrite_split_part_links(content, filename_map)))
    return out


def _split_parts_fit_limit(outputs: Sequence[tuple[Path, str]], max_chars: int) -> bool:
    if max_chars <= 0:
        return True
    for idx, (_, content) in enumerate(outputs):
        if idx == 0:
            continue
        if len(content) > max_chars:
            return False
    return True


def _extract_diff_blocks(md_text: str) -> str:
    """
    Extract only diff fences from markdown and concatenate to a unified diff string.
    """
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        opened = parse_fence_open(lines[i])
        if opened is not None and opened[1] == "diff":
            fence = opened[0]
            i += 1
            while i < len(lines) and not is_fence_close(lines[i], fence):
                out.append(lines[i])
                i += 1
        i += 1
    return "\n".join(out) + "\n"


def _extract_patch_metadata(md_text: str) -> dict[str, object] | None:
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        opened = parse_fence_open(lines[i])
        if opened is not None and opened[1] == FENCE_PATCH_META:
            fence = opened[0]
            i += 1
            body: list[str] = []
            while i < len(lines) and not is_fence_close(lines[i], fence):
                body.append(lines[i])
                i += 1
            try:
                parsed = json.loads("\n".join(body))
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        i += 1
    return None


def _read_text_with_policy(path: Path, *, encoding_errors: str) -> str:
    try:
        return path.read_text(encoding="utf-8", errors=encoding_errors)
    except UnicodeDecodeError as e:
        raise ValueError(
            f"Failed to decode UTF-8 for {path} (encoding_errors={encoding_errors})"
        ) from e


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _verify_patch_baseline(
    *,
    root: Path,
    diffs: Sequence[object],
    patch_meta: dict[str, object] | None,
    encoding_errors: str,
    policy: Literal["auto", "require", "ignore"] = "auto",
) -> None:
    if policy == "ignore":
        return

    if not patch_meta:
        if policy == "require":
            raise SystemExit(
                "apply: --check-baseline requires patch metadata "
                f"fence `{FENCE_PATCH_META}` with baseline hashes."
            )
        return

    baseline = patch_meta.get("baseline_files_sha256")
    if not isinstance(baseline, dict):
        if policy == "require":
            raise SystemExit(
                "apply: --check-baseline requires 'baseline_files_sha256' "
                "in patch metadata."
            )
        return

    mismatches: list[str] = []
    root_resolved = root.resolve()
    for fd in diffs:
        rel = getattr(fd, "path", "")
        op = getattr(fd, "op", "")
        if not isinstance(rel, str) or not rel:
            continue
        expected_sha = baseline.get(rel)
        path = root_resolved / rel

        if op == "add":
            if path.exists():
                mismatches.append(f"{rel} (expected absent before add)")
            continue

        if not isinstance(expected_sha, str) or not expected_sha:
            continue
        if not path.exists():
            mismatches.append(f"{rel} (missing; expected baseline file)")
            continue

        disk_text = normalize_newlines(
            _read_text_with_policy(path, encoding_errors=encoding_errors)
        )
        disk_sha = _sha256_text(disk_text)
        if disk_sha != expected_sha:
            mismatches.append(f"{rel} (baseline sha mismatch)")

    if mismatches:
        preview = ", ".join(mismatches[:5])
        suffix = "" if len(mismatches) <= 5 else ", ..."
        raise SystemExit(
            "apply: patch baseline does not match current repository state for "
            f"{len(mismatches)} file(s): {preview}{suffix}. "
            "Regenerate patch from current baseline or restore baseline files."
        )


def _pack_has_effective_dedupe(pack: object) -> bool:
    # True if any definition was remapped to a canonical id.
    # That means dedupe actually collapsed something.
    files = getattr(pack, "files", None)
    if files is None:
        return False
    for fp in files:
        for d in getattr(fp, "defs", []):
            if getattr(d, "id", None) != getattr(d, "local_id", None):
                return True
    return False


def _resolve_effective_nav_mode(
    nav_mode: str, split_max_chars: int
) -> Literal["compact", "full"]:
    mode = nav_mode.strip().lower()
    if mode == "auto":
        return "full" if split_max_chars > 0 else "compact"
    if mode == "compact":
        return "compact"
    if mode == "full":
        return "full"
    return "full"


def _print_pack_summary(
    *,
    out_path: Path,
    markdown: str,
    total_files: int,
    encoding: str,
) -> None:
    total_chars = len(markdown)
    total_tokens: str
    try:
        total_tokens = f"{TokenCounter(encoding).count(markdown):,}"
    except Exception:
        total_tokens = "n/a"

    print("", file=sys.stderr)
    print("Pack Summary:", file=sys.stderr)
    print("─────────────", file=sys.stderr)
    print(f"{'Total Files':>12}: {total_files:,} files", file=sys.stderr)
    print(f"{'Total Tokens':>12}: {total_tokens} tokens", file=sys.stderr)
    print(f"{'Total Chars':>12}: {total_chars:,} chars", file=sys.stderr)
    print(f"{'Output':>12}: {out_path.as_posix()}", file=sys.stderr)


def _emit_safety_warning(
    *,
    label: str,
    root: Path,
    findings: list[SafetyFinding],
) -> None:
    if not findings:
        return
    skipped = [f for f in findings if f.action == "skipped"]
    redacted = [f for f in findings if f.action == "redacted"]
    preview = ", ".join(
        f"{item.path.relative_to(root).as_posix()} ({item.reason})"
        for item in findings[:5]
    )
    suffix = "" if len(findings) <= 5 else ", ..."
    print(
        f"Warning: safety findings in {label}: "
        f"skipped={len(skipped)}, redacted={len(redacted)}; {preview}{suffix}",
        file=sys.stderr,
    )


def _resolve_worker_count(max_workers: int, item_count: int) -> int:
    if item_count <= 1:
        return 1
    if max_workers > 0:
        return max_workers
    cpu = os.cpu_count() or 1
    return max(2, min(32, cpu * 4, item_count))


def _is_likely_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True

    sample = data[:4096]
    if not sample:
        return False

    text_whitespace = {9, 10, 13}
    suspicious = 0
    for b in sample:
        if b in text_whitespace:
            continue
        if 32 <= b <= 126:
            continue
        if 128 <= b <= 255:
            # UTF-8 / extended bytes are allowed.
            continue
        suspicious += 1
    return suspicious / len(sample) > 0.30


def _read_measured_file(
    path: Path,
    root: Path,
    override_texts: dict[Path, str] | None,
    *,
    encoding_errors: str,
) -> _MeasuredFile:
    if override_texts is not None and path in override_texts:
        text = normalize_newlines(override_texts[path])
        data = text.encode("utf-8")
        return _MeasuredFile(
            path=path,
            rel=path.relative_to(root).as_posix(),
            text=text,
            size_bytes=len(data),
            is_binary=False,
        )

    data = path.read_bytes()
    is_binary = _is_likely_binary(data)
    text = ""
    if not is_binary:
        try:
            text = normalize_newlines(data.decode("utf-8", errors=encoding_errors))
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Failed to decode UTF-8 for {path.relative_to(root).as_posix()} "
                f"(encoding_errors={encoding_errors})"
            ) from e
    return _MeasuredFile(
        path=path,
        rel=path.relative_to(root).as_posix(),
        text=text,
        size_bytes=len(data),
        is_binary=is_binary,
    )


def _measure_files(
    *,
    files: list[Path],
    root: Path,
    max_workers: int,
    override_texts: dict[Path, str] | None = None,
    encoding_errors: str = "replace",
) -> list[_MeasuredFile]:
    worker_count = _resolve_worker_count(max_workers, len(files))
    if worker_count == 1:
        return [
            _read_measured_file(
                path, root, override_texts, encoding_errors=encoding_errors
            )
            for path in files
        ]
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        return list(
            pool.map(
                lambda p: _read_measured_file(
                    p,
                    root,
                    override_texts,
                    encoding_errors=encoding_errors,
                ),
                files,
            )
        )


def _count_tokens_parallel(
    *,
    files: list[_MeasuredFile],
    count_fn: Callable[[str], int],
    max_workers: int,
) -> dict[str, int]:
    worker_count = _resolve_worker_count(max_workers, len(files))
    if worker_count == 1:
        return {f.rel: int(count_fn(f.text)) for f in files}
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        pairs = list(pool.map(lambda f: (f.rel, int(count_fn(f.text))), files))
    return {k: v for k, v in pairs}


def _emit_budget_skip_warning(*, label: str, skipped: list[tuple[str, str]]) -> None:
    if not skipped:
        return
    preview = ", ".join(f"{rel} ({reason})" for rel, reason in skipped[:5])
    suffix = "" if len(skipped) <= 5 else ", ..."
    print(
        f"Warning: skipped {len(skipped)} file(s) due to per-file budgets in "
        f"{label}: {preview}{suffix}",
        file=sys.stderr,
    )


def _emit_binary_skip_warning(*, label: str, skipped: list[str]) -> None:
    if not skipped:
        return
    preview = ", ".join(skipped[:5])
    suffix = "" if len(skipped) <= 5 else ", ..."
    print(
        f"Warning: skipped {len(skipped)} likely-binary file(s) in "
        f"{label}: {preview}{suffix}",
        file=sys.stderr,
    )


def _manifest_json_output_path(
    *,
    manifest_json_arg: str | None,
    markdown_output: Path,
) -> Path | None:
    if manifest_json_arg is None:
        return None
    if manifest_json_arg.strip():
        return Path(manifest_json_arg)
    return markdown_output.with_name(f"{markdown_output.stem}.manifest.json")


def _validation_hint(message: str) -> str | None:
    if "expected exactly one codecrate-manifest block" in message:
        return (
            "ensure each repo section contains exactly one ```codecrate-manifest block"
        )
    if "Cross-repo anchor collision" in message:
        return (
            "make anchor ids unique across sections (or regenerate with codecrate pack)"
        )
    if "Machine header checksum mismatch" in message:
        return "manifest content changed; regenerate the pack to refresh checksum"
    if "Machine header" in message and "missing" in message:
        return "regenerate pack so machine header and manifest are emitted together"
    if "codecrate-machine-header block" in message:
        return "ensure exactly one machine header fence is present in the pack"
    if "Unsupported manifest format" in message:
        return "regenerate pack with a supported codecrate version"
    if "id_format_version" in message or "marker_format_version" in message:
        return "pack format metadata is incompatible; regenerate with current codecrate"
    if "Missing stubbed file block" in message:
        return "restore missing file block under ## Files or regenerate the pack"
    if "Manifest file missing from file blocks" in message:
        return (
            "ensure every manifest path has a matching ### `<path>` block in ## Files"
        )
    if "File block not present in manifest" in message:
        return "remove extra file blocks or regenerate manifest from source"
    if "Duplicate file block" in message:
        return "keep only one file block per path under ## Files"
    if "Missing canonical source" in message:
        return "restore the missing Function Library entry for the listed id"
    if "Orphan function-library entry" in message:
        return "remove unused Function Library entry or add matching manifest def"
    if "Missing FUNC marker" in message or "Unresolved marker mapping" in message:
        return "ensure stub contains a marker like ...  # ↪ FUNC:v1:<ID>"
    if "Repo-scope marker collision" in message:
        return "ensure each stub marker id maps to a single definition occurrence"
    if "sha mismatch" in message:
        return "pack content was edited after generation; regenerate from source files"
    if "failed to parse repository pack" in message:
        return "verify markdown fences/manifest JSON are intact"
    return None


def _split_validation_scope(message: str) -> tuple[str, str]:
    if message.startswith("repo '") and ": " in message:
        scope, rest = message.split(": ", 1)
        return scope, rest
    return "global", message


def _print_grouped_validation_report(report: object) -> None:
    warnings = list(getattr(report, "warnings", []))
    errors = list(getattr(report, "errors", []))

    if warnings:
        print("Warnings:")
        by_scope: dict[str, list[str]] = {}
        for msg in warnings:
            scope, detail = _split_validation_scope(msg)
            by_scope.setdefault(scope, []).append(detail)
        for scope, msgs in by_scope.items():
            print(f"- [{scope}]")
            for detail in msgs:
                print(f"  - {detail}")
                hint = _validation_hint(detail)
                if hint:
                    print(f"    hint: {hint}")

    if errors:
        print("Errors:")
        by_scope_err: dict[str, list[str]] = {}
        for msg in errors:
            scope, detail = _split_validation_scope(msg)
            by_scope_err.setdefault(scope, []).append(detail)
        for scope, msgs in by_scope_err.items():
            print(f"- [{scope}]")
            for detail in msgs:
                print(f"  - {detail}")
                hint = _validation_hint(detail)
                if hint:
                    print(f"    hint: {hint}")


def _validation_report_json(report: object) -> str:
    warnings = list(getattr(report, "warnings", []))
    errors = list(getattr(report, "errors", []))
    payload = {
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2, sort_keys=False)


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
    print()
    print("Explicit-file mode notes:")
    print("  --stdin/--stdin0 treat stdin paths as the candidate set.")
    print("  Include globs are bypassed; exclude + ignore rules still apply.")
    print("  Outside-root and missing files are skipped (see --print-skipped).")


_NO_MANIFEST_HELP = (
    "packed markdown is missing a Manifest section; re-run `codecrate pack` "
    "without `--no-manifest` (or use `--manifest`)."
)


def _is_no_manifest_error(error: Exception) -> bool:
    return MISSING_MANIFEST_ERROR in str(error)


def _raise_no_manifest_error(
    parser: argparse.ArgumentParser,
    *,
    command_name: str,
) -> None:
    parser.error(f"{command_name}: {_NO_MANIFEST_HELP}")


def _print_selected_files(*, label: str, root: Path, selected: list[Path]) -> None:
    print(
        f"Debug: selected files for {label} ({len(selected)}):",
        file=sys.stderr,
    )
    for path in selected:
        print(f"  - {path.relative_to(root).as_posix()}", file=sys.stderr)


def _print_skipped_files(*, label: str, skipped: list[tuple[str, str]]) -> None:
    print(
        f"Debug: skipped files for {label} ({len(skipped)}):",
        file=sys.stderr,
    )
    for rel, reason in skipped:
        print(f"  - {rel} ({reason})", file=sys.stderr)


def _print_effective_rules(*, label: str, root: Path, options: PackOptions) -> None:
    include = options.include or []
    exclude = DEFAULT_EXCLUDES + (options.exclude or [])
    print(f"Debug: effective rules for {label}:", file=sys.stderr)
    print(f"  include-source: {options.include_source}", file=sys.stderr)
    print(
        f"  include ({len(include)}): {', '.join(include) if include else '<none>'}",
        file=sys.stderr,
    )
    print(
        f"  exclude ({len(exclude)}): {', '.join(exclude) if exclude else '<none>'}",
        file=sys.stderr,
    )
    print(
        "  ignore-files: "
        f".gitignore={'yes' if options.respect_gitignore else 'no'}, "
        f".codecrateignore={'yes' if (root / '.codecrateignore').exists() else 'no'}",
        file=sys.stderr,
    )
    print(
        "  safety: "
        f"check={'on' if options.security_check else 'off'}, "
        f"content_sniff={'on' if options.security_content_sniff else 'off'}, "
        f"redaction={'on' if options.security_redaction else 'off'}, "
        f"report={'on' if options.safety_report else 'off'}, "
        f"path_rules={len(options.security_path_patterns)}, "
        f"content_rules={len(options.security_content_patterns)}",
        file=sys.stderr,
    )


def _doctor_find_selected_config(root: Path) -> Path | None:
    for name in CONFIG_FILENAMES:
        p = root / name
        if p.exists():
            return p
    pyproject = root / PYPROJECT_FILENAME
    if pyproject.exists():
        return pyproject
    return None


def _doctor_config_state(path: Path, *, pyproject: bool) -> str:
    if not path.exists():
        return "missing"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"present (parse error: {type(e).__name__})"

    if not isinstance(data, dict):
        return "present (invalid TOML root)"

    section_found = False
    if pyproject:
        tool = data.get("tool")
        section_found = isinstance(tool, dict) and isinstance(
            tool.get("codecrate"), dict
        )
    else:
        cc = data.get("codecrate")
        if isinstance(cc, dict):
            section_found = True
        else:
            tool = data.get("tool")
            section_found = isinstance(tool, dict) and isinstance(
                tool.get("codecrate"), dict
            )

    return "present (section found)" if section_found else "present (section missing)"


def _doctor_tree_sitter_status() -> str:
    try:
        tsl = importlib.import_module("tree_sitter_languages")
    except ModuleNotFoundError:
        return "missing"
    except Exception as e:  # pragma: no cover
        return f"error ({type(e).__name__})"

    get_parser = getattr(tsl, "get_parser", None)
    if not callable(get_parser):
        return "installed (get_parser missing)"

    try:
        get_parser("javascript")
    except Exception as e:
        return f"installed (unusable: {type(e).__name__})"
    return "available"


def _run_doctor(root: Path) -> None:
    root = root.resolve()
    selected = _doctor_find_selected_config(root)

    print("Codecrate Doctor")
    print(f"Root: {root.as_posix()}")
    print()

    print("Config discovery:")
    print(
        "- precedence: .codecrate.toml > codecrate.toml > "
        "pyproject.toml[tool.codecrate]"
    )
    for name in CONFIG_FILENAMES:
        p = root / name
        print(f"- {name}: {_doctor_config_state(p, pyproject=False)}")
    pyproject = root / PYPROJECT_FILENAME
    print(f"- {PYPROJECT_FILENAME}: {_doctor_config_state(pyproject, pyproject=True)}")
    if selected is None:
        print("- selected: none (defaults only)")
    else:
        print(f"- selected: {selected.relative_to(root).as_posix()}")

    print()
    print("Ignore files:")
    print(f"- .gitignore: {'yes' if (root / '.gitignore').exists() else 'no'}")
    print(
        f"- .codecrateignore: {'yes' if (root / '.codecrateignore').exists() else 'no'}"
    )

    print()
    print("Token backend:")
    token_counter = TokenCounter("o200k_base")
    print(f"- backend: {token_counter.backend}")
    try:
        token_counter.count("def _doctor_probe():\n    return 1\n")
        print("- encoding o200k_base: ok")
    except Exception as e:
        print(f"- encoding o200k_base: error ({type(e).__name__})")

    print()
    print("Optional parsing backends:")
    print(f"- tree-sitter: {_doctor_tree_sitter_status()}")


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not raw_argv:
        _print_top_level_help(parser)
        return

    args = parser.parse_args(raw_argv)

    if args.cmd == "pack":
        # argparse with nargs="?" can consume ROOT as the option value when users run
        # `pack --token-count-tree ROOT`. Recover ROOT so packing still proceeds.
        if not args.repo and args.root is None and args.token_count_tree is not None:
            raw_tree = str(args.token_count_tree).strip()
            if raw_tree and raw_tree != "-1":
                try:
                    int(raw_tree)
                except ValueError:
                    candidate = Path(raw_tree)
                    if candidate.exists():
                        args.root = candidate
                        args.token_count_tree = "-1"

        if args.repo:
            if args.root is not None:
                parser.error(
                    "pack: specify either ROOT or --repo (repeatable), not both"
                )
            roots = [r.resolve() for r in args.repo]
        else:
            if args.root is None:
                parser.error("pack: ROOT is required when --repo is not used")
            roots = [args.root.resolve()]
        stdin_files: list[Path] | None = None
        if args.stdin or args.stdin0:
            if args.repo:
                parser.error(
                    "pack: --stdin/--stdin0 requires a single ROOT (do not use --repo)"
                )
            if args.stdin0:
                raw_chunks = sys.stdin.buffer.read().split(b"\0")
                raw_paths = [
                    chunk.decode("utf-8", errors="replace")
                    for chunk in raw_chunks
                    if chunk
                ]
                if not raw_paths:
                    parser.error(
                        "pack: --stdin0 was set but no file paths were provided "
                        "on stdin"
                    )
            else:
                raw_paths = [ln.strip() for ln in sys.stdin.read().splitlines()]
                raw_paths = [ln for ln in raw_paths if ln and not ln.startswith("#")]
                if not raw_paths:
                    parser.error(
                        "pack: --stdin was set but no file paths were provided on stdin"
                    )
            stdin_files = [Path(raw) for raw in raw_paths]

        used_labels: set[str] = set()
        used_slugs: set[str] = set()
        pack_runs: list[PackRun] = []

        for root in roots:
            cfg = load_config(root)
            options = _resolve_pack_options(cfg, args)
            label = _unique_label(root, used_labels)
            slug = _unique_slug(label, used_slugs)

            if args.print_rules:
                _print_effective_rules(label=label, root=root, options=options)

            disc = discover_files(
                root=root,
                include=options.include,
                exclude=options.exclude,
                respect_gitignore=options.respect_gitignore,
                explicit_files=stdin_files,
            )
            safe_files = disc.files
            safety_findings: list[SafetyFinding] = []
            skipped: list[SafetyFinding] = []
            redacted_files: dict[Path, str] = {}
            if options.security_check:
                try:
                    ruleset = build_ruleset(
                        path_patterns=options.security_path_patterns,
                        content_patterns=options.security_content_patterns,
                    )
                except ValueError as e:
                    parser.error(f"pack: invalid security rule pattern: {e}")

                safety_result = apply_safety_filters(
                    disc.root,
                    disc.files,
                    ruleset=ruleset,
                    content_sniff=options.security_content_sniff,
                    redaction=options.security_redaction,
                )
                safe_files = safety_result.safe_files
                skipped = safety_result.skipped
                redacted_files = safety_result.redacted_files
                safety_findings = safety_result.findings

            needs_token_counts = bool(
                options.token_report
                or options.max_file_tokens > 0
                or options.max_total_tokens > 0
            )
            token_backend = ""
            count_tokens: Callable[[str], int] = approx_token_count
            if needs_token_counts:
                try:
                    counter = TokenCounter(options.token_count_encoding)
                    token_backend = getattr(counter, "backend", "")
                    counter.count("")
                    count_tokens = counter.count
                except Exception as e:
                    token_backend = "approx"
                    count_tokens = approx_token_count
                    print(
                        f"Warning: token counting disabled ({e}); "
                        "falling back to approximate counts.",
                        file=sys.stderr,
                    )

            try:
                measured_files = _measure_files(
                    files=safe_files,
                    root=disc.root,
                    max_workers=options.max_workers,
                    override_texts=redacted_files,
                    encoding_errors=options.encoding_errors,
                )
            except ValueError as e:
                parser.error(f"pack: {e}")
            binary_measured = [m for m in measured_files if m.is_binary]
            if binary_measured:
                binary_skipped = [
                    SafetyFinding(path=m.path, reason="binary", action="skipped")
                    for m in binary_measured
                ]
                skipped.extend(binary_skipped)
                safety_findings.extend(binary_skipped)
                _emit_binary_skip_warning(
                    label=label,
                    skipped=[m.rel for m in binary_measured],
                )
            measured_files = [m for m in measured_files if not m.is_binary]

            _emit_safety_warning(label=label, root=disc.root, findings=safety_findings)

            raw_token_counts: dict[str, int] = {}
            if options.max_file_tokens > 0 or options.max_total_tokens > 0:
                raw_token_counts = _count_tokens_parallel(
                    files=measured_files,
                    count_fn=count_tokens,
                    max_workers=options.max_workers,
                )

            kept_measured: list[_MeasuredFile] = []
            skipped_for_budget: list[tuple[str, str]] = []
            for measured in measured_files:
                if (
                    options.max_file_bytes > 0
                    and measured.size_bytes > options.max_file_bytes
                ):
                    skipped_for_budget.append(
                        (
                            measured.rel,
                            f"bytes>{options.max_file_bytes}",
                        )
                    )
                    continue
                if options.max_file_tokens > 0:
                    t = raw_token_counts.get(measured.rel, 0)
                    if t > options.max_file_tokens:
                        skipped_for_budget.append(
                            (
                                measured.rel,
                                f"tokens>{options.max_file_tokens}",
                            )
                        )
                        continue
                kept_measured.append(measured)

            _emit_budget_skip_warning(label=label, skipped=skipped_for_budget)

            total_bytes = sum(m.size_bytes for m in kept_measured)
            if options.max_total_bytes > 0 and total_bytes > options.max_total_bytes:
                raise SystemExit(
                    f"pack: total bytes {total_bytes} exceed max_total_bytes "
                    f"{options.max_total_bytes} for {label}"
                )

            if options.max_total_tokens > 0:
                total_tokens_raw = sum(
                    raw_token_counts.get(m.rel, 0) for m in kept_measured
                )
                if total_tokens_raw > options.max_total_tokens:
                    raise SystemExit(
                        f"pack: total tokens {total_tokens_raw} exceed "
                        f"max_total_tokens {options.max_total_tokens} for {label}"
                    )

            files_for_pack = [m.path for m in kept_measured]
            file_texts = {m.path: m.text for m in kept_measured}
            file_bytes = {m.rel: m.size_bytes for m in kept_measured}

            if args.print_files:
                _print_selected_files(
                    label=label, root=disc.root, selected=files_for_pack
                )

            if args.print_skipped:
                skipped_details = [(item.path, item.reason) for item in disc.skipped]
                skipped_details.extend(
                    (f.path.relative_to(disc.root).as_posix(), f.reason)
                    for f in skipped
                    if f.action == "skipped"
                )
                skipped_details.extend(skipped_for_budget)
                skipped_details = sorted(set(skipped_details))
                _print_skipped_files(label=label, skipped=skipped_details)

            pack, canonical = pack_repo(
                disc.root,
                files_for_pack,
                keep_docstrings=options.keep_docstrings,
                dedupe=options.dedupe,
                symbol_backend=options.symbol_backend,
                file_texts=file_texts,
                max_workers=options.max_workers,
            )
            use_stubs = options.layout == "stubs" or (
                options.layout == "auto" and _pack_has_effective_dedupe(pack)
            )
            effective_layout = "stubs" if use_stubs else "full"
            manifest_obj = to_manifest(pack, minimal=not use_stubs)
            manifest_checksum = manifest_sha256(manifest_obj)
            binary_count = sum(1 for f in skipped if f.reason == "binary")
            skipped_for_safety_count = sum(
                1
                for f in skipped
                if not (f.reason == "binary" and f.action == "skipped")
            )
            redacted_count = sum(1 for f in safety_findings if f.action == "redacted")
            safety_entries = [
                {
                    "path": f.path.relative_to(disc.root).as_posix(),
                    "reason": f.reason,
                    "action": f.action,
                }
                for f in sorted(
                    safety_findings,
                    key=lambda item: (
                        item.path.relative_to(disc.root).as_posix(),
                        item.action,
                        item.reason,
                    ),
                )
            ]
            md = render_markdown(
                pack,
                canonical,
                layout=options.layout,
                nav_mode=_resolve_effective_nav_mode(
                    options.nav_mode,
                    options.split_max_chars,
                ),
                skipped_for_safety_count=skipped_for_safety_count,
                skipped_for_binary_count=binary_count,
                redacted_for_safety_count=redacted_count,
                include_safety_report=options.safety_report,
                safety_report_entries=safety_entries,
                include_manifest=options.include_manifest,
                manifest_data=manifest_obj,
                repo_label=label,
                repo_slug=slug,
            )

            file_tokens: dict[str, int] = {}
            output_tokens = 0
            total_file_tokens = 0

            if options.token_report:
                output_tokens = count_tokens(md)
                diag_files = [
                    _MeasuredFile(
                        path=fp.path,
                        rel=fp.path.relative_to(pack.root).as_posix(),
                        text=(
                            fp.original_text
                            if effective_layout == "full"
                            else fp.stubbed_text
                        ),
                        size_bytes=file_bytes.get(
                            fp.path.relative_to(pack.root).as_posix(),
                            len(fp.original_text.encode("utf-8")),
                        ),
                    )
                    for fp in pack.files
                ]
                file_tokens = _count_tokens_parallel(
                    files=diag_files,
                    count_fn=count_tokens,
                    max_workers=options.max_workers,
                )
                total_file_tokens = sum(file_tokens.values())

            default_output = _resolve_output_path(cfg, args, root)

            pack_runs.append(
                PackRun(
                    root=root,
                    label=label,
                    slug=slug,
                    markdown=md,
                    options=options,
                    default_output=default_output,
                    file_count=len(files_for_pack),
                    skipped_for_safety_count=skipped_for_safety_count,
                    redacted_for_safety_count=redacted_count,
                    safety_findings=safety_findings,
                    effective_layout=effective_layout,
                    output_tokens=output_tokens,
                    total_file_tokens=total_file_tokens,
                    file_tokens=file_tokens,
                    file_bytes=file_bytes,
                    token_backend=token_backend,
                    manifest=manifest_obj,
                    manifest_sha256=manifest_checksum,
                )
            )

        out_path = (
            args.output if args.output is not None else pack_runs[0].default_output
        )
        if len(pack_runs) == 1:
            md = pack_runs[0].markdown
        else:
            md = _combine_pack_markdown(pack_runs)

        wrote_split_outputs = False
        split_files_written: list[Path] = []
        if len(pack_runs) == 1:
            split_max_chars = pack_runs[0].options.split_max_chars
            parts = split_by_max_chars(md, out_path, split_max_chars)
            if len(parts) == 1 and parts[0].path == out_path:
                out_path.write_text(md, encoding="utf-8")
            else:
                renamed = _rename_split_parts(parts, out_path)
                if _split_parts_fit_limit(renamed, split_max_chars):
                    for part_path, content in renamed:
                        part_path.write_text(content, encoding="utf-8")
                        split_files_written.append(part_path)
                    wrote_split_outputs = True
                else:
                    out_path.write_text(md, encoding="utf-8")
        else:
            all_repo_split = True
            split_candidates: list[tuple[PackRun, list[tuple[Path, str]]]] = []
            for run_pack in pack_runs:
                split_max_chars = run_pack.options.split_max_chars
                if split_max_chars <= 0:
                    all_repo_split = False
                    break
                repo_base = out_path.with_name(
                    f"{out_path.stem}.{run_pack.slug}{out_path.suffix}"
                )
                parts = split_by_max_chars(
                    run_pack.markdown, repo_base, run_pack.options.split_max_chars
                )
                if len(parts) == 1 and parts[0].path == repo_base:
                    all_repo_split = False
                    break
                renamed = _rename_split_parts(parts, repo_base)
                if not _split_parts_fit_limit(renamed, split_max_chars):
                    all_repo_split = False
                    break
                split_candidates.append((run_pack, renamed))

            if all_repo_split:
                wrote_split_outputs = True
                for run_pack, renamed in split_candidates:
                    for part_path, content in renamed:
                        content_with_header = _prefix_repo_header(
                            content, run_pack.label
                        )
                        part_path.write_text(content_with_header, encoding="utf-8")
                        split_files_written.append(part_path)
            else:
                out_path.write_text(md, encoding="utf-8")

        manifest_json_path = _manifest_json_output_path(
            manifest_json_arg=args.manifest_json,
            markdown_output=out_path,
        )
        if manifest_json_path is not None:
            payload: dict[str, object] = {
                "format": MANIFEST_JSON_FORMAT_VERSION,
                "repositories": [
                    {
                        "label": run.label,
                        "slug": run.slug,
                        "manifest_sha256": run.manifest_sha256,
                        "manifest": run.manifest,
                    }
                    for run in pack_runs
                ],
            }
            manifest_json_path.write_text(
                json.dumps(payload, indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )

        for run in pack_runs:
            if not run.options.token_report:
                continue
            backend = run.token_backend or "approx"
            enc = run.options.token_count_encoding
            print("", file=sys.stderr)
            print(f"Token counts for {run.label}:", file=sys.stderr)
            print(f"- Backend: {backend} (encoding={enc})", file=sys.stderr)
            print(f"- Output markdown: {run.output_tokens} tokens", file=sys.stderr)
            print(
                f"- Effective file contents ({run.effective_layout}): "
                f"{run.total_file_tokens} tokens across {len(run.file_tokens)} file(s)",
                file=sys.stderr,
            )
            if run.options.top_files_len:
                top_block = (
                    format_top_files(run.file_tokens, run.options.top_files_len)
                    if run.file_tokens
                    else format_top_files_by_size(
                        run.file_bytes, run.options.top_files_len
                    )
                )
                if top_block:
                    print(top_block, file=sys.stderr)
            if run.options.token_count_tree and run.file_tokens:
                print(
                    format_token_count_tree(
                        run.file_tokens,
                        threshold=run.options.token_count_tree_threshold,
                    ),
                    file=sys.stderr,
                )

        summary_run = next((run for run in pack_runs if run.options.file_summary), None)
        if summary_run is not None and not wrote_split_outputs:
            try:
                rel_out_path = out_path.relative_to(Path.cwd())
            except ValueError:
                rel_out_path = out_path
            summary_encoding = summary_run.options.token_count_encoding
            _print_pack_summary(
                out_path=rel_out_path,
                markdown=md,
                total_files=sum(run.file_count for run in pack_runs),
                encoding=summary_encoding,
            )
        else:
            if wrote_split_outputs:
                if len(pack_runs) == 1:
                    index_path = out_path.with_name(
                        f"{out_path.stem}.index{out_path.suffix}"
                    )
                    part_count = max(0, len(split_files_written) - 1)
                    print(f"Wrote {index_path} and {part_count} split part file(s).")
                else:
                    print(
                        f"Wrote split outputs for {len(pack_runs)} repos "
                        f"({len(split_files_written)} file(s))."
                    )
            else:
                if len(pack_runs) == 1:
                    print(f"Wrote {out_path}.")
                else:
                    print(f"Wrote {out_path} for {len(pack_runs)} repos.")
            if manifest_json_path is not None:
                print(f"Wrote {manifest_json_path}.")

    elif args.cmd == "unpack":
        unpack_encoding_errors = args.encoding_errors or "replace"
        try:
            md_text = _read_text_with_policy(
                args.markdown,
                encoding_errors=unpack_encoding_errors,
            )
        except ValueError as e:
            parser.error(f"unpack: {e}")
        try:
            unpack_to_dir(md_text, args.out_dir, strict=bool(args.strict))
        except ValueError as e:
            if _is_no_manifest_error(e):
                _raise_no_manifest_error(parser, command_name="unpack")
            raise
        print(f"Unpacked into {args.out_dir}")

    elif args.cmd == "patch":
        cfg = load_config(args.root)
        patch_encoding_errors = _resolve_encoding_errors(cfg, args.encoding_errors)
        try:
            old_md = _read_text_with_policy(
                args.old_markdown,
                encoding_errors=patch_encoding_errors,
            )
        except ValueError as e:
            parser.error(f"patch: {e}")
        old_sections = split_repository_sections(old_md)
        selected_label: str | None = None
        if old_sections:
            try:
                section = select_repository_section(
                    old_sections,
                    args.repo,
                    command_name="patch",
                )
            except ValueError as e:
                parser.error(str(e))
            old_md = section.content
            selected_label = section.label
        elif args.repo is not None:
            parser.error(
                "patch: --repo was provided, but old_markdown has no "
                "# Repository sections"
            )

        try:
            patch_md = generate_patch_markdown(
                old_md,
                args.root,
                include=cfg.include,
                exclude=cfg.exclude,
                respect_gitignore=cfg.respect_gitignore,
                encoding_errors=patch_encoding_errors,
            )
        except ValueError as e:
            if _is_no_manifest_error(e):
                _raise_no_manifest_error(parser, command_name="patch")
            raise
        if old_sections and selected_label is not None:
            patch_md = _prefix_repo_header(patch_md.rstrip() + "\n", selected_label)
        args.output.write_text(patch_md, encoding="utf-8")
        print(f"Wrote {args.output}")

    elif args.cmd == "validate-pack":
        cfg_root = args.root if args.root is not None else Path.cwd()
        cfg = load_config(cfg_root)
        validate_encoding_errors = _resolve_encoding_errors(cfg, args.encoding_errors)
        try:
            md_text = _read_text_with_policy(
                args.markdown,
                encoding_errors=validate_encoding_errors,
            )
        except ValueError as e:
            parser.error(f"validate-pack: {e}")
        try:
            report = validate_pack_markdown(
                md_text,
                root=args.root,
                strict=bool(args.strict),
                encoding_errors=validate_encoding_errors,
            )
        except ValueError as e:
            if _is_no_manifest_error(e):
                _raise_no_manifest_error(parser, command_name="validate-pack")
            raise
        if args.json:
            print(_validation_report_json(report))
        else:
            _print_grouped_validation_report(report)
        if report.errors:
            raise SystemExit(1)
        if not args.json:
            print("OK: pack is internally consistent.")

    elif args.cmd == "doctor":
        if not args.root.exists() or not args.root.is_dir():
            parser.error(f"doctor: root is not a directory: {args.root}")
        _run_doctor(args.root)

    elif args.cmd == "apply":
        cfg = load_config(args.root)
        apply_encoding_errors = _resolve_encoding_errors(cfg, args.encoding_errors)
        try:
            md_text = _read_text_with_policy(
                args.patch_markdown,
                encoding_errors=apply_encoding_errors,
            )
        except ValueError as e:
            parser.error(f"apply: {e}")
        patch_sections = split_repository_sections(md_text)
        if patch_sections:
            try:
                section = select_repository_section(
                    patch_sections,
                    args.repo,
                    command_name="apply",
                )
            except ValueError as e:
                parser.error(str(e))
            md_text = section.content
        elif args.repo is not None:
            parser.error(
                "apply: --repo was provided, but patch_markdown has no "
                "# Repository sections"
            )

        diff_text = _extract_diff_blocks(md_text)
        diffs = parse_unified_diff(diff_text)
        patch_meta = _extract_patch_metadata(md_text)
        baseline_policy: Literal["auto", "require", "ignore"] = "auto"
        if args.check_baseline:
            baseline_policy = "require"
        elif args.ignore_baseline:
            baseline_policy = "ignore"
        try:
            _verify_patch_baseline(
                root=args.root,
                diffs=diffs,
                patch_meta=patch_meta,
                encoding_errors=apply_encoding_errors,
                policy=baseline_policy,
            )
        except ValueError as e:
            parser.error(f"apply: {e}")
        try:
            changed = apply_file_diffs(
                diffs,
                args.root,
                dry_run=bool(args.dry_run),
                encoding_errors=apply_encoding_errors,
            )
        except ValueError as e:
            parser.error(f"apply: {e}")
        if args.dry_run:
            print(f"Dry run OK: patch can be applied to {len(changed)} file(s).")
        else:
            print(f"Applied patch to {len(changed)} file(s).")


if __name__ == "__main__":
    main()
