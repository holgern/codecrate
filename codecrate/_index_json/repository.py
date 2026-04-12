from __future__ import annotations

from typing import Any

from ..output_model import PackRun
from .common import _safety_payload, _split_policy
from .locators import _locator_space_order, _repo_reconstructed_root


def _repository_common_payload(
    run: PackRun,
    *,
    repo_markdown_path: str | None,
    repo_count: int,
    parts: list[dict[str, Any]],
    import_edges: list[dict[str, Any]],
    test_links: list[dict[str, Any]],
    guide: dict[str, list[str]],
    architecture: dict[str, list[str]],
    analysis_metadata: bool,
) -> dict[str, Any]:
    locator_space, secondary_locator_space = _locator_space_order(
        run.options.locator_space
    )
    payload = {
        "label": run.label,
        "slug": run.slug,
        "profile": run.options.profile,
        "locator_space": locator_space,
        "split_policy": _split_policy(run),
        "layout": run.effective_layout,
        "nav_mode": run.effective_nav_mode,
        "locator_mode": (
            "anchors+line-ranges" if repo_markdown_path is not None else "anchors"
        ),
        "has_manifest": run.options.include_manifest,
        "has_machine_header": run.options.include_manifest,
        "manifest_sha256": run.manifest_sha256,
        "markdown_path": repo_markdown_path,
        "parts": parts,
        "safety": _safety_payload(run),
    }
    if secondary_locator_space is not None:
        payload["secondary_locator_space"] = secondary_locator_space
    reconstructed_root = _repo_reconstructed_root(run, repo_count=repo_count)
    if reconstructed_root is not None:
        payload["reconstructed_root"] = reconstructed_root
    if analysis_metadata:
        if run.options.index_json_include_graph:
            payload["graph"] = {"import_edges": import_edges}
        if run.options.index_json_include_test_links:
            payload["test_links"] = test_links
        if run.options.index_json_include_guide:
            payload["guide"] = guide
            if architecture:
                payload["architecture"] = architecture
    return payload
