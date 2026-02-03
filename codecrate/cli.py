from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .config import Config, load_config
from .diffgen import generate_patch_markdown
from .discover import discover_files
from .markdown import render_markdown
from .packer import pack_repo
from .token_budget import split_by_max_chars
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


@dataclass(frozen=True)
class PackRun:
    root: Path
    label: str
    slug: str
    markdown: str
    options: PackOptions
    default_output: Path


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
    return PackOptions(
        include=include,
        exclude=exclude,
        keep_docstrings=keep_docstrings,
        include_manifest=include_manifest,
        respect_gitignore=respect_gitignore,
        dedupe=dedupe,
        split_max_chars=split_max_chars,
        layout=layout,
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


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "pack":
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
            default_output = _resolve_output_path(cfg, args, root)
            pack_runs.append(
                PackRun(
                    root=root,
                    label=label,
                    slug=slug,
                    markdown=md,
                    options=options,
                    default_output=default_output,
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

        if extra_count:
            if len(pack_runs) == 1:
                print(f"Wrote {out_path} and {extra_count} split part file(s).")
            else:
                print(
                    f"Wrote {out_path} and {extra_count} split part file(s) for "
                    f"{len(pack_runs)} repos."
                )
        else:
            if len(pack_runs) == 1:
                print(f"Wrote {out_path}.")
            else:
                print(f"Wrote {out_path} for {len(pack_runs)} repos.")
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
