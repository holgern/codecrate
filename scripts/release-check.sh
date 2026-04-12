#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

ruff check .
ruff format --check .
pytest -q
if command -v sphinx-build >/dev/null 2>&1; then
    sphinx-build -b dummy docs docs/_build/dummy
fi
python -m build

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

mkdir -p "$tmpdir/repo"
rsync -a \
    --exclude .git \
    --exclude .mypy_cache \
    --exclude .pytest_cache \
    --exclude .ruff_cache \
    --exclude build \
    --exclude dist \
    --exclude '*.egg-info' \
    ./ "$tmpdir/repo/" >/dev/null

(
    cd "$tmpdir/repo"
    python -m build
    python -m codecrate --version
)
