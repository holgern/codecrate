from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python examples/find_related_tests.py <index-json> <path>")
        return 1
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    target_path = sys.argv[2]
    for repository in payload.get("repositories", []):
        for file_entry in repository.get("files", []):
            if file_entry.get("path") == target_path:
                relationships = file_entry.get("relationships") or {}
                for test_path in relationships.get("related_tests", []):
                    print(test_path)
                return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
