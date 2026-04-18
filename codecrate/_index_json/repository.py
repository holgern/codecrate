from __future__ import annotations

from typing import Any

from ..reference_analysis import call_like_edges_payload
from .common import _safety_payload, _split_policy
from .ir import RepositoryIR
from .locators import _locator_space_order, _repo_reconstructed_root


def _repository_common_payload(
    ir: RepositoryIR,
) -> dict[str, Any]:
    run = ir.run
    locator_space, secondary_locator_space = _locator_space_order(
        run.options.locator_space
    )
    payload: dict[str, Any] = {
        "label": run.label,
        "slug": run.slug,
        "profile": run.options.profile,
        "locator_space": locator_space,
        "split_policy": _split_policy(run),
        "layout": run.effective_layout,
        "nav_mode": run.effective_nav_mode,
        "locator_mode": (
            "anchors+line-ranges" if ir.repo_markdown_path is not None else "anchors"
        ),
        "has_manifest": run.options.include_manifest,
        "has_machine_header": run.options.include_manifest,
        "manifest_sha256": run.manifest_sha256,
        "markdown_path": ir.repo_markdown_path,
        "parts": ir.parts,
        "safety": _safety_payload(run),
    }
    if secondary_locator_space is not None:
        payload["secondary_locator_space"] = secondary_locator_space
    reconstructed_root = _repo_reconstructed_root(run, repo_count=ir.repo_count)
    if reconstructed_root is not None:
        payload["reconstructed_root"] = reconstructed_root
    if ir.focus_selection is not None and ir.focus_selection.inclusion_reasons:
        payload["focus"] = ir.focus_selection.repository_payload()
    if ir.repository_analysis_metadata:
        if run.options.index_json_include_graph:
            payload["graph"] = {"import_edges": ir.import_edges}
        if run.options.index_json_include_test_links:
            payload["test_links"] = ir.test_links
        if run.options.index_json_include_guide:
            payload["guide"] = ir.guide
            if ir.architecture:
                payload["architecture"] = ir.architecture
            if ir.package_summaries:
                payload["package_summaries"] = ir.package_summaries
            if ir.entrypoint_paths:
                payload["entrypoint_paths"] = ir.entrypoint_paths
            if ir.centrality_rank:
                payload["centrality_rank"] = ir.centrality_rank
            if ir.likely_edit_targets:
                payload["likely_edit_targets"] = ir.likely_edit_targets
        if (
            run.options.index_json_include_symbol_references
            and ir.reference_analysis is not None
        ):
            payload["reference_graph"] = {
                "call_like_edges": call_like_edges_payload(ir.reference_analysis)
            }
    return payload
