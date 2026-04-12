from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python examples/read_normalized_tables.py <index-json>")
        return 1
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for repository in payload.get("repositories", []):
        tables = repository.get("tables")
        if not isinstance(tables, dict):
            continue
        paths = tables.get("paths", [])
        qualnames = tables.get("qualnames", [])
        for symbol in repository.get("symbols", []):
            path = paths[symbol["p"]] if isinstance(symbol.get("p"), int) else None
            qualname = (
                qualnames[symbol["q"]] if isinstance(symbol.get("q"), int) else None
            )
            print(path, qualname)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
