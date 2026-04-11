from __future__ import annotations

from argparse import ArgumentParser, Namespace

from . import cli as cli_impl


def run_doctor_command(parser: ArgumentParser, args: Namespace) -> None:
    if not args.root.exists() or not args.root.is_dir():
        parser.error(f"doctor: root is not a directory: {args.root}")
    cli_impl._run_doctor(args.root)


def run_config_show_command(parser: ArgumentParser, args: Namespace) -> None:
    if not args.root.exists() or not args.root.is_dir():
        parser.error(f"config show: root is not a directory: {args.root}")
    cli_impl._run_config_show(
        args.root,
        effective=bool(args.effective),
        as_json=bool(args.json),
    )
