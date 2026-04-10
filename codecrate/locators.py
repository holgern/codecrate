from __future__ import annotations


def _normalize_anchor(base: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in base.lower())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def anchor_for_symbol(defn_id: str) -> str:
    # Anchors should be stable under dedupe: multiple defs can share the same
    # canonical id, so we anchor by id only.
    return _normalize_anchor(f"func-{defn_id}")


def anchor_for_file_index(rel_path: str) -> str:
    return _normalize_anchor(f"file-{rel_path}")


def anchor_for_file_source(rel_path: str) -> str:
    return _normalize_anchor(f"src-{rel_path}")


def href(path: str | None, anchor: str | None) -> str | None:
    if not path or not anchor:
        return None
    return f"{path}#{anchor}"
