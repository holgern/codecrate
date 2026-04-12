from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python examples/list_entrypoints.py <index-json>")
        return 1
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for repository in payload.get("repositories", []):
        for entry in repository.get("entrypoint_paths", []):
            print(entry.get("entrypoint"), entry.get("reachable_count", 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
