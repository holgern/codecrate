from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .analysis_metadata import build_entrypoints, build_import_edges, build_test_links
from .cli_pack_helpers import (
    _count_tokens_parallel,
    _emit_binary_skip_warning,
    _emit_budget_skip_warning,
    _emit_safety_warning,
    _measure_files,
    _MeasuredFile,
    _pack_has_effective_dedupe,
    _print_effective_rules,
    _print_selected_files,
    _print_skipped_files,
    _resolve_effective_nav_mode,
    _resolve_output_path,
    _unique_label,
    _unique_slug,
)
from .config import load_config
from .discover import Discovery, discover_files
from .focus import FocusSelectionResult, build_focus_selection
from .manifest import manifest_sha256, to_manifest
from .markdown import render_markdown_result
from .model import PackResult
from .options import PackOptions, resolve_pack_options
from .output_model import PackRun
from .packer import pack_repo
from .security import SafetyFinding, apply_safety_filters, build_ruleset
from .tokens import TokenCounter, approx_token_count


def _resolve_output_index_json_mode(pack_runs: list[PackRun]) -> str:
    priority = {"normalized": 0, "minimal": 1, "compact": 2, "full": 3}
    modes = [
        str(run.options.index_json_mode)
        for run in pack_runs
        if run.options.index_json_enabled and run.options.index_json_mode is not None
    ]
    if not modes:
        return "full"
    return max(modes, key=lambda item: priority.get(item, -1))


@dataclass(frozen=True)
class _DiscoveryState:
    discovery: Discovery
    safe_files: list[Path]
    skipped: list[SafetyFinding]
    safety_findings: list[SafetyFinding]
    redacted_files: dict[Path, str]


@dataclass(frozen=True)
class _PreparedPackFiles:
    kept_measured: list[_MeasuredFile]
    skipped: list[SafetyFinding]
    safety_findings: list[SafetyFinding]
    skipped_for_budget: list[tuple[str, str]]
    raw_token_counts: dict[str, int]
    file_texts: dict[Path, str]
    file_bytes: dict[str, int]
    token_backend: str
    count_tokens: Callable[[str], int]


def _resolve_pack_roots_and_stdin(
    parser: ArgumentParser, args: Namespace
) -> tuple[list[Path], list[Path] | None]:
    has_focus_options = bool(getattr(args, "focus_file", None)) or bool(
        getattr(args, "focus_symbol", None)
    )
    has_focus_options = has_focus_options or bool(
        getattr(args, "include_import_neighbors", None)
    )
    has_focus_options = has_focus_options or bool(
        getattr(args, "include_reverse_import_neighbors", None)
    )
    has_focus_options = has_focus_options or bool(
        getattr(args, "include_same_package", None)
    )
    has_focus_options = has_focus_options or bool(
        getattr(args, "include_entrypoints", None)
    )
    has_focus_options = has_focus_options or bool(getattr(args, "include_tests", False))
    if args.repo:
        if args.root is not None:
            parser.error("pack: specify either ROOT or --repo (repeatable), not both")
        if has_focus_options:
            parser.error(
                "pack: focus options require a single ROOT (do not use --repo)"
            )
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
    return roots, stdin_files


def _discover_and_filter_files(
    parser: ArgumentParser,
    *,
    label: str,
    root: Path,
    options: PackOptions,
    stdin_files: list[Path] | None,
) -> _DiscoveryState:
    disc = discover_files(
        root=root,
        include=options.include,
        exclude=options.exclude,
        respect_gitignore=options.respect_gitignore,
        explicit_files=stdin_files,
    )
    safe_files = disc.files
    skipped: list[SafetyFinding] = []
    safety_findings: list[SafetyFinding] = []
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

    return _DiscoveryState(
        discovery=disc,
        safe_files=safe_files,
        skipped=skipped,
        safety_findings=safety_findings,
        redacted_files=redacted_files,
    )


def _build_token_counter(options: PackOptions) -> tuple[str, Callable[[str], int]]:
    needs_token_counts = bool(
        options.token_report
        or options.max_file_tokens > 0
        or options.max_total_tokens > 0
    )
    token_backend = ""
    count_tokens = approx_token_count
    if not needs_token_counts:
        return token_backend, count_tokens

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
    return token_backend, count_tokens


def _measure_and_apply_budgets(
    parser: ArgumentParser,
    *,
    label: str,
    options: PackOptions,
    discovery_state: _DiscoveryState,
) -> _PreparedPackFiles:
    token_backend, count_tokens = _build_token_counter(options)
    try:
        measured_files = _measure_files(
            files=discovery_state.safe_files,
            root=discovery_state.discovery.root,
            max_workers=options.max_workers,
            override_texts=discovery_state.redacted_files,
            encoding_errors=options.encoding_errors,
        )
    except ValueError as e:
        parser.error(f"pack: {e}")

    skipped = list(discovery_state.skipped)
    safety_findings = list(discovery_state.safety_findings)
    binary_measured = [m for m in measured_files if m.is_binary]
    if binary_measured:
        binary_skipped = [
            SafetyFinding(path=m.path, reason="binary", action="skipped")
            for m in binary_measured
        ]
        skipped.extend(binary_skipped)
        safety_findings.extend(binary_skipped)
        _emit_binary_skip_warning(
            label=label,
            skipped=[m.rel for m in binary_measured],
        )
    measured_files = [m for m in measured_files if not m.is_binary]

    _emit_safety_warning(
        label=label,
        root=discovery_state.discovery.root,
        findings=safety_findings,
    )

    raw_token_counts: dict[str, int] = {}
    if options.max_file_tokens > 0 or options.max_total_tokens > 0:
        raw_token_counts = _count_tokens_parallel(
            files=measured_files,
            count_fn=count_tokens,
            max_workers=options.max_workers,
        )

    kept_measured = []
    skipped_for_budget: list[tuple[str, str]] = []
    for measured in measured_files:
        if options.max_file_bytes > 0 and measured.size_bytes > options.max_file_bytes:
            skipped_for_budget.append((measured.rel, f"bytes>{options.max_file_bytes}"))
            continue
        if options.max_file_tokens > 0:
            token_count = raw_token_counts.get(measured.rel, 0)
            if token_count > options.max_file_tokens:
                skipped_for_budget.append(
                    (measured.rel, f"tokens>{options.max_file_tokens}")
                )
                continue
        kept_measured.append(measured)

    _emit_budget_skip_warning(label=label, skipped=skipped_for_budget)

    total_bytes = sum(m.size_bytes for m in kept_measured)
    if options.max_total_bytes > 0 and total_bytes > options.max_total_bytes:
        raise SystemExit(
            f"pack: total bytes {total_bytes} exceed max_total_bytes "
            f"{options.max_total_bytes} for {label}"
        )

    if options.max_total_tokens > 0:
        total_tokens_raw = sum(raw_token_counts.get(m.rel, 0) for m in kept_measured)
        if total_tokens_raw > options.max_total_tokens:
            raise SystemExit(
                f"pack: total tokens {total_tokens_raw} exceed "
                f"max_total_tokens {options.max_total_tokens} for {label}"
            )

    return _PreparedPackFiles(
        kept_measured=kept_measured,
        skipped=skipped,
        safety_findings=safety_findings,
        skipped_for_budget=skipped_for_budget,
        raw_token_counts=raw_token_counts,
        file_texts={m.path: m.text for m in kept_measured},
        file_bytes={m.rel: m.size_bytes for m in kept_measured},
        token_backend=token_backend,
        count_tokens=count_tokens,
    )


def _normalize_focus_path(raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return Path(value).as_posix()


def _resolve_focus_paths(pack: PackResult, options: PackOptions) -> set[str]:
    available_paths = {
        file_pack.path.relative_to(pack.root).as_posix() for file_pack in pack.files
    }
    selected: set[str] = set()
    missing: list[str] = []

    for raw_path in options.focus_file:
        rel = _normalize_focus_path(raw_path)
        if rel in available_paths:
            selected.add(rel)
        else:
            missing.append(raw_path)

    for raw_symbol in options.focus_symbol:
        query = raw_symbol.strip()
        matched = False
        if ":" in query:
            module, qualname = query.split(":", 1)
            for def_item in pack.defs:
                rel = def_item.path.relative_to(pack.root).as_posix()
                if def_item.module == module and def_item.qualname == qualname:
                    selected.add(rel)
                    matched = True
            for class_item in pack.classes:
                rel = class_item.path.relative_to(pack.root).as_posix()
                if class_item.module == module and class_item.qualname == qualname:
                    selected.add(rel)
                    matched = True
        else:
            for def_item in pack.defs:
                rel = def_item.path.relative_to(pack.root).as_posix()
                if def_item.qualname == query:
                    selected.add(rel)
                    matched = True
            for class_item in pack.classes:
                rel = class_item.path.relative_to(pack.root).as_posix()
                if class_item.qualname == query:
                    selected.add(rel)
                    matched = True
        if not matched:
            missing.append(raw_symbol)

    if missing:
        missing_text = ", ".join(f"`{item}`" for item in missing)
        raise ValueError(f"focus selectors matched no files for: {missing_text}")
    return selected


def _expand_import_neighbors(
    seed_paths: set[str],
    *,
    pack: PackResult,
    depth: int,
) -> set[str]:
    if depth <= 0 or not seed_paths:
        return set(seed_paths)

    adjacency: dict[str, set[str]] = {}
    for edge in build_import_edges(pack):
        if edge.target_path is None:
            continue
        adjacency.setdefault(edge.source_path, set()).add(edge.target_path)
        adjacency.setdefault(edge.target_path, set()).add(edge.source_path)

    selected = set(seed_paths)
    frontier = set(seed_paths)
    for _hop in range(depth):
        next_frontier: set[str] = set()
        for path in frontier:
            next_frontier.update(adjacency.get(path, set()))
        next_frontier -= selected
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier
    return selected


def _expand_reverse_import_neighbors(
    seed_paths: set[str],
    *,
    pack: PackResult,
    depth: int,
) -> set[str]:
    if depth <= 0 or not seed_paths:
        return set(seed_paths)

    reverse_adjacency: dict[str, set[str]] = {}
    for edge in build_import_edges(pack):
        if edge.target_path is None:
            continue
        reverse_adjacency.setdefault(edge.target_path, set()).add(edge.source_path)

    selected = set(seed_paths)
    frontier = set(seed_paths)
    for _hop in range(depth):
        next_frontier: set[str] = set()
        for path in frontier:
            next_frontier.update(reverse_adjacency.get(path, set()))
        next_frontier -= selected
        if not next_frontier:
            break
        selected.update(next_frontier)
        frontier = next_frontier
    return selected


def _include_same_package_neighbors(
    selected_paths: set[str],
    *,
    pack: PackResult,
) -> set[str]:
    if not selected_paths:
        return set(selected_paths)

    package_by_path: dict[str, str] = {}
    groups: dict[str, set[str]] = {}
    for file_pack in pack.files:
        rel = file_pack.path.relative_to(pack.root).as_posix()
        package = file_pack.module.rsplit(".", 1)[0] if "." in file_pack.module else ""
        if file_pack.path.name == "__init__.py":
            package = file_pack.module
        package_by_path[rel] = package
        groups.setdefault(package, set()).add(rel)

    expanded = set(selected_paths)
    for path in list(selected_paths):
        expanded.update(groups.get(package_by_path.get(path, ""), set()))
    return expanded


def _include_entrypoint_context(
    selected_paths: set[str],
    *,
    root: Path,
    pack: PackResult,
) -> set[str]:
    if not selected_paths:
        return set(selected_paths)

    adjacency: dict[str, set[str]] = {}
    for edge in build_import_edges(pack):
        if edge.target_path is None:
            continue
        adjacency.setdefault(edge.source_path, set()).add(edge.target_path)

    entrypoints = build_entrypoints(root=root, pack=pack)
    expanded = set(selected_paths)
    targets = set(selected_paths)
    for entrypoint in entrypoints:
        frontier = [entrypoint]
        seen = {entrypoint}
        found = False
        while frontier and not found:
            current = frontier.pop()
            if current in targets:
                found = True
                break
            for target in sorted(adjacency.get(current, set())):
                if target in seen:
                    continue
                seen.add(target)
                frontier.append(target)
        if found:
            expanded.add(entrypoint)
    return expanded


def _include_related_tests(
    selected_paths: set[str],
    *,
    pack: PackResult,
) -> set[str]:
    selected = set(selected_paths)
    for link in build_test_links(pack):
        if link.source_path in selected:
            selected.add(link.test_path)
    return selected


def _include_related_context(
    selected_paths: set[str], available_paths: set[str]
) -> set[str]:
    selected = set(selected_paths)
    for candidate in (
        "pyproject.toml",
        "codecrate.toml",
        ".codecrate.toml",
        "README.md",
        "README.rst",
    ):
        if candidate in available_paths:
            selected.add(candidate)
    return selected


def _apply_focus_selection(
    parser: ArgumentParser,
    *,
    root: Path,
    options: PackOptions,
    prepared_files: _PreparedPackFiles,
) -> tuple[list[_MeasuredFile], FocusSelectionResult | None]:
    if (
        not options.focus_file
        and not options.focus_symbol
        and options.include_import_neighbors <= 0
        and options.include_reverse_import_neighbors <= 0
        and not options.include_same_package
        and not options.include_entrypoints
        and not options.include_tests
    ):
        return prepared_files.kept_measured, None
    if not options.focus_file and not options.focus_symbol:
        parser.error(
            "pack: focus expansion options require --focus-file or --focus-symbol"
        )

    analysis_files = [item.path for item in prepared_files.kept_measured]
    analysis_pack, _canonical = pack_repo(
        root,
        analysis_files,
        keep_docstrings=options.keep_docstrings,
        dedupe=False,
        symbol_backend=options.symbol_backend,
        file_texts=prepared_files.file_texts,
        max_workers=options.max_workers,
        encoding_errors=options.encoding_errors,
    )

    try:
        focus_selection = build_focus_selection(
            root=root,
            pack=analysis_pack,
            options=options,
            available_paths={
                item.path.relative_to(root).as_posix()
                for item in prepared_files.kept_measured
            },
        )
    except ValueError as e:
        parser.error(f"pack: {e}")

    filtered = [
        item
        for item in prepared_files.kept_measured
        if item.path.relative_to(root).as_posix() in focus_selection.selected_paths
    ]
    if not filtered:
        parser.error("pack: focus options produced an empty file set")
    return filtered, focus_selection


def _build_single_pack_run(
    parser: ArgumentParser,
    args: Namespace,
    *,
    root: Path,
    stdin_files: list[Path] | None,
    used_labels: set[str],
    used_slugs: set[str],
) -> PackRun:
    cfg = load_config(root)
    try:
        options = resolve_pack_options(cfg, args)
    except ValueError as e:
        parser.error(f"pack: {e}")
    label = _unique_label(root, used_labels)
    slug = _unique_slug(label, used_slugs)

    if args.print_rules:
        _print_effective_rules(label=label, root=root, options=options)

    discovery_state = _discover_and_filter_files(
        parser,
        label=label,
        root=root,
        options=options,
        stdin_files=stdin_files,
    )
    prepared_files = _measure_and_apply_budgets(
        parser,
        label=label,
        options=options,
        discovery_state=discovery_state,
    )

    selected_measured, focus_selection = _apply_focus_selection(
        parser,
        root=discovery_state.discovery.root,
        options=options,
        prepared_files=prepared_files,
    )
    files_for_pack = [m.path for m in selected_measured]
    if args.print_files:
        _print_selected_files(
            label=label,
            root=discovery_state.discovery.root,
            selected=files_for_pack,
        )

    if args.print_skipped:
        skipped_details = [
            (item.path, item.reason) for item in discovery_state.discovery.skipped
        ]
        skipped_details.extend(
            (f.path.relative_to(discovery_state.discovery.root).as_posix(), f.reason)
            for f in prepared_files.skipped
            if f.action == "skipped"
        )
        skipped_details.extend(prepared_files.skipped_for_budget)
        skipped_details = sorted(set(skipped_details))
        _print_skipped_files(label=label, skipped=skipped_details)

    pack, canonical = pack_repo(
        discovery_state.discovery.root,
        files_for_pack,
        keep_docstrings=options.keep_docstrings,
        dedupe=options.dedupe,
        symbol_backend=options.symbol_backend,
        file_texts=prepared_files.file_texts,
        max_workers=options.max_workers,
        encoding_errors=options.encoding_errors,
    )
    use_stubs = options.layout == "stubs" or (
        options.layout == "auto" and _pack_has_effective_dedupe(pack)
    )
    effective_layout = "stubs" if use_stubs else "full"
    manifest_obj = to_manifest(pack, minimal=not use_stubs)
    manifest_checksum = manifest_sha256(manifest_obj)
    binary_count = sum(1 for f in prepared_files.skipped if f.reason == "binary")
    skipped_for_safety_count = sum(
        1
        for f in prepared_files.skipped
        if not (f.reason == "binary" and f.action == "skipped")
    )
    redacted_count = sum(
        1 for f in prepared_files.safety_findings if f.action == "redacted"
    )
    safety_entries = [
        {
            "path": f.path.relative_to(discovery_state.discovery.root).as_posix(),
            "reason": f.reason,
            "action": f.action,
        }
        for f in sorted(
            prepared_files.safety_findings,
            key=lambda item: (
                item.path.relative_to(discovery_state.discovery.root).as_posix(),
                item.action,
                item.reason,
            ),
        )
    ]
    effective_nav_mode = _resolve_effective_nav_mode(
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
        include_repository_guide=options.markdown_include_repository_guide,
        include_symbol_index=options.markdown_include_symbol_index,
        include_directory_tree=options.markdown_include_directory_tree,
        include_environment_setup=options.markdown_include_environment_setup,
        include_how_to_use=options.markdown_include_how_to_use,
        manifest_data=manifest_obj,
        repo_label=label,
        repo_slug=slug,
        focus_selection=focus_selection,
    )
    md = rendered.markdown

    file_tokens: dict[str, int] = {}
    output_tokens = 0
    total_file_tokens = 0
    if options.token_report:
        output_tokens = prepared_files.count_tokens(md)
        diag_files = [
            _MeasuredFile(
                path=fp.path,
                rel=fp.path.relative_to(pack.root).as_posix(),
                text=(
                    fp.original_text if effective_layout == "full" else fp.stubbed_text
                ),
                size_bytes=prepared_files.file_bytes.get(
                    fp.path.relative_to(pack.root).as_posix(),
                    len(fp.original_text.encode("utf-8")),
                ),
            )
            for fp in pack.files
        ]
        file_tokens = _count_tokens_parallel(
            files=diag_files,
            count_fn=prepared_files.count_tokens,
            max_workers=options.max_workers,
        )
        total_file_tokens = sum(file_tokens.values())

    default_output = _resolve_output_path(cfg, args, root)
    return PackRun(
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
        safety_findings=prepared_files.safety_findings,
        effective_layout=effective_layout,
        effective_nav_mode=effective_nav_mode,
        output_tokens=output_tokens,
        total_file_tokens=total_file_tokens,
        file_tokens=file_tokens,
        file_bytes=prepared_files.file_bytes,
        token_backend=prepared_files.token_backend,
        manifest=manifest_obj,
        manifest_sha256=manifest_checksum,
        focus_selection=focus_selection,
    )
