from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Part:
    path: Path
    content: str


def split_by_max_chars(markdown: str, out_path: Path, max_chars: int) -> list[Part]:
    if max_chars <= 0 or len(markdown) <= max_chars:
        return [Part(path=out_path, content=markdown)]

    parts: list[Part] = []
    chunk: list[str] = []
    chunk_len = 0
    idx = 1

    for block in markdown.split("\n\n"):
        add = block + "\n\n"
        if chunk_len + len(add) > max_chars and chunk:
            part_path = out_path.with_name(
                f"{out_path.stem}.part{idx}{out_path.suffix}"
            )
            parts.append(Part(path=part_path, content="".join(chunk).rstrip() + "\n"))
            idx += 1
            chunk = []
            chunk_len = 0
        chunk.append(add)
        chunk_len += len(add)

    if chunk:
        part_path = out_path.with_name(f"{out_path.stem}.part{idx}{out_path.suffix}")
        parts.append(Part(path=part_path, content="".join(chunk).rstrip() + "\n"))

    return parts
