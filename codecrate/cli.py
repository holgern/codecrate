from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
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
    pack = sub.add_parser("pack", help="Pack a repository/directory into Markdown.")
    pack.add_argument("root", type=Path, help="Root directory to scan")
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


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "pack":
        root: Path = args.root.resolve()
        cfg = load_config(root)

        include = args.include if args.include is not None else cfg.include
        exclude = args.exclude if args.exclude is not None else cfg.exclude

        keep_docstrings = (
            cfg.keep_docstrings
            if args.keep_docstrings is None
            else bool(args.keep_docstrings)
        )
        include_manifest = (
            cfg.manifest if args.manifest is None else bool(args.manifest)
        )
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
        if args.output is not None:
            out_path = args.output
        else:
            out_path = Path(getattr(cfg, "output", "context.md"))
            if not out_path.is_absolute():
                out_path = root / out_path
        disc = discover_files(
            root=root,
            include=include,
            exclude=exclude,
            respect_gitignore=respect_gitignore,
        )
        pack, canonical = pack_repo(
            disc.root, disc.files, keep_docstrings=keep_docstrings, dedupe=dedupe
        )
        md = render_markdown(
            pack, canonical, layout=layout, include_manifest=include_manifest
        )
        # Always write the canonical, unsplit pack
        # for machine parsing (unpack/validate).
        out_path.write_text(md, encoding="utf-8")

        # Additionally, write split parts for LLM consumption, if requested.
        parts = split_by_max_chars(md, out_path, split_max_chars)
        extra = [p for p in parts if p.path != out_path]
        for part in extra:
            part.path.write_text(part.content, encoding="utf-8")

        if extra:
            print(f"Wrote {out_path} and {len(extra)} split part file(s).")
        else:
            print(f"Wrote {out_path}.")
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
