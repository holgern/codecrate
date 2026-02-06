from __future__ import annotations

from dataclasses import dataclass

from .fences import is_fence_close, parse_fence_open


@dataclass(frozen=True)
class RepositorySection:
    label: str
    slug: str
    content: str


def slugify_repo_label(label: str) -> str:
    safe: list[str] = []
    for ch in label:
        if ch.isalnum() or ch in {"-", "_"}:
            safe.append(ch)
        else:
            safe.append("-")
    slug = "".join(safe).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "repo"


def _unique_slug(base_label: str, used: set[str]) -> str:
    base = slugify_repo_label(base_label)
    slug = base
    idx = 2
    while slug in used:
        slug = f"{base}-{idx}"
        idx += 1
    used.add(slug)
    return slug


def split_repository_sections(markdown_text: str) -> list[RepositorySection]:
    """Split a combined markdown by top-level '# Repository: <label>' boundaries.

    Returns an empty list for single-repo markdown without repository boundaries.
    """

    lines = markdown_text.splitlines(keepends=True)
    fence: str | None = None
    headers: list[tuple[int, str]] = []

    for idx, line in enumerate(lines):
        if fence is None:
            opened = parse_fence_open(line)
            if opened is not None:
                fence = opened[0]
                continue
            if line.startswith("# Repository:"):
                label = line.split(":", 1)[1].strip() or f"repo-{len(headers) + 1}"
                headers.append((idx, label))
            continue

        if is_fence_close(line, fence):
            fence = None

    if not headers:
        return []

    used_slugs: set[str] = set()
    sections: list[RepositorySection] = []
    for pos, (start_idx, label) in enumerate(headers):
        body_start = start_idx + 1
        body_end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
        content = "".join(lines[body_start:body_end]).lstrip("\n")
        sections.append(
            RepositorySection(
                label=label,
                slug=_unique_slug(label, used_slugs),
                content=content,
            )
        )
    return sections


def format_repository_choices(sections: list[RepositorySection]) -> str:
    choices = [f"{section.label} ({section.slug})" for section in sections]
    return ", ".join(choices)


def select_repository_section(
    sections: list[RepositorySection],
    selector: str | None,
    *,
    command_name: str,
) -> RepositorySection:
    if not sections:
        raise ValueError(f"{command_name}: no # Repository sections were found")

    if selector is None:
        if len(sections) == 1:
            return sections[0]
        raise ValueError(
            f"{command_name}: combined markdown contains {len(sections)} repositories; "
            "use --repo <label-or-slug>. "
            f"Available: {format_repository_choices(sections)}"
        )

    exact = [s for s in sections if s.label == selector or s.slug == selector]
    if not exact:
        lowered = selector.lower()
        exact = [
            s
            for s in sections
            if s.label.lower() == lowered or s.slug.lower() == lowered
        ]
    if not exact:
        raise ValueError(
            f"{command_name}: unknown repo '{selector}'. "
            f"Available: {format_repository_choices(sections)}"
        )
    if len(exact) > 1:
        raise ValueError(
            f"{command_name}: ambiguous repo selector '{selector}'. "
            f"Matches: {format_repository_choices(exact)}"
        )
    return exact[0]
