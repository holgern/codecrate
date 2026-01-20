from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass
class Config:
    keep_docstrings: bool = True
    dedupe: bool = False
    respect_gitignore: bool = True
    include: list[str] = field(default_factory=lambda: ["**/*.py"])
    exclude: list[str] = field(default_factory=list)
    split_max_chars: int = 0  # 0 means no splitting


def load_config(root: Path) -> Config:
    """
    Loads `codecrate.toml` from root if present.
    """
    cfg_path = root / "codecrate.toml"
    if not cfg_path.exists():
        return Config()

    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    section: dict[str, Any] = (
        data.get("codecrate", {}) if isinstance(data, dict) else {}
    )

    cfg = Config()
    cfg.keep_docstrings = bool(section.get("keep_docstrings", cfg.keep_docstrings))
    cfg.dedupe = bool(section.get("dedupe", cfg.dedupe))
    cfg.respect_gitignore = bool(
        section.get("respect_gitignore", cfg.respect_gitignore)
    )

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

    return cfg
