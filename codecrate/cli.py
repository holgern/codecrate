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
from dataclasses import dataclass, fields
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
from .index_json import build_index_payload, write_index_json
from .manifest import manifest_sha256, to_manifest
from .markdown import render_markdown_result
from .options import PackOptions, resolve_encoding_errors, resolve_pack_options
from .output_model import PackRun
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
        "--profile",
        choices=["human", "agent", "hybrid"],
        default=None,
        help=(
            "Output defaults profile: human keeps current behavior, "
            "agent implies compact nav + index-json, hybrid implies index-json."
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
            "path; without a path writes <output>.index.json"
        ),
    )
    pack.add_argument(
        "--no-index-json",
        action="store_true",
        help="Disable index JSON output, including profile-implied defaults.",
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

    # config
    config = sub.add_parser("config", help="Inspect resolved configuration values.")
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

    return p

@dataclass(frozen=True)
class _MeasuredFile:
    path: Path
    rel: str
    text: str
    size_bytes: int
    is_binary: bool = False

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


def _rename_split_parts(parts: Sequence[Part], base_path: Path) -> list[Part]:
    if len(parts) <= 1:
        part = parts[0]
        return [
            Part(
                path=base_path,
                content=part.content,
                kind=part.kind,
                files=part.files,
                canonical_ids=part.canonical_ids,
                section_types=part.section_types,
            )
        ]

    new_paths = _index_and_part_paths(base_path, len(parts))
    old_names = [Path(p.path).name for p in parts]
    new_names = [p.name for p in new_paths]
    filename_map = {old: new for old, new in zip(old_names, new_names, strict=True)}

    out: list[Part] = []
    for old, new_path in zip(parts, new_paths, strict=True):
        content = old.content
        out.append(
            Part(
                path=new_path,
                content=_rewrite_split_part_links(content, filename_map),
                kind=old.kind,
                files=old.files,
                canonical_ids=old.canonical_ids,
                section_types=old.section_types,
            )
        )
    return out


def _oversized_split_parts(outputs: Sequence[Part], max_chars: int) -> list[Path]:
    if max_chars <= 0:
        return []
    oversized: list[Path] = []
    for idx, part in enumerate(outputs):
        if idx == 0:
            continue
        if len(part.content) > max_chars:
            oversized.append(part.path)
    return oversized


def _warn_oversized_split_outputs(
    *, label: str, paths: Sequence[Path], max_chars: int
) -> None:
    if not paths:
        return
    preview = ", ".join(path.name for path in paths[:3])
    suffix = "" if len(paths) <= 3 else ", ..."
    print(
        f"Warning: wrote {len(paths)} oversize split part(s) for {label} "
        f"that exceed split_max_chars {max_chars}: {preview}{suffix}",
        file=sys.stderr,
    )


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


def _index_json_output_path(
    *,
    index_json_arg: str | None,
    markdown_output: Path,
) -> Path | None:
    if index_json_arg is None:
        return None
    if index_json_arg.strip():
        return Path(index_json_arg)
    return markdown_output.with_name(f"{markdown_output.stem}.index.json")


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
    root_drift_paths = list(getattr(report, "root_drift_paths", []))
    payload = {
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "root_drift_count": len(root_drift_paths),
        "root_drift_paths": root_drift_paths,
        "redacted_count": int(getattr(report, "redacted_count", 0)),
        "safety_skip_count": int(getattr(report, "safety_skip_count", 0)),
        "errors": errors,
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def _validation_policy_errors(report: object, args: argparse.Namespace) -> list[str]:
    warnings = list(getattr(report, "warnings", []))
    root_drift_paths = list(getattr(report, "root_drift_paths", []))
    redacted_count = int(getattr(report, "redacted_count", 0))
    safety_skip_count = int(getattr(report, "safety_skip_count", 0))

    errors: list[str] = []
    if bool(getattr(args, "fail_on_warning", False)) and warnings:
        errors.append(
            "Policy failure: warnings present "
            f"({len(warnings)}); use without --fail-on-warning to allow warnings"
        )
    if bool(getattr(args, "fail_on_root_drift", False)) and root_drift_paths:
        errors.append(
            "Policy failure: root drift detected for "
            f"{len(root_drift_paths)} file(s): {', '.join(root_drift_paths[:5])}"
        )
    if bool(getattr(args, "fail_on_redaction", False)) and redacted_count > 0:
        errors.append(f"Policy failure: pack reports {redacted_count} redacted file(s)")
    if bool(getattr(args, "fail_on_safety_skip", False)) and safety_skip_count > 0:
        errors.append(
            f"Policy failure: pack reports {safety_skip_count} safety-skipped file(s)"
        )
    return errors


def _validation_report_json_with_policy(
    report: object, policy_errors: list[str]
) -> str:
    warnings = list(getattr(report, "warnings", []))
    errors = list(getattr(report, "errors", []))
    root_drift_paths = list(getattr(report, "root_drift_paths", []))
    payload = {
        "ok": not errors and not policy_errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "policy_error_count": len(policy_errors),
        "root_drift_count": len(root_drift_paths),
        "root_drift_paths": root_drift_paths,
        "redacted_count": int(getattr(report, "redacted_count", 0)),
        "safety_skip_count": int(getattr(report, "safety_skip_count", 0)),
        "errors": errors,
        "warnings": warnings,
        "policy_errors": policy_errors,
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
    print("  codecrate config show . --effective")
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
        f"path_rules(base={len(options.security_path_patterns)}, "
        f"add={len(options.security_path_patterns_add)}, "
        f"remove={len(options.security_path_patterns_remove)}), "
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


def _config_values(cfg: Config, *, effective: bool) -> dict[str, object]:
    values: dict[str, object] = {}
    for field in fields(cfg):
        values[field.name] = getattr(cfg, field.name)
    if effective:
        values["security_path_patterns"] = list(
            build_ruleset(
                path_patterns=cfg.security_path_patterns,
                path_patterns_add=getattr(cfg, "security_path_patterns_add", []),
                path_patterns_remove=getattr(cfg, "security_path_patterns_remove", []),
                content_patterns=[],
            ).path_patterns
        )
    return values


def _run_config_show(root: Path, *, effective: bool, as_json: bool) -> None:
    root = root.resolve()
    selected = _doctor_find_selected_config(root)
    mode = "effective"
    if not effective:
        # The command currently supports only effective configuration rendering.
        mode = "effective"

    values = _config_values(load_config(root), effective=True)
    selected_text = (
        "none (defaults only)"
        if selected is None
        else selected.relative_to(root).as_posix()
    )
    precedence = [
        ".codecrate.toml",
        "codecrate.toml",
        "pyproject.toml[tool.codecrate]",
    ]

    if as_json:
        payload = {
            "root": root.as_posix(),
            "mode": mode,
            "precedence": precedence,
            "selected": selected_text,
            "values": values,
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
        return

    print("Codecrate Config")
    print(f"Root: {root.as_posix()}")
    print(f"Mode: {mode}")
    print(
        "Precedence: .codecrate.toml > codecrate.toml > pyproject.toml[tool.codecrate]"
    )
    print(f"Selected: {selected_text}")
    print()
    print("Effective values:")
    for key, value in values.items():
        print(f"{key} = {json.dumps(value, ensure_ascii=True)}")


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
        from .cli_pack import run_pack_command

        run_pack_command(parser, args)
        return

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
            try:
                options = resolve_pack_options(cfg, args)
            except ValueError as e:
                parser.error(f"pack: {e}")
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
                        path_patterns_add=options.security_path_patterns_add,
                        path_patterns_remove=options.security_path_patterns_remove,
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
                encoding_errors=options.encoding_errors,
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
            effective_nav_mode = _resolve_effective_nav_mode(
                options.nav_mode,
                options.split_max_chars,
            )
            rendered = render_markdown_result(
                pack,
                canonical,
                layout=options.layout,
                nav_mode=effective_nav_mode,
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
            md = rendered.markdown

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
                    render_metadata=rendered.metadata,
                    pack_result=pack,
                    canonical_sources=canonical,
                    options=options,
                    default_output=default_output,
                    file_count=len(files_for_pack),
                    skipped_for_safety_count=skipped_for_safety_count,
                    redacted_for_safety_count=redacted_count,
                    safety_findings=safety_findings,
                    effective_layout=effective_layout,
                    effective_nav_mode=effective_nav_mode,
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
        repo_output_parts: dict[str, list[Part]] = {}
        if len(pack_runs) == 1:
            split_max_chars = pack_runs[0].options.split_max_chars
            try:
                parts = split_by_max_chars(
                    md,
                    out_path,
                    split_max_chars,
                    strict=pack_runs[0].options.split_strict,
                    allow_cut_files=pack_runs[0].options.split_allow_cut_files,
                )
            except ValueError as e:
                raise SystemExit(f"pack: {e}") from e
            if len(parts) == 1 and parts[0].path == out_path:
                out_path.write_text(md, encoding="utf-8")
                repo_output_parts[pack_runs[0].slug] = [Part(path=out_path, content=md)]
            else:
                renamed = _rename_split_parts(parts, out_path)
                oversized_parts = _oversized_split_parts(renamed, split_max_chars)
                if pack_runs[0].options.split_strict and oversized_parts:
                    raise SystemExit(
                        "pack: split_strict requires all non-index parts to fit "
                        f"within split_max_chars {split_max_chars}; oversize: "
                        f"{', '.join(path.name for path in oversized_parts)}"
                    )
                for part in renamed:
                    part.path.write_text(part.content, encoding="utf-8")
                    split_files_written.append(part.path)
                wrote_split_outputs = True
                repo_output_parts[pack_runs[0].slug] = list(renamed)
                _warn_oversized_split_outputs(
                    label=pack_runs[0].label,
                    paths=oversized_parts,
                    max_chars=split_max_chars,
                )
        else:
            all_repo_split = True
            split_candidates: list[tuple[PackRun, list[Part], list[Path]]] = []
            for run_pack in pack_runs:
                split_max_chars = run_pack.options.split_max_chars
                if split_max_chars <= 0:
                    all_repo_split = False
                    break
                repo_base = out_path.with_name(
                    f"{out_path.stem}.{run_pack.slug}{out_path.suffix}"
                )
                try:
                    parts = split_by_max_chars(
                        run_pack.markdown,
                        repo_base,
                        run_pack.options.split_max_chars,
                        strict=run_pack.options.split_strict,
                        allow_cut_files=run_pack.options.split_allow_cut_files,
                    )
                except ValueError as e:
                    raise SystemExit(f"pack: {e}") from e
                if len(parts) == 1 and parts[0].path == repo_base:
                    all_repo_split = False
                    break
                renamed = _rename_split_parts(parts, repo_base)
                oversized_parts = _oversized_split_parts(renamed, split_max_chars)
                if run_pack.options.split_strict and oversized_parts:
                    raise SystemExit(
                        "pack: split_strict requires all non-index parts to fit "
                        f"within split_max_chars {split_max_chars} "
                        f"for {run_pack.label}; "
                        f"oversize: {', '.join(path.name for path in oversized_parts)}"
                    )
                split_candidates.append((run_pack, renamed, oversized_parts))

            if all_repo_split:
                wrote_split_outputs = True
                for run_pack, renamed, oversized_parts in split_candidates:
                    written_parts: list[Part] = []
                    for part in renamed:
                        content_with_header = _prefix_repo_header(
                            part.content, run_pack.label
                        )
                        final_part = Part(
                            path=part.path,
                            content=content_with_header,
                            kind=part.kind,
                            files=part.files,
                            canonical_ids=part.canonical_ids,
                            section_types=part.section_types,
                        )
                        final_part.path.write_text(final_part.content, encoding="utf-8")
                        split_files_written.append(final_part.path)
                        written_parts.append(final_part)
                    repo_output_parts[run_pack.slug] = written_parts
                    _warn_oversized_split_outputs(
                        label=run_pack.label,
                        paths=oversized_parts,
                        max_chars=run_pack.options.split_max_chars,
                    )
            else:
                out_path.write_text(md, encoding="utf-8")
                for run_pack in pack_runs:
                    repo_output_parts[run_pack.slug] = [Part(path=out_path, content=md)]

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

        index_json_path = None
        if any(run.options.index_json_enabled for run in pack_runs):
            index_json_arg = args.index_json if args.index_json is not None else ""
            index_json_path = _index_json_output_path(
                index_json_arg=index_json_arg,
                markdown_output=out_path,
            )
        if index_json_path is not None:
            payload = build_index_payload(
                codecrate_version=_codecrate_version(),
                index_output_path=index_json_path,
                pack_runs=pack_runs,
                repo_output_parts=repo_output_parts,
                is_split=wrote_split_outputs,
            )
            write_index_json(index_json_path, payload)

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
            if index_json_path is not None:
                print(f"Wrote {index_json_path}.")

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
        from .cli_patch import run_patch_command

        run_patch_command(parser, args)
        return
        cfg = load_config(args.root)
        patch_encoding_errors = resolve_encoding_errors(cfg, args.encoding_errors)
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
        from .cli_validate import run_validate_pack_command

        run_validate_pack_command(parser, args)
        return
        if args.fail_on_root_drift and args.root is None:
            parser.error("validate-pack: --fail-on-root-drift requires --root")
        cfg_root = args.root if args.root is not None else Path.cwd()
        cfg = load_config(cfg_root)
        validate_encoding_errors = resolve_encoding_errors(cfg, args.encoding_errors)
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
        policy_errors = _validation_policy_errors(report, args)
        if args.json:
            print(_validation_report_json_with_policy(report, policy_errors))
        else:
            _print_grouped_validation_report(report)
            if policy_errors:
                print("Policy Errors:")
                for msg in policy_errors:
                    print(f"- {msg}")
        if report.errors or policy_errors:
            raise SystemExit(1)
        if not args.json:
            print("OK: pack is internally consistent.")

    elif args.cmd == "doctor":
        from .cli_doctor import run_doctor_command

        run_doctor_command(parser, args)
        return
        if not args.root.exists() or not args.root.is_dir():
            parser.error(f"doctor: root is not a directory: {args.root}")
        _run_doctor(args.root)

    elif args.cmd == "config":
        if args.config_cmd == "show":
            from .cli_doctor import run_config_show_command

            run_config_show_command(parser, args)
            return
            if not args.root.exists() or not args.root.is_dir():
                parser.error(f"config show: root is not a directory: {args.root}")
            _run_config_show(
                args.root,
                effective=bool(args.effective),
                as_json=bool(args.json),
            )

    elif args.cmd == "apply":
        from .cli_patch import run_apply_command

        run_apply_command(parser, args)
        return
        cfg = load_config(args.root)
        apply_encoding_errors = resolve_encoding_errors(cfg, args.encoding_errors)
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
