from __future__ import annotations

from argparse import ArgumentParser, Namespace

from .cli_doctor_helpers import _run_config_schema, _run_config_show, _run_doctor


def run_doctor_command(parser: ArgumentParser, args: Namespace) -> None:
    if not args.root.exists() or not args.root.is_dir():
        parser.error(f"doctor: root is not a directory: {args.root}")
    _run_doctor(args.root)


def run_config_show_command(parser: ArgumentParser, args: Namespace) -> None:
    if not args.root.exists() or not args.root.is_dir():
        parser.error(f"config show: root is not a directory: {args.root}")
    _run_config_show(
        args.root,
        effective=bool(args.effective),
        as_json=bool(args.json),
    )


def run_config_schema_command(_parser: ArgumentParser, args: Namespace) -> None:
    _run_config_schema(as_json=bool(args.json))
