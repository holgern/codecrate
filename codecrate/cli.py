from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Config, load_config
from .diffgen import generate_patch_markdown
from .discover import discover_files
from .markdown import render_markdown
from .packer import pack_repo
from .token_budget import split_by_max_chars
from .tokens import TokenCounter, format_token_count_tree, format_top_files
from .udiff import apply_file_diffs, parse_unified_diff
from .unpacker import unpack_to_dir
from .validate import validate_pack_markdown


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codecrate",
        description="Pack/unpack/patch/apply for repositories  (Python + text files).",
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
    pack.add_argument(
        "--stdin",
        action="store_true",
        help="Read file paths from stdin (one per line) instead of scanning the root",
    )
    pack.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output markdown path (default: config 'output' or context.md)",
    )
    pack.add_argument(
        "--dedupe", action="store_true", help="Deduplicate identical function bodies"
    )
    pack.add_argument(
        "--layout",
        choices=["auto", "stubs", "full"],
        default=None,
        help="Output layout: auto|stubs|full (default: auto via config)",
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
        "--manifest",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include Manifest section (default: true via config)",
    )
    pack.add_argument(
        "--include", action="append", default=None, help="Include glob (repeatable)"
    )
    pack.add_argument(
        "--exclude", action="append", default=None, help="Exclude glob (repeatable)"
    )
    pack.add_argument(
        "--split-max-chars",
        type=int,
        default=None,
        help="Split output into .partN.md files",
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

    # unpack
    unpack = sub.add_parser(
        "unpack", help="Reconstruct files from a packed context Markdown."
    )
    unpack.add_argument("markdown", type=Path, help="Packed Markdown file from `pack`")
    unpack.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        required=True,
        help="Output directory for reconstructed files",
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
        "-o",
        "--output",
        type=Path,
        default=Path("patch.md"),
        help="Output patch markdown",
    )

    # apply
    apply = sub.add_parser("apply", help="Apply a diff-only patch Markdown to a repo.")
    apply.add_argument(
        "patch_markdown", type=Path, help="Patch Markdown containing ```diff blocks"
    )
    apply.add_argument("root", type=Path, help="Repo root to apply patch to")
    # validate-pack
    vpack = sub.add_parser(
        "validate-pack",
        help="Validate a packed context Markdown (sha/markers/canonical consistency).",
    )
    vpack.add_argument("markdown", type=Path, help="Packed Markdown to validate")
    vpack.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Optional repo root to compare reconstructed files against",
    )

    return p


@dataclass(frozen=True)
class PackOptions:
    include: list[str] | None
    exclude: list[str] | None
    keep_docstrings: bool
    include_manifest: bool
    respect_gitignore: bool
    dedupe: bool
    split_max_chars: int
    layout: str

    # CLI-only diagnostics
    token_report: bool
    token_count_tree: bool
    token_count_tree_threshold: int
    top_files_len: int
    token_count_encoding: str
    file_summary: bool


@dataclass(frozen=True)
class PackRun:
    root: Path
    label: str
    slug: str
    markdown: str
    options: PackOptions
    default_output: Path
    file_count: int

    # Token diagnostics (optional)
    effective_layout: str
    output_tokens: int
    total_file_tokens: int
    file_tokens: dict[str, int]
    token_backend: str


def _resolve_pack_options(cfg: Config, args: argparse.Namespace) -> PackOptions:
    include = args.include if args.include is not None else cfg.include
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
    dedupe = bool(args.dedupe) or bool(cfg.dedupe)
    split_max_chars = (
        cfg.split_max_chars
        if args.split_max_chars is None
        else int(args.split_max_chars or 0)
    )
    layout = (
        str(args.layout).strip().lower()
        if args.layout is not None
        else str(getattr(cfg, "layout", "auto")).strip().lower()
    )

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

    return PackOptions(
        include=include,
        exclude=exclude,
        keep_docstrings=keep_docstrings,
        include_manifest=include_manifest,
        respect_gitignore=respect_gitignore,
        dedupe=dedupe,
        split_max_chars=split_max_chars,
        layout=layout,
        token_report=token_report,
        token_count_tree=token_count_tree,
        token_count_tree_threshold=token_count_tree_threshold,
        top_files_len=top_files_len,
        token_count_encoding=token_count_encoding,
        file_summary=file_summary,
    )


def _resolve_output_path(cfg: Config, args: argparse.Namespace, root: Path) -> Path:
    if args.output is not None:
        return args.output
    out_path = Path(getattr(cfg, "output", "context.md"))
    if not out_path.is_absolute():
        out_path = root / out_path
    return out_path


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
    safe: list[str] = []
    for ch in label:
        if ch.isalnum() or ch in {"-", "_"}:
            safe.append(ch)
        else:
            safe.append("-")
    slug = "".join(safe).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "repo"


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


def _extract_diff_blocks(md_text: str) -> str:
    """
    Extract only diff fences from markdown and concatenate to a unified diff string.
    """
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "```diff":
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                out.append(lines[i])
                i += 1
        i += 1
    return "\n".join(out) + "\n"


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


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    parser = build_parser()
    args = parser.parse_args(argv)

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
        if args.stdin:
            if args.repo:
                parser.error("pack: --stdin requires a single ROOT (do not use --repo)")
            raw_lines = [ln.strip() for ln in sys.stdin.read().splitlines()]
            raw_lines = [ln for ln in raw_lines if ln and not ln.startswith("#")]
            if not raw_lines:
                parser.error(
                    "pack: --stdin was set but no file paths were provided on stdin"
                )
            stdin_files = [Path(ln) for ln in raw_lines]

        used_labels: set[str] = set()
        used_slugs: set[str] = set()
        pack_runs: list[PackRun] = []

        for root in roots:
            cfg = load_config(root)
            options = _resolve_pack_options(cfg, args)
            label = _unique_label(root, used_labels)
            slug = _unique_slug(label, used_slugs)

            disc = discover_files(
                root=root,
                include=options.include,
                exclude=options.exclude,
                respect_gitignore=options.respect_gitignore,
                explicit_files=stdin_files,
            )
            pack, canonical = pack_repo(
                disc.root,
                disc.files,
                keep_docstrings=options.keep_docstrings,
                dedupe=options.dedupe,
            )
            md = render_markdown(
                pack,
                canonical,
                layout=options.layout,
                include_manifest=options.include_manifest,
            )
            effective_layout = options.layout
            if effective_layout == "auto":
                effective_layout = (
                    "stubs" if _pack_has_effective_dedupe(pack) else "full"
                )

            file_tokens: dict[str, int] = {}
            output_tokens = 0
            total_file_tokens = 0
            token_backend = ""

            if options.token_report:
                try:
                    counter = TokenCounter(options.token_count_encoding)
                    token_backend = getattr(counter, "backend", "")
                    output_tokens = counter.count(md)
                    for fp in pack.files:
                        rel = fp.path.relative_to(pack.root).as_posix()
                        txt = (
                            fp.original_text
                            if effective_layout == "full"
                            else fp.stubbed_text
                        )
                        n = counter.count(txt)
                        file_tokens[rel] = n
                        total_file_tokens += n
                except Exception as e:
                    print(f"Warning: token counting disabled ({e}).", file=sys.stderr)
                    file_tokens = {}
                    output_tokens = 0
                    total_file_tokens = 0
                    token_backend = ""

            default_output = _resolve_output_path(cfg, args, root)
            pack_runs.append(
                PackRun(
                    root=root,
                    label=label,
                    slug=slug,
                    markdown=md,
                    options=options,
                    default_output=default_output,
                    file_count=len(disc.files),
                    effective_layout=effective_layout,
                    output_tokens=output_tokens,
                    total_file_tokens=total_file_tokens,
                    file_tokens=file_tokens,
                    token_backend=token_backend,
                )
            )

        out_path = (
            args.output if args.output is not None else pack_runs[0].default_output
        )
        if len(pack_runs) == 1:
            md = pack_runs[0].markdown
        else:
            md = _combine_pack_markdown(pack_runs)

        # Always write the canonical, unsplit pack
        # for machine parsing (unpack/validate).
        out_path.write_text(md, encoding="utf-8")
        rel_out_path = out_path.relative_to(Path.cwd())

        extra_count = 0
        if len(pack_runs) == 1:
            split_max_chars = pack_runs[0].options.split_max_chars
            parts = split_by_max_chars(md, out_path, split_max_chars)
            extra = [p for p in parts if p.path != out_path]
            for part in extra:
                part.path.write_text(part.content, encoding="utf-8")
            extra_count += len(extra)
        else:
            for pack in pack_runs:
                if pack.options.split_max_chars <= 0:
                    continue
                repo_base = out_path.with_name(
                    f"{out_path.stem}.{pack.slug}{out_path.suffix}"
                )
                parts = split_by_max_chars(
                    pack.markdown, repo_base, pack.options.split_max_chars
                )
                extra = [p for p in parts if p.path != repo_base]
                for part in extra:
                    content = _prefix_repo_header(part.content, pack.label)
                    part.path.write_text(content, encoding="utf-8")
                extra_count += len(extra)

        # Token diagnostics (stderr)
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
            if run.options.top_files_len and run.file_tokens:
                print(
                    format_top_files(run.file_tokens, run.options.top_files_len),
                    file=sys.stderr,
                )
            if run.options.token_count_tree and run.file_tokens:
                print(
                    format_token_count_tree(
                        run.file_tokens,
                        threshold=run.options.token_count_tree_threshold,
                    ),
                    file=sys.stderr,
                )

        summary_run = next((run for run in pack_runs if run.options.file_summary), None)
        if summary_run is not None:
            summary_encoding = summary_run.options.token_count_encoding
            _print_pack_summary(
                out_path=rel_out_path,
                markdown=md,
                total_files=sum(run.file_count for run in pack_runs),
                encoding=summary_encoding,
            )
        else:
            if extra_count:
                if len(pack_runs) == 1:
                    print(f"Wrote {rel_out_path} and {extra_count} split part file(s).")
                else:
                    print(
                        f"Wrote {rel_out_path} and {extra_count} split part file(s) for "
                        f"{len(pack_runs)} repos."
                    )
            else:
                if len(pack_runs) == 1:
                    print(f"Wrote {rel_out_path}.")
                else:
                    print(f"Wrote {rel_out_path} for {len(pack_runs)} repos.")

           
    elif args.cmd == "unpack":
        md_text = args.markdown.read_text(encoding="utf-8", errors="replace")
        unpack_to_dir(md_text, args.out_dir)
        print(f"Unpacked into {args.out_dir}")

    elif args.cmd == "patch":
        old_md = args.old_markdown.read_text(encoding="utf-8", errors="replace")
        cfg = load_config(args.root)
        patch_md = generate_patch_markdown(
            old_md,
            args.root,
            include=cfg.include,
            exclude=cfg.exclude,
            respect_gitignore=cfg.respect_gitignore,
        )
        args.output.write_text(patch_md, encoding="utf-8")
        print(f"Wrote {args.output}")

    elif args.cmd == "validate-pack":
        md_text = args.markdown.read_text(encoding="utf-8", errors="replace")
        report = validate_pack_markdown(md_text, root=args.root)
        if report.warnings:
            print("Warnings:")
            for w in report.warnings:
                print(f"- {w}")
        if report.errors:
            print("Errors:")
            for e in report.errors:
                print(f"- {e}")
            raise SystemExit(1)
        print("OK: pack is internally consistent.")

    elif args.cmd == "apply":
        md_text = args.patch_markdown.read_text(encoding="utf-8", errors="replace")
        diff_text = _extract_diff_blocks(md_text)
        diffs = parse_unified_diff(diff_text)
        changed = apply_file_diffs(diffs, args.root)
        print(f"Applied patch to {len(changed)} file(s).")


if __name__ == "__main__":
    main()
