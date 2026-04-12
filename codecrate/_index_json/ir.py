from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..focus import FocusSelectionResult
from ..output_model import PackRun
from ..reference_analysis import ReferenceAnalysis


@dataclass(frozen=True)
class RepositoryIR:
    run: PackRun
    repo_markdown_path: str | None
    repo_count: int
    parts: list[dict[str, Any]]
    file_to_part: dict[str, str]
    file_index_to_part: dict[str, str]
    func_to_part: dict[str, str]
    markdown_path: str | None
    file_markdown_ranges: dict[str, dict[str, int]]
    symbol_index_ranges: dict[str, dict[str, int]]
    canonical_markdown_ranges: dict[str, dict[str, int]]
    reconstructed_root: str | None
    split_file_ranges: dict[str, dict[str, Any]]
    split_symbol_ranges: dict[str, dict[str, Any]]
    import_edges: list[dict[str, Any]]
    test_links: list[dict[str, Any]]
    guide: dict[str, list[str]]
    architecture: dict[str, list[str]]
    package_summaries: dict[str, dict[str, Any]]
    entrypoint_paths: list[dict[str, Any]]
    centrality_rank: list[dict[str, Any]]
    likely_edit_targets: list[str]
    imports_by_source: dict[str, list[dict[str, Any]]]
    role_hints: dict[str, str | None]
    relationship_summaries: dict[str, dict[str, list[str]]]
    file_summaries: dict[str, dict[str, Any]]
    reference_analysis: ReferenceAnalysis | None
    focus_selection: FocusSelectionResult | None
    repository_analysis_metadata: bool
    file_analysis_metadata: bool
    symbol_analysis_metadata: bool
