from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path

from .cli_pack_helpers import (
    _combine_pack_markdown,
    _index_json_output_path,
    _manifest_json_output_path,
    _oversized_split_parts,
    _print_pack_summary,
    _rename_split_parts,
    _warn_oversized_split_outputs,
    resolve_standalone_unpacker_output_path,
)
from .cli_parser import _codecrate_version
from .cli_shared import _prefix_repo_header
from .formats import MANIFEST_JSON_FORMAT_VERSION
from .index_json import build_index_payload, write_index_json
from .output_model import PackRun
from .pack_pipeline import (
    _build_single_pack_run,
    _resolve_output_index_json_mode,
    _resolve_pack_roots_and_stdin,
)
from .standalone_unpacker import render_standalone_unpacker
from .token_budget import Part, split_by_max_chars
from .tokens import (
    format_token_count_tree,
    format_top_files,
    format_top_files_by_size,
)


@dataclass(frozen=True)
class _WrittenPackOutputs:
    wrote_split_outputs: bool
    wrote_unsplit_markdown: bool
    split_files_written: list[Path]
    repo_output_parts: dict[str, list[Part]]


def _resolve_shared_config_output(
    parser: ArgumentParser,
    *,
    cli_value: str | None,
    pack_runs: list[PackRun],
    attr_name: str,
    config_key: str,
) -> str | None:
    if cli_value is not None:
        return cli_value
    config_values: set[str] = set()
    for run in pack_runs:
        raw_value = getattr(run.options, attr_name, None)
        if raw_value is None:
            continue
        if raw_value == "":
            config_values.add(raw_value)
            continue
        path_value = Path(raw_value)
        if not path_value.is_absolute():
            path_value = run.root / path_value
        config_values.add(path_value.as_posix())
    if not config_values:
        return None
    if len(config_values) > 1:
        parser.error(
            "pack: conflicting config-defined "
            f"{config_key} values across repositories; use a CLI override"
        )
    return next(iter(config_values))


def _require_manifest_for_standalone(
    parser: ArgumentParser,
    *,
    emit_standalone_unpacker: bool,
    pack_runs: list[PackRun],
) -> None:
    if not emit_standalone_unpacker:
        return
    manifestless = [run.label for run in pack_runs if not run.options.include_manifest]
    if manifestless:
        parser.error(
            "--emit-standalone-unpacker requires a manifest-enabled pack "
            "(remove --no-manifest)."
        )


def _write_single_repo_outputs(
    *,
    out_path: Path,
    md: str,
    pack_run: PackRun,
    emit_standalone_unpacker: bool,
) -> _WrittenPackOutputs:
    split_max_chars = pack_run.options.split_max_chars
    try:
        parts = split_by_max_chars(
            md,
            out_path,
            split_max_chars,
            strict=pack_run.options.split_strict,
            allow_cut_files=pack_run.options.split_allow_cut_files,
        )
    except ValueError as e:
        raise SystemExit(f"pack: {e}") from e

    if len(parts) == 1 and parts[0].path == out_path:
        out_path.write_text(md, encoding="utf-8")
        return _WrittenPackOutputs(
            wrote_split_outputs=False,
            wrote_unsplit_markdown=True,
            split_files_written=[],
            repo_output_parts={pack_run.slug: [Part(path=out_path, content=md)]},
        )

    renamed = _rename_split_parts(parts, out_path)
    oversized_parts = _oversized_split_parts(renamed, split_max_chars)
    if pack_run.options.split_strict and oversized_parts:
        raise SystemExit(
            "pack: split_strict requires all non-index parts to fit "
            f"within split_max_chars {split_max_chars}; oversize: "
            f"{', '.join(path.name for path in oversized_parts)}"
        )

    split_files_written: list[Path] = []
    for part in renamed:
        part.path.write_text(part.content, encoding="utf-8")
        split_files_written.append(part.path)

    wrote_unsplit_markdown = False
    if emit_standalone_unpacker:
        out_path.write_text(md, encoding="utf-8")
        wrote_unsplit_markdown = True
    _warn_oversized_split_outputs(
        label=pack_run.label,
        paths=oversized_parts,
        max_chars=split_max_chars,
    )
    return _WrittenPackOutputs(
        wrote_split_outputs=True,
        wrote_unsplit_markdown=wrote_unsplit_markdown,
        split_files_written=split_files_written,
        repo_output_parts={pack_run.slug: list(renamed)},
    )


def _write_multi_repo_outputs(
    *,
    out_path: Path,
    md: str,
    pack_runs: list[PackRun],
    emit_standalone_unpacker: bool,
) -> _WrittenPackOutputs:
    all_repo_split = True
    split_candidates = []
    for run_pack in pack_runs:
        split_max_chars = run_pack.options.split_max_chars
        if split_max_chars <= 0:
            all_repo_split = False
            break
        repo_base = out_path.with_name(
            f"{out_path.stem}.{run_pack.slug}{out_path.suffix}"
        )
        try:
            parts = split_by_max_chars(
                run_pack.markdown,
                repo_base,
                run_pack.options.split_max_chars,
                strict=run_pack.options.split_strict,
                allow_cut_files=run_pack.options.split_allow_cut_files,
            )
        except ValueError as e:
            raise SystemExit(f"pack: {e}") from e
        if len(parts) == 1 and parts[0].path == repo_base:
            all_repo_split = False
            break
        renamed = _rename_split_parts(parts, repo_base)
        oversized_parts = _oversized_split_parts(renamed, split_max_chars)
        if run_pack.options.split_strict and oversized_parts:
            raise SystemExit(
                "pack: split_strict requires all non-index parts to fit "
                f"within split_max_chars {split_max_chars} "
                f"for {run_pack.label}; "
                f"oversize: {', '.join(path.name for path in oversized_parts)}"
            )
        split_candidates.append((run_pack, renamed, oversized_parts))

    if not all_repo_split:
        out_path.write_text(md, encoding="utf-8")
        return _WrittenPackOutputs(
            wrote_split_outputs=False,
            wrote_unsplit_markdown=True,
            split_files_written=[],
            repo_output_parts={
                run_pack.slug: [Part(path=out_path, content=md)]
                for run_pack in pack_runs
            },
        )

    split_files_written: list[Path] = []
    repo_output_parts: dict[str, list[Part]] = {}
    for run_pack, renamed, oversized_parts in split_candidates:
        written_parts = []
        for part in renamed:
            content_with_header = _prefix_repo_header(part.content, run_pack.label)
            final_part = Part(
                path=part.path,
                content=content_with_header,
                kind=part.kind,
                files=part.files,
                canonical_ids=part.canonical_ids,
                section_types=part.section_types,
            )
            final_part.path.write_text(final_part.content, encoding="utf-8")
            split_files_written.append(final_part.path)
            written_parts.append(final_part)
        repo_output_parts[run_pack.slug] = written_parts
        _warn_oversized_split_outputs(
            label=run_pack.label,
            paths=oversized_parts,
            max_chars=run_pack.options.split_max_chars,
        )

    wrote_unsplit_markdown = False
    if emit_standalone_unpacker:
        out_path.write_text(md, encoding="utf-8")
        wrote_unsplit_markdown = True
    return _WrittenPackOutputs(
        wrote_split_outputs=True,
        wrote_unsplit_markdown=wrote_unsplit_markdown,
        split_files_written=split_files_written,
        repo_output_parts=repo_output_parts,
    )


def _write_manifest_json_if_requested(
    *,
    manifest_json_arg: str | None,
    out_path: Path,
    pack_runs: list[PackRun],
) -> Path | None:
    manifest_json_path = _manifest_json_output_path(
        manifest_json_arg=manifest_json_arg,
        markdown_output=out_path,
    )
    if manifest_json_path is None:
        return None
    manifest_json_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "format": MANIFEST_JSON_FORMAT_VERSION,
        "repositories": [
            {
                "label": run.label,
                "slug": run.slug,
                "manifest_sha256": run.manifest_sha256,
                "manifest": run.manifest,
            }
            for run in pack_runs
        ],
    }
    manifest_json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return manifest_json_path


def _write_index_json_if_requested(
    *,
    index_json_arg: str | None,
    out_path: Path,
    pack_runs: list[PackRun],
    repo_output_parts: dict[str, list[Part]],
    wrote_split_outputs: bool,
) -> Path | None:
    if not any(run.options.index_json_enabled for run in pack_runs):
        return None
    index_json_path = _index_json_output_path(
        index_json_arg=index_json_arg or "",
        markdown_output=out_path,
    )
    if index_json_path is None:
        return None
    index_json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_index_payload(
        codecrate_version=_codecrate_version(),
        index_output_path=index_json_path,
        pack_runs=pack_runs,
        repo_output_parts=repo_output_parts,
        is_split=wrote_split_outputs,
        index_json_mode=_resolve_output_index_json_mode(pack_runs),
    )
    write_index_json(
        index_json_path,
        payload,
        pretty=any(run.options.index_json_pretty for run in pack_runs),
    )
    return index_json_path


def _emit_token_reports(pack_runs: list[PackRun]) -> None:
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
        if run.options.top_files_len:
            top_block = (
                format_top_files(run.file_tokens, run.options.top_files_len)
                if run.file_tokens
                else format_top_files_by_size(run.file_bytes, run.options.top_files_len)
            )
            if top_block:
                print(top_block, file=sys.stderr)
        if run.options.token_count_tree and run.file_tokens:
            print(
                format_token_count_tree(
                    run.file_tokens,
                    threshold=run.options.token_count_tree_threshold,
                ),
                file=sys.stderr,
            )


def _print_pack_output_summary(
    *,
    out_path: Path,
    md: str,
    pack_runs: list[PackRun],
    outputs: _WrittenPackOutputs,
    manifest_json_path: Path | None,
    index_json_path: Path | None,
) -> None:
    summary_run = next((run for run in pack_runs if run.options.file_summary), None)
    if summary_run is not None and not outputs.wrote_split_outputs:
        try:
            rel_out_path = out_path.relative_to(Path.cwd())
        except ValueError:
            rel_out_path = out_path
        summary_encoding = summary_run.options.token_count_encoding
        _print_pack_summary(
            out_path=rel_out_path,
            markdown=md,
            total_files=sum(run.file_count for run in pack_runs),
            encoding=summary_encoding,
        )
    else:
        if outputs.wrote_split_outputs:
            if len(pack_runs) == 1:
                index_path = out_path.with_name(
                    f"{out_path.stem}.index{out_path.suffix}"
                )
                part_count = max(0, len(outputs.split_files_written) - 1)
                if outputs.wrote_unsplit_markdown:
                    print(
                        f"Wrote {out_path}, {index_path}, and {part_count} split part "
                        "file(s)."
                    )
                else:
                    print(f"Wrote {index_path} and {part_count} split part file(s).")
            elif outputs.wrote_unsplit_markdown:
                print(
                    f"Wrote {out_path} plus split outputs for {len(pack_runs)} "
                    f"repos ({len(outputs.split_files_written)} file(s))."
                )
            else:
                print(
                    f"Wrote split outputs for {len(pack_runs)} repos "
                    f"({len(outputs.split_files_written)} file(s))."
                )
        elif len(pack_runs) == 1:
            print(f"Wrote {out_path}.")
        else:
            print(f"Wrote {out_path} for {len(pack_runs)} repos.")
        if manifest_json_path is not None:
            print(f"Wrote {manifest_json_path}.")
        if index_json_path is not None:
            print(f"Wrote {index_json_path}.")


def _write_standalone_unpacker_if_requested(
    *,
    emit_standalone_unpacker: bool,
    out_path: Path,
    pack_runs: list[PackRun],
    standalone_unpacker_output: str | None,
) -> None:
    if not emit_standalone_unpacker:
        return
    standalone_unpacker_path = resolve_standalone_unpacker_output_path(
        markdown_output=out_path,
        standalone_unpacker_arg=standalone_unpacker_output,
    )
    standalone_unpacker_path.parent.mkdir(parents=True, exist_ok=True)
    standalone_unpacker_path.write_text(
        render_standalone_unpacker(
            pack_format_version=pack_runs[0].manifest.get("format", ""),
            default_pack_filename=out_path.name,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {standalone_unpacker_path}.")


def _write_pack_outputs(
    parser: ArgumentParser,
    args: Namespace,
    *,
    pack_runs: list[PackRun],
) -> None:
    out_path = args.output if args.output is not None else pack_runs[0].default_output
    emit_standalone_unpacker = any(
        run.options.emit_standalone_unpacker for run in pack_runs
    )
    _require_manifest_for_standalone(
        parser,
        emit_standalone_unpacker=emit_standalone_unpacker,
        pack_runs=pack_runs,
    )
    if len(pack_runs) == 1:
        md = pack_runs[0].markdown
    else:
        md = _combine_pack_markdown(pack_runs)
    manifest_json_arg = _resolve_shared_config_output(
        parser,
        cli_value=args.manifest_json,
        pack_runs=pack_runs,
        attr_name="manifest_json_output",
        config_key="manifest_json_output",
    )
    index_json_arg = _resolve_shared_config_output(
        parser,
        cli_value=args.index_json,
        pack_runs=pack_runs,
        attr_name="index_json_output",
        config_key="index_json_output",
    )
    standalone_unpacker_output = _resolve_shared_config_output(
        parser,
        cli_value=None,
        pack_runs=pack_runs,
        attr_name="standalone_unpacker_output",
        config_key="standalone_unpacker_output",
    )
    outputs = (
        _write_single_repo_outputs(
            out_path=out_path,
            md=md,
            pack_run=pack_runs[0],
            emit_standalone_unpacker=emit_standalone_unpacker,
        )
        if len(pack_runs) == 1
        else _write_multi_repo_outputs(
            out_path=out_path,
            md=md,
            pack_runs=pack_runs,
            emit_standalone_unpacker=emit_standalone_unpacker,
        )
    )
    manifest_json_path = _write_manifest_json_if_requested(
        manifest_json_arg=manifest_json_arg,
        out_path=out_path,
        pack_runs=pack_runs,
    )
    index_json_path = _write_index_json_if_requested(
        index_json_arg=index_json_arg,
        out_path=out_path,
        pack_runs=pack_runs,
        repo_output_parts=outputs.repo_output_parts,
        wrote_split_outputs=outputs.wrote_split_outputs,
    )
    _emit_token_reports(pack_runs)
    _print_pack_output_summary(
        out_path=out_path,
        md=md,
        pack_runs=pack_runs,
        outputs=outputs,
        manifest_json_path=manifest_json_path,
        index_json_path=index_json_path,
    )
    _write_standalone_unpacker_if_requested(
        emit_standalone_unpacker=emit_standalone_unpacker,
        out_path=out_path,
        pack_runs=pack_runs,
        standalone_unpacker_output=standalone_unpacker_output,
    )


def run_pack_command(parser: ArgumentParser, args: Namespace) -> None:
    roots, stdin_files = _resolve_pack_roots_and_stdin(parser, args)

    used_labels: set[str] = set()
    used_slugs: set[str] = set()
    pack_runs: list[PackRun] = []

    for root in roots:
        pack_runs.append(
            _build_single_pack_run(
                parser,
                args,
                root=root,
                stdin_files=stdin_files,
                used_labels=used_labels,
                used_slugs=used_slugs,
            )
        )
    _write_pack_outputs(parser, args, pack_runs=pack_runs)
