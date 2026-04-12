from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .cli_shared import _prefix_repo_header
from .config import Config
from .discover import DEFAULT_EXCLUDES
from .options import PackOptions
from .output_model import PackRun
from .repositories import slugify_repo_label
from .security import SafetyFinding
from .token_budget import Part
from .tokens import TokenCounter
from .udiff import normalize_newlines


@dataclass(frozen=True)
class _MeasuredFile:
    path: Path
    rel: str
    text: str
    size_bytes: int
    is_binary: bool = False


def _resolve_output_path(cfg: Config, args: argparse.Namespace, root: Path) -> Path:
    if args.output is not None:
        return Path(args.output)
    out_path = Path(cfg.output)
    if not out_path.is_absolute():
        out_path = root / out_path
    return out_path


def _resolve_output_dir_and_prefix(output_path: Path) -> tuple[Path, str]:
    if output_path.suffix:
        return output_path.parent.resolve(), output_path.stem or "context"
    return output_path.resolve(), "context"


def _default_repo_label(root: Path) -> str:
    cwd = Path.cwd().resolve()
    resolved = root.resolve()
    try:
        rel = resolved.relative_to(cwd).as_posix()
        return rel or resolved.name or resolved.as_posix()
    except ValueError:
        return root.name or resolved.name or resolved.as_posix()


def _unique_label(root: Path, used: set[str]) -> str:
    base = _default_repo_label(root)
    label = base
    idx = 2
    while label in used:
        label = f"{base}-{idx}"
        idx += 1
    used.add(label)
    return label


def _slugify(label: str) -> str:
    return slugify_repo_label(label)


def _unique_slug(label: str, used: set[str]) -> str:
    base = _slugify(label)
    slug = base
    idx = 2
    while slug in used:
        slug = f"{base}-{idx}"
        idx += 1
    used.add(slug)
    return slug


def _combine_pack_markdown(packs: list[PackRun]) -> str:
    out: list[str] = []
    for i, pack in enumerate(packs):
        if i:
            out.append("\n\n")
        out.append(_prefix_repo_header(pack.markdown.rstrip() + "\n", pack.label))
    return "".join(out).rstrip() + "\n"


def _rewrite_split_part_links(text: str, filename_map: dict[str, str]) -> str:
    if not filename_map:
        return text
    pattern = re.compile("|".join(re.escape(name) for name in filename_map))
    return pattern.sub(lambda m: filename_map[m.group(0)], text)


def _index_and_part_paths(base_path: Path, count: int) -> list[Path]:
    paths = [base_path.with_name(f"{base_path.stem}.index{base_path.suffix}")]
    paths.extend(
        base_path.with_name(f"{base_path.stem}.part{i}{base_path.suffix}")
        for i in range(1, count)
    )
    return paths


def _rename_split_parts(parts: Sequence[Part], base_path: Path) -> list[Part]:
    if len(parts) <= 1:
        part = parts[0]
        return [
            Part(
                path=base_path,
                content=part.content,
                kind=part.kind,
                files=part.files,
                canonical_ids=part.canonical_ids,
                section_types=part.section_types,
            )
        ]

    new_paths = _index_and_part_paths(base_path, len(parts))
    old_names = [Path(p.path).name for p in parts]
    new_names = [p.name for p in new_paths]
    filename_map = {old: new for old, new in zip(old_names, new_names, strict=True)}

    out: list[Part] = []
    for old, new_path in zip(parts, new_paths, strict=True):
        content = old.content
        out.append(
            Part(
                path=new_path,
                content=_rewrite_split_part_links(content, filename_map),
                kind=old.kind,
                files=old.files,
                canonical_ids=old.canonical_ids,
                section_types=old.section_types,
            )
        )
    return out


def _oversized_split_parts(outputs: Sequence[Part], max_chars: int) -> list[Path]:
    if max_chars <= 0:
        return []
    oversized: list[Path] = []
    for idx, part in enumerate(outputs):
        if idx == 0:
            continue
        if len(part.content) > max_chars:
            oversized.append(part.path)
    return oversized


def _warn_oversized_split_outputs(
    *, label: str, paths: Sequence[Path], max_chars: int
) -> None:
    if not paths:
        return
    preview = ", ".join(path.name for path in paths[:3])
    suffix = "" if len(paths) <= 3 else ", ..."
    print(
        f"Warning: wrote {len(paths)} oversize split part(s) for {label} "
        f"that exceed split_max_chars {max_chars}: {preview}{suffix}",
        file=sys.stderr,
    )


def _pack_has_effective_dedupe(pack: object) -> bool:
    # True if any definition was remapped to a canonical id.
    # That means dedupe actually collapsed something.
    files = getattr(pack, "files", None)
    if files is None:
        return False
    for fp in files:
        for d in getattr(fp, "defs", []):
            if getattr(d, "id", None) != getattr(d, "local_id", None):
                return True
    return False


def _resolve_effective_nav_mode(
    nav_mode: str, split_max_chars: int
) -> Literal["compact", "full"]:
    mode = nav_mode.strip().lower()
    if mode == "auto":
        return "full" if split_max_chars > 0 else "compact"
    if mode == "compact":
        return "compact"
    if mode == "full":
        return "full"
    return "full"


def _print_pack_summary(
    *,
    out_path: Path,
    markdown: str,
    total_files: int,
    encoding: str,
) -> None:
    total_chars = len(markdown)
    total_tokens: str
    try:
        total_tokens = f"{TokenCounter(encoding).count(markdown):,}"
    except Exception:
        total_tokens = "n/a"

    print("", file=sys.stderr)
    print("Pack Summary:", file=sys.stderr)
    print("─────────────", file=sys.stderr)
    print(f"{'Total Files':>12}: {total_files:,} files", file=sys.stderr)
    print(f"{'Total Tokens':>12}: {total_tokens} tokens", file=sys.stderr)
    print(f"{'Total Chars':>12}: {total_chars:,} chars", file=sys.stderr)
    print(f"{'Output':>12}: {out_path.as_posix()}", file=sys.stderr)


def _emit_safety_warning(
    *,
    label: str,
    root: Path,
    findings: list[SafetyFinding],
) -> None:
    if not findings:
        return
    skipped = [f for f in findings if f.action == "skipped"]
    redacted = [f for f in findings if f.action == "redacted"]
    preview = ", ".join(
        f"{item.path.relative_to(root).as_posix()} ({item.reason})"
        for item in findings[:5]
    )
    suffix = "" if len(findings) <= 5 else ", ..."
    print(
        f"Warning: safety findings in {label}: "
        f"skipped={len(skipped)}, redacted={len(redacted)}; {preview}{suffix}",
        file=sys.stderr,
    )


def _resolve_worker_count(max_workers: int, item_count: int) -> int:
    if item_count <= 1:
        return 1
    if max_workers > 0:
        return max_workers
    cpu = os.cpu_count() or 1
    return max(2, min(32, cpu * 4, item_count))


def _is_likely_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True

    sample = data[:4096]
    if not sample:
        return False

    text_whitespace = {9, 10, 13}
    suspicious = 0
    for b in sample:
        if b in text_whitespace:
            continue
        if 32 <= b <= 126:
            continue
        if 128 <= b <= 255:
            # UTF-8 / extended bytes are allowed.
            continue
        suspicious += 1
    return suspicious / len(sample) > 0.30


def _read_measured_file(
    path: Path,
    root: Path,
    override_texts: dict[Path, str] | None,
    *,
    encoding_errors: str,
) -> _MeasuredFile:
    if override_texts is not None and path in override_texts:
        text = normalize_newlines(override_texts[path])
        data = text.encode("utf-8")
        return _MeasuredFile(
            path=path,
            rel=path.relative_to(root).as_posix(),
            text=text,
            size_bytes=len(data),
            is_binary=False,
        )

    data = path.read_bytes()
    is_binary = _is_likely_binary(data)
    text = ""
    if not is_binary:
        try:
            text = normalize_newlines(data.decode("utf-8", errors=encoding_errors))
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Failed to decode UTF-8 for {path.relative_to(root).as_posix()} "
                f"(encoding_errors={encoding_errors})"
            ) from e
    return _MeasuredFile(
        path=path,
        rel=path.relative_to(root).as_posix(),
        text=text,
        size_bytes=len(data),
        is_binary=is_binary,
    )


def _measure_files(
    *,
    files: list[Path],
    root: Path,
    max_workers: int,
    override_texts: dict[Path, str] | None = None,
    encoding_errors: str = "replace",
) -> list[_MeasuredFile]:
    worker_count = _resolve_worker_count(max_workers, len(files))
    if worker_count == 1:
        return [
            _read_measured_file(
                path, root, override_texts, encoding_errors=encoding_errors
            )
            for path in files
        ]
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        return list(
            pool.map(
                lambda p: _read_measured_file(
                    p,
                    root,
                    override_texts,
                    encoding_errors=encoding_errors,
                ),
                files,
            )
        )


def _count_tokens_parallel(
    *,
    files: list[_MeasuredFile],
    count_fn: Callable[[str], int],
    max_workers: int,
) -> dict[str, int]:
    worker_count = _resolve_worker_count(max_workers, len(files))
    if worker_count == 1:
        return {f.rel: int(count_fn(f.text)) for f in files}
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        pairs = list(pool.map(lambda f: (f.rel, int(count_fn(f.text))), files))
    return {k: v for k, v in pairs}


def _emit_budget_skip_warning(*, label: str, skipped: list[tuple[str, str]]) -> None:
    if not skipped:
        return
    preview = ", ".join(f"{rel} ({reason})" for rel, reason in skipped[:5])
    suffix = "" if len(skipped) <= 5 else ", ..."
    print(
        f"Warning: skipped {len(skipped)} file(s) due to per-file budgets in "
        f"{label}: {preview}{suffix}",
        file=sys.stderr,
    )


def _emit_binary_skip_warning(*, label: str, skipped: list[str]) -> None:
    if not skipped:
        return
    preview = ", ".join(skipped[:5])
    suffix = "" if len(skipped) <= 5 else ", ..."
    print(
        f"Warning: skipped {len(skipped)} likely-binary file(s) in "
        f"{label}: {preview}{suffix}",
        file=sys.stderr,
    )


def _manifest_json_output_path(
    *,
    manifest_json_arg: str | None,
    markdown_output: Path,
) -> Path | None:
    if manifest_json_arg is None:
        return None
    if manifest_json_arg.strip():
        return Path(manifest_json_arg)
    return markdown_output.with_name(f"{markdown_output.stem}.manifest.json")


def _index_json_output_path(
    *,
    index_json_arg: str | None,
    markdown_output: Path,
) -> Path | None:
    if index_json_arg is None:
        return None
    if index_json_arg.strip():
        return Path(index_json_arg)
    return markdown_output.with_name(f"{markdown_output.stem}.index.json")


def _standalone_unpacker_output_path(*, markdown_output: Path) -> Path:
    return markdown_output.with_name(f"{markdown_output.stem}.unpack.py")


def resolve_standalone_unpacker_output_path(
    *,
    markdown_output: Path,
    standalone_unpacker_arg: str | None,
) -> Path:
    if standalone_unpacker_arg is not None and standalone_unpacker_arg.strip():
        return Path(standalone_unpacker_arg)
    return _standalone_unpacker_output_path(markdown_output=markdown_output)


def _print_selected_files(*, label: str, root: Path, selected: list[Path]) -> None:
    print(
        f"Debug: selected files for {label} ({len(selected)}):",
        file=sys.stderr,
    )
    for path in selected:
        print(f"  - {path.relative_to(root).as_posix()}", file=sys.stderr)


def _print_skipped_files(*, label: str, skipped: list[tuple[str, str]]) -> None:
    print(
        f"Debug: skipped files for {label} ({len(skipped)}):",
        file=sys.stderr,
    )
    for rel, reason in skipped:
        print(f"  - {rel} ({reason})", file=sys.stderr)


def _print_effective_rules(*, label: str, root: Path, options: PackOptions) -> None:
    include = options.include or []
    exclude = DEFAULT_EXCLUDES + (options.exclude or [])
    print(f"Debug: effective rules for {label}:", file=sys.stderr)
    print(f"  include-source: {options.include_source}", file=sys.stderr)
    print(
        f"  include ({len(include)}): {', '.join(include) if include else '<none>'}",
        file=sys.stderr,
    )
    print(
        f"  exclude ({len(exclude)}): {', '.join(exclude) if exclude else '<none>'}",
        file=sys.stderr,
    )
    print(
        "  ignore-files: "
        f".gitignore={'yes' if options.respect_gitignore else 'no'}, "
        f".codecrateignore={'yes' if (root / '.codecrateignore').exists() else 'no'}",
        file=sys.stderr,
    )
    print(
        "  safety: "
        f"check={'on' if options.security_check else 'off'}, "
        f"content_sniff={'on' if options.security_content_sniff else 'off'}, "
        f"redaction={'on' if options.security_redaction else 'off'}, "
        f"report={'on' if options.safety_report else 'off'}, "
        f"path_rules(base={len(options.security_path_patterns)}, "
        f"add={len(options.security_path_patterns_add)}, "
        f"remove={len(options.security_path_patterns_remove)}), "
        f"content_rules={len(options.security_content_patterns)}",
        file=sys.stderr,
    )
