from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

CONFIG_FILENAMES: tuple[str, ...] = (".codecrate.toml", "codecrate.toml")

DEFAULT_INCLUDES: list[str] = [
    "**/*.py",
    # Common packaging + repo metadata
    "pyproject.toml",
    "project.toml",
    "setup.cfg",
    "README*",
    "LICENSE*",
    # Docs
    "docs/**/*.rst",
    "docs/**/*.md",
]


@dataclass
class Config:
    # Default output path for `codecrate pack` when CLI does not specify -o/--output
    output: str = "context.md"
    keep_docstrings: bool = True
    dedupe: bool = False
    respect_gitignore: bool = True
    include: list[str] = field(default_factory=lambda: DEFAULT_INCLUDES.copy())
    exclude: list[str] = field(default_factory=list)
    split_max_chars: int = 0  # 0 means no splitting
    # Emit the `## Manifest` section (required for unpack/patch/validate-pack).
    # Disable only for LLM-only packs to save tokens.
    manifest: bool = True
    # Output layout:
    # - "stubs": always emit stubbed files + Function Library (current format)
    # - "full":  emit full file contents (no Function Library)
    # - "auto":  use "stubs" only if dedupe actually collapses something,
    #            otherwise use "full" (best token efficiency when no duplicates)
    layout: Literal["auto", "stubs", "full"] = "auto"
    # Token counting (CLI diagnostics; not included in pack output).
    token_count_encoding: str = "o200k_base"
    token_count_tree: bool = False
    token_count_tree_threshold: int = 0
    top_files_len: int = 5
    file_summary: bool = True


def _find_config_path(root: Path) -> Path | None:
    root = root.resolve()
    for name in CONFIG_FILENAMES:
        p = root / name
        if p.exists():
            return p
    return None


def load_config(root: Path) -> Config:
    cfg_path = _find_config_path(root)
    if cfg_path is None:
        return Config()

    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    section: dict[str, Any] = {}
    if isinstance(data, dict):
        # Preferred: [codecrate]
        cc = data.get("codecrate")
        if isinstance(cc, dict):
            section = cc
        else:
            # Also accept: [tool.codecrate] (common convention from pyproject.toml)
            tool = data.get("tool")
            if isinstance(tool, dict):
                cc2 = tool.get("codecrate")
                if isinstance(cc2, dict):
                    section = cc2
    cfg = Config()
    out = section.get("output", cfg.output)
    if isinstance(out, str) and out.strip():
        cfg.output = out.strip()
    cfg.keep_docstrings = bool(section.get("keep_docstrings", cfg.keep_docstrings))
    cfg.dedupe = bool(section.get("dedupe", cfg.dedupe))
    cfg.respect_gitignore = bool(
        section.get("respect_gitignore", cfg.respect_gitignore)
    )
    man = section.get("manifest", section.get("include_manifest", cfg.manifest))
    cfg.manifest = bool(man)
    layout = section.get("layout", cfg.layout)
    if isinstance(layout, str):
        layout = layout.strip().lower()
        if layout in {"auto", "stubs", "full"}:
            cfg.layout = layout  # type: ignore[assignment]

    inc = section.get("include", cfg.include)
    exc = section.get("exclude", cfg.exclude)
    if isinstance(inc, list):
        cfg.include = [str(x) for x in inc]
    if isinstance(exc, list):
        cfg.exclude = [str(x) for x in exc]

    split = section.get("split_max_chars", cfg.split_max_chars)
    try:
        cfg.split_max_chars = int(split)
    except Exception:
        pass

    enc = section.get("token_count_encoding", cfg.token_count_encoding)
    if isinstance(enc, str) and enc.strip():
        cfg.token_count_encoding = enc.strip()

    tree = section.get("token_count_tree", cfg.token_count_tree)
    cfg.token_count_tree = bool(tree)

    thr = section.get("token_count_tree_threshold", cfg.token_count_tree_threshold)
    try:
        cfg.token_count_tree_threshold = int(thr)
    except Exception:
        pass

    top = section.get("top_files_len", cfg.top_files_len)
    try:
        cfg.top_files_len = int(top)
    except Exception:
        pass

    summary = section.get("file_summary", cfg.file_summary)
    cfg.file_summary = bool(summary)

    return cfg
