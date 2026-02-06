from __future__ import annotations

from dataclasses import dataclass

try:  # Optional dependency
    import tiktoken  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    tiktoken = None  # type: ignore

_ENCODER_CACHE: dict[str, object] = {}


def _approx_tokens(text: str) -> int:
    # Rough heuristic: ~4 characters per token in English-ish source text.
    return (len(text) + 3) // 4 if text else 0


def _get_encoder(name: str) -> object | None:
    if tiktoken is None:
        return None
    enc = _ENCODER_CACHE.get(name)
    if enc is None:
        enc = tiktoken.get_encoding(name)
        _ENCODER_CACHE[name] = enc
    return enc


@dataclass(frozen=True)
class TokenCounter:
    encoding: str = "o200k_base"

    @property
    def backend(self) -> str:
        return "tiktoken" if tiktoken is not None else "approx"

    def count(self, text: str) -> int:
        enc = _get_encoder(self.encoding)
        if enc is None:
            return _approx_tokens(text)
        return len(enc.encode(text))  # type: ignore[attr-defined]


class _Node:
    __slots__ = ("name", "children", "file_tokens", "total_tokens")

    def __init__(self, name: str) -> None:
        self.name = name
        self.children: dict[str, _Node] = {}
        self.file_tokens: int | None = None
        self.total_tokens: int = 0


def _build_tree(file_tokens: dict[str, int]) -> _Node:
    root = _Node(".")
    for path, n in file_tokens.items():
        parts = [p for p in path.split("/") if p]
        cur = root
        for part in parts:
            cur = cur.children.setdefault(part, _Node(part))
        cur.file_tokens = n
    return root


def _sum_tokens(node: _Node) -> int:
    total = node.file_tokens or 0
    for child in node.children.values():
        total += _sum_tokens(child)
    node.total_tokens = total
    return total


def format_token_count_tree(file_tokens: dict[str, int], threshold: int = 0) -> str:
    root = _build_tree(file_tokens)
    _sum_tokens(root)

    lines: list[str] = [
        f"🔢 Token Count Tree (threshold={threshold}):",
        "────────────────────",
        f"└── . ({root.total_tokens} tokens)",
    ]

    def rec(node: _Node, prefix: str, is_last: bool) -> None:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{node.name} ({node.total_tokens} tokens)")
        child_prefix = prefix + ("    " if is_last else "│   ")

        children = [c for c in node.children.values() if c.total_tokens >= threshold]
        children.sort(key=lambda n: (0 if n.children else 1, n.name))
        for i, child in enumerate(children):
            rec(child, child_prefix, i == len(children) - 1)

    children = [c for c in root.children.values() if c.total_tokens >= threshold]
    children.sort(key=lambda n: (0 if n.children else 1, n.name))
    for i, child in enumerate(children):
        rec(child, "    ", i == len(children) - 1)

    return "\n".join(lines)


def format_top_files(file_tokens: dict[str, int], top_n: int) -> str:
    if top_n <= 0:
        return ""
    items = sorted(file_tokens.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    lines = ["Top files by tokens:"]
    for i, (path, n) in enumerate(items, 1):
        lines.append(f"{i:>2}. {path} ({n} tokens)")
    return "\n".join(lines)
