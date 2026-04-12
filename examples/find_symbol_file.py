from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python examples/find_symbol_file.py <index-json> <qualname>")
        return 1
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    qualname = sys.argv[2]
    for repository in payload.get("repositories", []):
        for symbol in repository.get("symbols", []):
            if symbol.get("qualname") == qualname:
                print(f"{qualname}: {symbol.get('path')}")
                return 0
    print(f"{qualname}: not found")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
