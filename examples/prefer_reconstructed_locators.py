from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: python examples/prefer_reconstructed_locators.py "
            "<index-json> <path>"
        )
        return 1
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    target_path = sys.argv[2]
    for repository in payload.get("repositories", []):
        for file_entry in repository.get("files", []):
            if file_entry.get("path") != target_path:
                continue
            locators = file_entry.get("locators") or {}
            locator = locators.get("reconstructed") or locators.get("markdown")
            if locator is not None:
                print(json.dumps(locator, indent=2, ensure_ascii=False))
                return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
