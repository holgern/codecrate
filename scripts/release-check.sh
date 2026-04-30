#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

step() { printf ":: %s\n" "$*"; }

step "ruff check"
ruff check .

step "ruff format --check"
ruff format --check .

step "pytest"
pytest -q

step "build sdist + wheel"
python -m build

step "smoke-test wheel in clean copy"
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

printf "All checks passed.\n"
