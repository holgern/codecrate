from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .security import (
    DEFAULT_SENSITIVE_CONTENT_PATTERNS,
    DEFAULT_SENSITIVE_PATH_PATTERNS,
)

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

CONFIG_FILENAMES: tuple[str, ...] = (".codecrate.toml", "codecrate.toml")
PYPROJECT_FILENAME = "pyproject.toml"

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

INCLUDE_PRESETS: dict[str, list[str]] = {
    "python-only": ["**/*.py"],
    "python+docs": DEFAULT_INCLUDES,
    "everything": ["**/*"],
}
DEFAULT_INCLUDE_PRESET: Literal["python+docs"] = "python+docs"


def include_patterns_for_preset(name: str) -> list[str]:
    return list(INCLUDE_PRESETS.get(name, INCLUDE_PRESETS[DEFAULT_INCLUDE_PRESET]))


@dataclass
class Config:
    # Default output path for `codecrate pack` when CLI does not specify -o/--output
    output: str = "context.md"
    keep_docstrings: bool = True
    dedupe: bool = False
    respect_gitignore: bool = True
    include: list[str] = field(default_factory=lambda: DEFAULT_INCLUDES.copy())
    include_preset: Literal["python-only", "python+docs", "everything"] = (
        DEFAULT_INCLUDE_PRESET
    )
    exclude: list[str] = field(default_factory=list)
    split_max_chars: int = 0  # 0 means no splitting
    # Split policy for oversized logical blocks.
    # By default, oversized file/function blocks stay intact in an oversize part.
    split_strict: bool = False
    split_allow_cut_files: bool = False
    # Emit the `## Manifest` section (required for unpack/patch/validate-pack).
    # Disable only for LLM-only packs to save tokens.
    manifest: bool = True
    # Output defaults profile.
    # - "human": preserve current markdown-first behavior
    # - "agent": emit agent-sidecar defaults and compact navigation
    # - "hybrid": preserve current markdown behavior but emit index-json by default
    profile: Literal["human", "agent", "hybrid"] = "human"
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
    # Pack-size budgets; <=0 disables each limit.
    max_file_bytes: int = 0
    max_total_bytes: int = 0
    max_file_tokens: int = 0
    max_total_tokens: int = 0
    # Worker pool size for file IO/parsing/token diagnostics. <=0 means auto.
    max_workers: int = 0
    file_summary: bool = True
    # Safety filter for potentially sensitive files.
    security_check: bool = True
    security_content_sniff: bool = False
    security_redaction: bool = False
    safety_report: bool = False
    security_path_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_PATH_PATTERNS)
    )
    security_path_patterns_add: list[str] = field(default_factory=list)
    security_path_patterns_remove: list[str] = field(default_factory=list)
    security_content_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_CONTENT_PATTERNS)
    )
    # Navigation density for markdown pack output.
    # - "compact": omit file-level jump anchors/back-links to save tokens
    # - "full": keep all navigation helpers
    # - "auto": compact for unsplit packs, full when split outputs are requested
    nav_mode: Literal["auto", "compact", "full"] = "auto"
    # Retrieval sidecar mode for index-json output.
    # - None: let profile/default behavior decide whether to emit it
    # - "full": current v1-compatible sidecar
    # - "compact": slimmer v2 retrieval sidecar
    # - "minimal": smallest practical v2 retrieval sidecar
    index_json_mode: Literal["full", "compact", "minimal"] | None = None
    # Optional symbol extraction backend for non-Python files.
    # Python files always use the built-in AST parser.
    symbol_backend: Literal["auto", "python", "tree-sitter", "none"] = "auto"
    # Text decoding behavior when reading repository/markdown files.
    # - "replace": preserve operation by replacing invalid bytes (default)
    # - "strict": fail on invalid UTF-8 bytes
    encoding_errors: Literal["replace", "strict"] = "replace"


def _find_config_path(root: Path) -> Path | None:
    root = root.resolve()
    for name in CONFIG_FILENAMES:
        p = root / name
        if p.exists():
            return p
    pyproject = root / PYPROJECT_FILENAME
    if pyproject.exists():
        return pyproject
    return None


def _extract_section(data: Any, *, from_pyproject: bool) -> dict[str, Any]:
    section: dict[str, Any] = {}
    if not isinstance(data, dict):
        return section

    if not from_pyproject:
        # Preferred for dedicated config files: [codecrate]
        cc = data.get("codecrate")
        if isinstance(cc, dict):
            return cc

    # Supported in all files; required for pyproject.toml.
    tool = data.get("tool")
    if isinstance(tool, dict):
        cc2 = tool.get("codecrate")
        if isinstance(cc2, dict):
            return cc2

    return section


def load_config(root: Path) -> Config:  # noqa: C901
    cfg_path = _find_config_path(root)
    if cfg_path is None:
        return Config()

    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    section = _extract_section(data, from_pyproject=cfg_path.name == PYPROJECT_FILENAME)
    cfg = Config()
    out = section.get("output", cfg.output)
    if isinstance(out, str) and out.strip():
        raw_output = out.strip()
        output_path = Path(raw_output)
        if output_path.suffix or raw_output.endswith(("/", "\\")):
            cfg.output = raw_output
        else:
            cfg.output = f"{raw_output}.md"
    cfg.keep_docstrings = bool(section.get("keep_docstrings", cfg.keep_docstrings))
    cfg.dedupe = bool(section.get("dedupe", cfg.dedupe))
    cfg.respect_gitignore = bool(
        section.get("respect_gitignore", cfg.respect_gitignore)
    )
    man = section.get("manifest", section.get("include_manifest", cfg.manifest))
    cfg.manifest = bool(man)
    profile = section.get("profile", cfg.profile)
    if isinstance(profile, str):
        profile = profile.strip().lower()
        if profile in {"human", "agent", "hybrid"}:
            cfg.profile = profile  # type: ignore[assignment]
    layout = section.get("layout", cfg.layout)
    if isinstance(layout, str):
        layout = layout.strip().lower()
        if layout in {"auto", "stubs", "full"}:
            cfg.layout = layout  # type: ignore[assignment]

    include_preset = section.get("include_preset", cfg.include_preset)
    if isinstance(include_preset, str):
        include_preset = include_preset.strip().lower()
        if include_preset in INCLUDE_PRESETS:
            cfg.include_preset = include_preset  # type: ignore[assignment]

    inc = section.get("include")
    exc = section.get("exclude", cfg.exclude)
    if isinstance(inc, list):
        cfg.include = [str(x) for x in inc]
    elif inc is None:
        cfg.include = include_patterns_for_preset(cfg.include_preset)
    if isinstance(exc, list):
        cfg.exclude = [str(x) for x in exc]

    split = section.get("split_max_chars", cfg.split_max_chars)
    try:
        cfg.split_max_chars = int(split)
    except Exception:
        pass

    cfg.split_strict = bool(section.get("split_strict", cfg.split_strict))
    cfg.split_allow_cut_files = bool(
        section.get("split_allow_cut_files", cfg.split_allow_cut_files)
    )

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

    max_file_bytes = section.get("max_file_bytes", cfg.max_file_bytes)
    try:
        cfg.max_file_bytes = int(max_file_bytes)
    except Exception:
        pass

    max_total_bytes = section.get("max_total_bytes", cfg.max_total_bytes)
    try:
        cfg.max_total_bytes = int(max_total_bytes)
    except Exception:
        pass

    max_file_tokens = section.get("max_file_tokens", cfg.max_file_tokens)
    try:
        cfg.max_file_tokens = int(max_file_tokens)
    except Exception:
        pass

    max_total_tokens = section.get("max_total_tokens", cfg.max_total_tokens)
    try:
        cfg.max_total_tokens = int(max_total_tokens)
    except Exception:
        pass

    max_workers = section.get("max_workers", cfg.max_workers)
    try:
        cfg.max_workers = int(max_workers)
    except Exception:
        pass

    summary = section.get("file_summary", cfg.file_summary)
    cfg.file_summary = bool(summary)

    sec = section.get("security_check", cfg.security_check)
    cfg.security_check = bool(sec)

    sniff = section.get("security_content_sniff", cfg.security_content_sniff)
    cfg.security_content_sniff = bool(sniff)

    redaction = section.get("security_redaction", cfg.security_redaction)
    cfg.security_redaction = bool(redaction)

    safety_report = section.get("safety_report", cfg.safety_report)
    cfg.safety_report = bool(safety_report)

    path_patterns = section.get("security_path_patterns", cfg.security_path_patterns)
    if isinstance(path_patterns, list):
        cfg.security_path_patterns = [str(p) for p in path_patterns]

    path_patterns_add = section.get(
        "security_path_patterns_add",
        cfg.security_path_patterns_add,
    )
    if isinstance(path_patterns_add, list):
        cfg.security_path_patterns_add = [str(p) for p in path_patterns_add]

    path_patterns_remove = section.get(
        "security_path_patterns_remove",
        cfg.security_path_patterns_remove,
    )
    if isinstance(path_patterns_remove, list):
        cfg.security_path_patterns_remove = [str(p) for p in path_patterns_remove]

    content_patterns = section.get(
        "security_content_patterns",
        cfg.security_content_patterns,
    )
    if isinstance(content_patterns, list):
        cfg.security_content_patterns = [str(p) for p in content_patterns]

    nav_mode = section.get("nav_mode", cfg.nav_mode)
    if isinstance(nav_mode, str):
        nav_mode = nav_mode.strip().lower()
        if nav_mode in {"auto", "compact", "full"}:
            cfg.nav_mode = nav_mode  # type: ignore[assignment]

    index_json_mode = section.get("index_json_mode", cfg.index_json_mode)
    if isinstance(index_json_mode, str):
        index_json_mode = index_json_mode.strip().lower()
        if index_json_mode in {"full", "compact", "minimal"}:
            cfg.index_json_mode = index_json_mode  # type: ignore[assignment]

    backend = section.get("symbol_backend", cfg.symbol_backend)
    if isinstance(backend, str):
        backend = backend.strip().lower()
        if backend in {"auto", "python", "tree-sitter", "none"}:
            cfg.symbol_backend = backend  # type: ignore[assignment]

    encoding_errors = section.get("encoding_errors", cfg.encoding_errors)
    if isinstance(encoding_errors, str):
        encoding_errors = encoding_errors.strip().lower()
        if encoding_errors in {"replace", "strict"}:
            cfg.encoding_errors = encoding_errors  # type: ignore[assignment]

    return cfg
