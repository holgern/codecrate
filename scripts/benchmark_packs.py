#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from codecrate.cli import main


def _default_repositories() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[1]
    return [
        repo_root / "tests" / "fixtures" / "repos" / "golden_single",
        repo_root / "tests" / "fixtures" / "repos" / "golden_stub",
        repo_root,
    ]


def _json_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _sidecar_family_sizes(payload: dict[str, Any]) -> dict[str, int]:
    repositories = payload.get("repositories", [])
    family_sizes: dict[str, int] = {
        "repositories": _json_size(repositories),
        "files": 0,
        "symbols": 0,
        "classes": 0,
        "lookup": 0,
        "analysis": 0,
        "reference_graph": 0,
    }
    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        family_sizes["files"] += _json_size(repository.get("files", []))
        family_sizes["symbols"] += _json_size(repository.get("symbols", []))
        family_sizes["classes"] += _json_size(repository.get("classes", []))
        family_sizes["lookup"] += _json_size(repository.get("lookup", {}))
        family_sizes["reference_graph"] += _json_size(
            repository.get("reference_graph", {})
        )
        analysis_payload = {
            key: repository.get(key)
            for key in (
                "graph",
                "test_links",
                "guide",
                "architecture",
                "package_summaries",
                "entrypoint_paths",
                "centrality_rank",
                "likely_edit_targets",
            )
            if key in repository
        }
        family_sizes["analysis"] += _json_size(analysis_payload)
    return family_sizes


def _run_case(
    *,
    root: Path,
    profile: str,
    index_json_mode: str | None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        output_path = temp_root / "context.md"
        args = ["pack", str(root), "-o", str(output_path), "--profile", profile]
        if index_json_mode is not None:
            args.extend(["--index-json-mode", index_json_mode])
        started_at = time.perf_counter()
        main(args)
        elapsed = time.perf_counter() - started_at
        markdown_size = output_path.stat().st_size
        entry: dict[str, Any] = {
            "repository": root.as_posix(),
            "profile": profile,
            "index_json_mode": index_json_mode,
            "markdown_bytes": markdown_size,
            "generation_time_seconds": round(elapsed, 6),
        }
        index_path = output_path.with_suffix(".index.json")
        if not index_path.exists():
            entry["index_json_bytes"] = 0
            entry["symbol_count"] = 0
            entry["file_count"] = 0
            entry["sidecar_family_bytes"] = {}
            return entry
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        repositories = payload.get("repositories", [])
        entry["index_json_bytes"] = index_path.stat().st_size
        entry["file_count"] = sum(
            len(repository.get("files", []))
            for repository in repositories
            if isinstance(repository, dict)
        )
        entry["symbol_count"] = sum(
            len(repository.get("symbols", []))
            for repository in repositories
            if isinstance(repository, dict)
        )
        entry["sidecar_family_bytes"] = _sidecar_family_sizes(payload)
        return entry


def main_cli() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark markdown and sidecar generation across pack profiles."
    )
    parser.add_argument(
        "repos",
        nargs="*",
        type=Path,
        help=(
            "Repository roots to benchmark (default: bundled fixture repos "
            "and this repo)."
        ),
    )
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        default=None,
        help="Profile to benchmark (repeatable).",
    )
    parser.add_argument(
        "--index-json-mode",
        action="append",
        dest="index_json_modes",
        default=None,
        help="Optional index-json mode to benchmark (repeatable).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Prints to stdout when omitted.",
    )
    args = parser.parse_args()

    repositories = args.repos or _default_repositories()
    profiles = args.profiles or ["human", "agent", "lean-agent", "portable-agent"]
    index_json_modes = args.index_json_modes or [None, "normalized", "minimal"]
    results = [
        _run_case(root=root.resolve(), profile=profile, index_json_mode=index_json_mode)
        for root in repositories
        for profile in profiles
        for index_json_mode in index_json_modes
    ]
    payload = {"format": "codecrate.benchmark.v1", "results": results}
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
