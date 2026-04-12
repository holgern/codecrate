from __future__ import annotations

import sys
from pathlib import Path

from .cli_parser import _print_top_level_help, build_parser
from .cli_shared import (
    _is_no_manifest_error,
    _raise_no_manifest_error,
    _read_text_with_policy,
)
from .unpacker import unpack_to_dir


def main(argv: list[str] | None = None) -> None:
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

    if args.cmd == "unpack":
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
        return

    if args.cmd == "patch":
        from .cli_patch import run_patch_command

        run_patch_command(parser, args)
        return

    if args.cmd == "validate-pack":
        from .cli_validate import run_validate_pack_command

        run_validate_pack_command(parser, args)
        return

    if args.cmd == "doctor":
        from .cli_doctor import run_doctor_command

        run_doctor_command(parser, args)
        return

    if args.cmd == "config" and args.config_cmd == "show":
        from .cli_doctor import run_config_show_command

        run_config_show_command(parser, args)
        return

    if args.cmd == "config" and args.config_cmd == "schema":
        from .cli_doctor import run_config_schema_command

        run_config_schema_command(parser, args)
        return

    if args.cmd == "apply":
        from .cli_patch import run_apply_command

        run_apply_command(parser, args)
        return


if __name__ == "__main__":
    main()
