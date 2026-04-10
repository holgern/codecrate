from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import PackResult
from .options import PackOptions
from .security import SafetyFinding


@dataclass(frozen=True)
class LineRange:
    start_line: int
    end_line: int


@dataclass(frozen=True)
class RenderMetadata:
    section_ranges: dict[str, LineRange]
    file_ranges: dict[str, LineRange]
    symbol_index_ranges: dict[str, LineRange]
    canonical_ranges: dict[str, LineRange]
    anchors_present: frozenset[str]


@dataclass(frozen=True)
class RenderedMarkdown:
    markdown: str
    metadata: RenderMetadata


@dataclass(frozen=True)
class PackRun:
    root: Path
    label: str
    slug: str
    markdown: str
    render_metadata: RenderMetadata
    pack_result: PackResult
    canonical_sources: dict[str, str]
    options: PackOptions
    default_output: Path
    file_count: int
    skipped_for_safety_count: int
    redacted_for_safety_count: int
    safety_findings: list[SafetyFinding]

    # Token diagnostics (optional)
    effective_layout: str
    effective_nav_mode: str
    output_tokens: int
    total_file_tokens: int
    file_tokens: dict[str, int]
    file_bytes: dict[str, int]
    token_backend: str
    manifest: dict[str, Any]
    manifest_sha256: str
