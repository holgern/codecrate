from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path

from . import cli as cli_impl
from .config import load_config
from .options import resolve_encoding_errors
from .validate import validate_pack_markdown


def run_validate_pack_command(parser: ArgumentParser, args: Namespace) -> None:
    if args.fail_on_root_drift and args.root is None:
        parser.error("validate-pack: --fail-on-root-drift requires --root")
    cfg_root = args.root if args.root is not None else Path.cwd()
    cfg = load_config(cfg_root)
    validate_encoding_errors = resolve_encoding_errors(
        cfg,
        args.encoding_errors,
    )
    try:
        md_text = cli_impl._read_text_with_policy(
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
        if cli_impl._is_no_manifest_error(e):
            cli_impl._raise_no_manifest_error(parser, command_name="validate-pack")
        raise
    policy_errors = cli_impl._validation_policy_errors(report, args)
    if args.json:
        print(cli_impl._validation_report_json_with_policy(report, policy_errors))
    else:
        cli_impl._print_grouped_validation_report(report)
        if policy_errors:
            print("Policy Errors:")
            for msg in policy_errors:
                print(f"- {msg}")
    if report.errors or policy_errors:
        raise SystemExit(1)
    if not args.json:
        print("OK: pack is internally consistent.")
