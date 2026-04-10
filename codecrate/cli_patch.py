from __future__ import annotations

from typing import Literal

from . import cli as cli_impl


def run_patch_command(parser: object, args: object) -> None:
    cfg = cli_impl.load_config(args.root)
    patch_encoding_errors = cli_impl.resolve_encoding_errors(cfg, args.encoding_errors)
    try:
        old_md = cli_impl._read_text_with_policy(
            args.old_markdown,
            encoding_errors=patch_encoding_errors,
        )
    except ValueError as e:
        parser.error(f"patch: {e}")
    old_sections = cli_impl.split_repository_sections(old_md)
    selected_label: str | None = None
    if old_sections:
        try:
            section = cli_impl.select_repository_section(
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
        patch_md = cli_impl.generate_patch_markdown(
            old_md,
            args.root,
            include=cfg.include,
            exclude=cfg.exclude,
            respect_gitignore=cfg.respect_gitignore,
            encoding_errors=patch_encoding_errors,
        )
    except ValueError as e:
        if cli_impl._is_no_manifest_error(e):
            cli_impl._raise_no_manifest_error(parser, command_name="patch")
        raise
    if old_sections and selected_label is not None:
        patch_md = cli_impl._prefix_repo_header(
            patch_md.rstrip() + "\n",
            selected_label,
        )
    args.output.write_text(patch_md, encoding="utf-8")
    print(f"Wrote {args.output}")


def run_apply_command(parser: object, args: object) -> None:
    cfg = cli_impl.load_config(args.root)
    apply_encoding_errors = cli_impl.resolve_encoding_errors(cfg, args.encoding_errors)
    try:
        md_text = cli_impl._read_text_with_policy(
            args.patch_markdown,
            encoding_errors=apply_encoding_errors,
        )
    except ValueError as e:
        parser.error(f"apply: {e}")
    patch_sections = cli_impl.split_repository_sections(md_text)
    if patch_sections:
        try:
            section = cli_impl.select_repository_section(
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

    diff_text = cli_impl._extract_diff_blocks(md_text)
    diffs = cli_impl.parse_unified_diff(diff_text)
    patch_meta = cli_impl._extract_patch_metadata(md_text)
    baseline_policy: Literal["auto", "require", "ignore"] = "auto"
    if args.check_baseline:
        baseline_policy = "require"
    elif args.ignore_baseline:
        baseline_policy = "ignore"
    try:
        cli_impl._verify_patch_baseline(
            root=args.root,
            diffs=diffs,
            patch_meta=patch_meta,
            encoding_errors=apply_encoding_errors,
            policy=baseline_policy,
        )
    except ValueError as e:
        parser.error(f"apply: {e}")
    try:
        changed = cli_impl.apply_file_diffs(
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
