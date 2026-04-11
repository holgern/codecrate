from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from . import cli as cli_impl
from .config import load_config
from .discover import discover_files
from .formats import MANIFEST_JSON_FORMAT_VERSION
from .index_json import build_index_payload, write_index_json
from .manifest import manifest_sha256, to_manifest
from .markdown import render_markdown_result
from .options import resolve_pack_options
from .output_model import PackRun
from .packer import pack_repo
from .security import SafetyFinding, apply_safety_filters, build_ruleset
from .token_budget import Part, split_by_max_chars
from .tokens import (
    TokenCounter,
    approx_token_count,
    format_token_count_tree,
    format_top_files,
    format_top_files_by_size,
)


def run_pack_command(parser: ArgumentParser, args: Namespace) -> None:  # noqa: C901
    if args.repo:
        if args.root is not None:
            parser.error("pack: specify either ROOT or --repo (repeatable), not both")
        roots = [r.resolve() for r in args.repo]
    else:
        if args.root is None:
            parser.error("pack: ROOT is required when --repo is not used")
        roots = [args.root.resolve()]
    stdin_files: list[Path] | None = None
    if args.stdin or args.stdin0:
        if args.repo:
            parser.error(
                "pack: --stdin/--stdin0 requires a single ROOT (do not use --repo)"
            )
        if args.stdin0:
            raw_chunks = sys.stdin.buffer.read().split(b"\0")
            raw_paths = [
                chunk.decode("utf-8", errors="replace") for chunk in raw_chunks if chunk
            ]
            if not raw_paths:
                parser.error(
                    "pack: --stdin0 was set but no file paths were provided on stdin"
                )
        else:
            raw_paths = [ln.strip() for ln in sys.stdin.read().splitlines()]
            raw_paths = [ln for ln in raw_paths if ln and not ln.startswith("#")]
            if not raw_paths:
                parser.error(
                    "pack: --stdin was set but no file paths were provided on stdin"
                )
        stdin_files = [Path(raw) for raw in raw_paths]

    used_labels: set[str] = set()
    used_slugs: set[str] = set()
    pack_runs = []

    for root in roots:
        cfg = load_config(root)
        try:
            options = resolve_pack_options(cfg, args)
        except ValueError as e:
            parser.error(f"pack: {e}")
        label = cli_impl._unique_label(root, used_labels)
        slug = cli_impl._unique_slug(label, used_slugs)

        if args.print_rules:
            cli_impl._print_effective_rules(label=label, root=root, options=options)

        disc = discover_files(
            root=root,
            include=options.include,
            exclude=options.exclude,
            respect_gitignore=options.respect_gitignore,
            explicit_files=stdin_files,
        )
        safe_files = disc.files
        safety_findings = []
        skipped = []
        redacted_files: dict[Path, str] = {}
        if options.security_check:
            try:
                ruleset = build_ruleset(
                    path_patterns=options.security_path_patterns,
                    path_patterns_add=options.security_path_patterns_add,
                    path_patterns_remove=options.security_path_patterns_remove,
                    content_patterns=options.security_content_patterns,
                )
            except ValueError as e:
                parser.error(f"pack: invalid security rule pattern: {e}")

            safety_result = apply_safety_filters(
                disc.root,
                disc.files,
                ruleset=ruleset,
                content_sniff=options.security_content_sniff,
                redaction=options.security_redaction,
            )
            safe_files = safety_result.safe_files
            skipped = safety_result.skipped
            redacted_files = safety_result.redacted_files
            safety_findings = safety_result.findings

        needs_token_counts = bool(
            options.token_report
            or options.max_file_tokens > 0
            or options.max_total_tokens > 0
        )
        token_backend = ""
        count_tokens = approx_token_count
        if needs_token_counts:
            try:
                counter = TokenCounter(options.token_count_encoding)
                token_backend = getattr(counter, "backend", "")
                counter.count("")
                count_tokens = counter.count
            except Exception as e:
                token_backend = "approx"
                count_tokens = approx_token_count
                print(
                    f"Warning: token counting disabled ({e}); "
                    "falling back to approximate counts.",
                    file=sys.stderr,
                )

        try:
            measured_files = cli_impl._measure_files(
                files=safe_files,
                root=disc.root,
                max_workers=options.max_workers,
                override_texts=redacted_files,
                encoding_errors=options.encoding_errors,
            )
        except ValueError as e:
            parser.error(f"pack: {e}")
        binary_measured = [m for m in measured_files if m.is_binary]
        if binary_measured:
            binary_skipped = [
                SafetyFinding(path=m.path, reason="binary", action="skipped")
                for m in binary_measured
            ]
            skipped.extend(binary_skipped)
            safety_findings.extend(binary_skipped)
            cli_impl._emit_binary_skip_warning(
                label=label,
                skipped=[m.rel for m in binary_measured],
            )
        measured_files = [m for m in measured_files if not m.is_binary]

        cli_impl._emit_safety_warning(
            label=label,
            root=disc.root,
            findings=safety_findings,
        )

        raw_token_counts: dict[str, int] = {}
        if options.max_file_tokens > 0 or options.max_total_tokens > 0:
            raw_token_counts = cli_impl._count_tokens_parallel(
                files=measured_files,
                count_fn=count_tokens,
                max_workers=options.max_workers,
            )

        kept_measured = []
        skipped_for_budget: list[tuple[str, str]] = []
        for measured in measured_files:
            if (
                options.max_file_bytes > 0
                and measured.size_bytes > options.max_file_bytes
            ):
                skipped_for_budget.append(
                    (measured.rel, f"bytes>{options.max_file_bytes}")
                )
                continue
            if options.max_file_tokens > 0:
                t = raw_token_counts.get(measured.rel, 0)
                if t > options.max_file_tokens:
                    skipped_for_budget.append(
                        (measured.rel, f"tokens>{options.max_file_tokens}")
                    )
                    continue
            kept_measured.append(measured)

        cli_impl._emit_budget_skip_warning(label=label, skipped=skipped_for_budget)

        total_bytes = sum(m.size_bytes for m in kept_measured)
        if options.max_total_bytes > 0 and total_bytes > options.max_total_bytes:
            raise SystemExit(
                f"pack: total bytes {total_bytes} exceed max_total_bytes "
                f"{options.max_total_bytes} for {label}"
            )

        if options.max_total_tokens > 0:
            total_tokens_raw = sum(
                raw_token_counts.get(m.rel, 0) for m in kept_measured
            )
            if total_tokens_raw > options.max_total_tokens:
                raise SystemExit(
                    f"pack: total tokens {total_tokens_raw} exceed "
                    f"max_total_tokens {options.max_total_tokens} for {label}"
                )

        files_for_pack = [m.path for m in kept_measured]
        file_texts = {m.path: m.text for m in kept_measured}
        file_bytes = {m.rel: m.size_bytes for m in kept_measured}

        if args.print_files:
            cli_impl._print_selected_files(
                label=label, root=disc.root, selected=files_for_pack
            )

        if args.print_skipped:
            skipped_details = [(item.path, item.reason) for item in disc.skipped]
            skipped_details.extend(
                (f.path.relative_to(disc.root).as_posix(), f.reason)
                for f in skipped
                if f.action == "skipped"
            )
            skipped_details.extend(skipped_for_budget)
            skipped_details = sorted(set(skipped_details))
            cli_impl._print_skipped_files(label=label, skipped=skipped_details)

        pack, canonical = pack_repo(
            disc.root,
            files_for_pack,
            keep_docstrings=options.keep_docstrings,
            dedupe=options.dedupe,
            symbol_backend=options.symbol_backend,
            file_texts=file_texts,
            max_workers=options.max_workers,
            encoding_errors=options.encoding_errors,
        )
        use_stubs = options.layout == "stubs" or (
            options.layout == "auto" and cli_impl._pack_has_effective_dedupe(pack)
        )
        effective_layout = "stubs" if use_stubs else "full"
        manifest_obj = to_manifest(pack, minimal=not use_stubs)
        manifest_checksum = manifest_sha256(manifest_obj)
        binary_count = sum(1 for f in skipped if f.reason == "binary")
        skipped_for_safety_count = sum(
            1 for f in skipped if not (f.reason == "binary" and f.action == "skipped")
        )
        redacted_count = sum(1 for f in safety_findings if f.action == "redacted")
        safety_entries = [
            {
                "path": f.path.relative_to(disc.root).as_posix(),
                "reason": f.reason,
                "action": f.action,
            }
            for f in sorted(
                safety_findings,
                key=lambda item: (
                    item.path.relative_to(disc.root).as_posix(),
                    item.action,
                    item.reason,
                ),
            )
        ]
        effective_nav_mode = cli_impl._resolve_effective_nav_mode(
            options.nav_mode,
            options.split_max_chars,
        )
        rendered = render_markdown_result(
            pack,
            canonical,
            layout=options.layout,
            nav_mode=effective_nav_mode,
            skipped_for_safety_count=skipped_for_safety_count,
            skipped_for_binary_count=binary_count,
            redacted_for_safety_count=redacted_count,
            include_safety_report=options.safety_report,
            safety_report_entries=safety_entries,
            include_manifest=options.include_manifest,
            manifest_data=manifest_obj,
            repo_label=label,
            repo_slug=slug,
        )
        md = rendered.markdown

        file_tokens: dict[str, int] = {}
        output_tokens = 0
        total_file_tokens = 0

        if options.token_report:
            output_tokens = count_tokens(md)
            diag_files = [
                cli_impl._MeasuredFile(
                    path=fp.path,
                    rel=fp.path.relative_to(pack.root).as_posix(),
                    text=(
                        fp.original_text
                        if effective_layout == "full"
                        else fp.stubbed_text
                    ),
                    size_bytes=file_bytes.get(
                        fp.path.relative_to(pack.root).as_posix(),
                        len(fp.original_text.encode("utf-8")),
                    ),
                )
                for fp in pack.files
            ]
            file_tokens = cli_impl._count_tokens_parallel(
                files=diag_files,
                count_fn=count_tokens,
                max_workers=options.max_workers,
            )
            total_file_tokens = sum(file_tokens.values())

        default_output = cli_impl._resolve_output_path(cfg, args, root)

        pack_runs.append(
            PackRun(
                root=root,
                label=label,
                slug=slug,
                markdown=md,
                render_metadata=rendered.metadata,
                pack_result=pack,
                canonical_sources=canonical,
                options=options,
                default_output=default_output,
                file_count=len(files_for_pack),
                skipped_for_safety_count=skipped_for_safety_count,
                redacted_for_safety_count=redacted_count,
                safety_findings=safety_findings,
                effective_layout=effective_layout,
                effective_nav_mode=effective_nav_mode,
                output_tokens=output_tokens,
                total_file_tokens=total_file_tokens,
                file_tokens=file_tokens,
                file_bytes=file_bytes,
                token_backend=token_backend,
                manifest=manifest_obj,
                manifest_sha256=manifest_checksum,
            )
        )

    out_path = args.output if args.output is not None else pack_runs[0].default_output
    if len(pack_runs) == 1:
        md = pack_runs[0].markdown
    else:
        md = cli_impl._combine_pack_markdown(pack_runs)

    wrote_split_outputs = False
    split_files_written: list[Path] = []
    repo_output_parts: dict[str, list[Part]] = {}
    if len(pack_runs) == 1:
        split_max_chars = pack_runs[0].options.split_max_chars
        try:
            parts = split_by_max_chars(
                md,
                out_path,
                split_max_chars,
                strict=pack_runs[0].options.split_strict,
                allow_cut_files=pack_runs[0].options.split_allow_cut_files,
            )
        except ValueError as e:
            raise SystemExit(f"pack: {e}") from e
        if len(parts) == 1 and parts[0].path == out_path:
            out_path.write_text(md, encoding="utf-8")
            repo_output_parts[pack_runs[0].slug] = [Part(path=out_path, content=md)]
        else:
            renamed = cli_impl._rename_split_parts(parts, out_path)
            oversized_parts = cli_impl._oversized_split_parts(renamed, split_max_chars)
            if pack_runs[0].options.split_strict and oversized_parts:
                raise SystemExit(
                    "pack: split_strict requires all non-index parts to fit "
                    f"within split_max_chars {split_max_chars}; oversize: "
                    f"{', '.join(path.name for path in oversized_parts)}"
                )
            for part in renamed:
                part.path.write_text(part.content, encoding="utf-8")
                split_files_written.append(part.path)
            wrote_split_outputs = True
            repo_output_parts[pack_runs[0].slug] = list(renamed)
            cli_impl._warn_oversized_split_outputs(
                label=pack_runs[0].label,
                paths=oversized_parts,
                max_chars=split_max_chars,
            )
    else:
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
            renamed = cli_impl._rename_split_parts(parts, repo_base)
            oversized_parts = cli_impl._oversized_split_parts(renamed, split_max_chars)
            if run_pack.options.split_strict and oversized_parts:
                raise SystemExit(
                    "pack: split_strict requires all non-index parts to fit "
                    f"within split_max_chars {split_max_chars} "
                    f"for {run_pack.label}; "
                    f"oversize: {', '.join(path.name for path in oversized_parts)}"
                )
            split_candidates.append((run_pack, renamed, oversized_parts))

        if all_repo_split:
            wrote_split_outputs = True
            for run_pack, renamed, oversized_parts in split_candidates:
                written_parts = []
                for part in renamed:
                    content_with_header = cli_impl._prefix_repo_header(
                        part.content, run_pack.label
                    )
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
                cli_impl._warn_oversized_split_outputs(
                    label=run_pack.label,
                    paths=oversized_parts,
                    max_chars=run_pack.options.split_max_chars,
                )
        else:
            out_path.write_text(md, encoding="utf-8")
            for run_pack in pack_runs:
                repo_output_parts[run_pack.slug] = [Part(path=out_path, content=md)]

    manifest_json_path = cli_impl._manifest_json_output_path(
        manifest_json_arg=args.manifest_json,
        markdown_output=out_path,
    )
    if manifest_json_path is not None:
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

    index_json_path = None
    if any(run.options.index_json_enabled for run in pack_runs):
        index_json_arg = args.index_json if args.index_json is not None else ""
        index_json_path = cli_impl._index_json_output_path(
            index_json_arg=index_json_arg,
            markdown_output=out_path,
        )
    if index_json_path is not None:
        payload = build_index_payload(
            codecrate_version=cli_impl._codecrate_version(),
            index_output_path=index_json_path,
            pack_runs=pack_runs,
            repo_output_parts=repo_output_parts,
            is_split=wrote_split_outputs,
        )
        write_index_json(index_json_path, payload)

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
                else format_top_files_by_size(
                    run.file_bytes, run.options.top_files_len
                )
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

    summary_run = next((run for run in pack_runs if run.options.file_summary), None)
    if summary_run is not None and not wrote_split_outputs:
        try:
            rel_out_path = out_path.relative_to(Path.cwd())
        except ValueError:
            rel_out_path = out_path
        summary_encoding = summary_run.options.token_count_encoding
        cli_impl._print_pack_summary(
            out_path=rel_out_path,
            markdown=md,
            total_files=sum(run.file_count for run in pack_runs),
            encoding=summary_encoding,
        )
    else:
        if wrote_split_outputs:
            if len(pack_runs) == 1:
                index_path = out_path.with_name(
                    f"{out_path.stem}.index{out_path.suffix}"
                )
                part_count = max(0, len(split_files_written) - 1)
                print(f"Wrote {index_path} and {part_count} split part file(s).")
            else:
                print(
                    f"Wrote split outputs for {len(pack_runs)} repos "
                    f"({len(split_files_written)} file(s))."
                )
        else:
            if len(pack_runs) == 1:
                print(f"Wrote {out_path}.")
            else:
                print(f"Wrote {out_path} for {len(pack_runs)} repos.")
        if manifest_json_path is not None:
            print(f"Wrote {manifest_json_path}.")
        if index_json_path is not None:
            print(f"Wrote {index_json_path}.")
