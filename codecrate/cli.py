from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .discover import discover_python_files
from .markdown import render_markdown
from .packer import pack_repo
from .token_budget import split_by_max_chars


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codecrate", description="Pack Python code into Markdown for LLM context."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pack = sub.add_parser("pack", help="Pack a repository/directory into Markdown.")
    pack.add_argument("root", type=Path, help="Root directory to scan")
    pack.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("context.md"),
        help="Output markdown path",
    )

    pack.add_argument(
        "--dedupe", action="store_true", help="Deduplicate identical function bodies"
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
        "--include", action="append", default=None, help="Include glob (repeatable)"
    )
    pack.add_argument(
        "--exclude", action="append", default=None, help="Exclude glob (repeatable)"
    )

    pack.add_argument(
        "--split-max-chars",
        type=int,
        default=None,
        help="If >0, split output into multiple .partN.md files by character count",
    )

    return p


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

        disc = discover_python_files(
            root=root,
            include=include,
            exclude=exclude,
            respect_gitignore=respect_gitignore,
        )

        pack, canonical = pack_repo(
            disc.root, disc.files, keep_docstrings=keep_docstrings, dedupe=dedupe
        )
        md = render_markdown(pack, canonical)

        out = args.output
        parts = split_by_max_chars(md, out, split_max_chars)
        for part in parts:
            part.path.write_text(part.content, encoding="utf-8")

        if len(parts) == 1:
            print(f"Wrote {parts[0].path}")
        else:
            print(f"Wrote {len(parts)} parts:")
            for part in parts:
                print(f" - {part.path}")


if __name__ == "__main__":
    main()
