from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Literal

from .cli_shared import (
    _extract_diff_blocks,
    _extract_patch_metadata,
    _is_no_manifest_error,
    _prefix_repo_header,
    _raise_no_manifest_error,
    _read_text_with_policy,
    _verify_patch_baseline,
)
from .config import load_config
from .diffgen import generate_patch_markdown
from .options import resolve_encoding_errors
from .repositories import select_repository_section, split_repository_sections
from .udiff import apply_file_diffs, parse_unified_diff


def run_patch_command(parser: ArgumentParser, args: Namespace) -> None:
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
            "patch: --repo was provided, but old_markdown has no # Repository sections"
        )

    try:
        patch_md = generate_patch_markdown(
            old_md,
            args.root,
            include=cfg.include,
            exclude=cfg.exclude,
            respect_gitignore=cfg.respect_gitignore,
            gitignore_allow=cfg.gitignore_allow,
            encoding_errors=patch_encoding_errors,
        )
    except ValueError as e:
        if _is_no_manifest_error(e):
            _raise_no_manifest_error(parser, command_name="patch")
        raise
    if old_sections and selected_label is not None:
        patch_md = _prefix_repo_header(
            patch_md.rstrip() + "\n",
            selected_label,
        )
    args.output.write_text(patch_md, encoding="utf-8")
    print(f"Wrote {args.output}")


def run_apply_command(parser: ArgumentParser, args: Namespace) -> None:
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
