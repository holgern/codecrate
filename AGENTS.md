# AGENTS.md

This file summarizes how to work in this repository for agentic tooling.
Follow these conventions unless a task explicitly requires otherwise.

## Repository Overview

- Project: `codecrate` (Python library + CLI)
- Package directory: `codecrate/`
- Tests: `tests/` with pytest
- Python support: 3.10+ (see `pyproject.toml`)
- Lint/format tooling: ruff + ruff-format (`.ruff.toml`)
- Pre-commit hooks: ruff, ruff-format, plus general hooks

## Key Config Files

- `pyproject.toml`: build metadata, optional deps, mypy config
- `.ruff.toml`: lint + format rules (target version, import order, complexity)
- `.pre-commit-config.yaml`: formatting and linting hooks
- `.github/workflows/tests.yml`: CI test commands
- `.github/pytest.ini`: pytest defaults (`-rw`, ignore dirs)
- `codecrate.toml`: runtime config for pack/unpack behavior

## Setup

Common install paths used in CI and docs:

- `uv pip install -e .`

## Build, Lint, Format, Test Commands

Run these from the repository root:

- Format: `ruff format .`
- Lint: `ruff check .`
- Lint + autofix: `ruff check --fix .`
- All tests: `pytest`
- Pre-commit hooks: `pre-commit run --all-files`

## Running a Single Test

Typical pytest patterns:

- One file: `pytest tests/test_parse.py`
- One test: `pytest tests/test_parse.py::test_parse_basic`
- By keyword: `pytest -k line_numbers`
- Show stdout: `pytest -s tests/test_smoke.py::test_cli_pack`

Pytest defaults (`.github/pytest.ini`) include:

- `addopts = -rw`
- `norecursedirs = .git .* *.egg* old dist build`

## Formatting and Linting Rules

Ruff is the source of truth for formatting and linting.
Configuration lives in `.ruff.toml`.

- Target Python: 3.10 (`target-version = "py310"`)
- Line length: ruff E501 defaults (88 unless configured otherwise)
- Import sorting: ruff isort with sections
- Complexity limit: McCabe max 22

When editing code, prefer running:

- `ruff format .`
- `ruff check --fix .`

## Import Conventions

Follow the existing import layout:

- `from __future__ import annotations` at the top of each module
- Standard library imports first
- Third-party imports next (rare here)
- First-party imports last (`codecrate.*` or relative)
- Keep imports sorted by ruff/isort

`__init__.py` files may intentionally have unused imports; ruff ignores
F401/I001 there (see `.ruff.toml`).

## Type Hints and Static Analysis

Type hints are expected on public functions and helpers.
The mypy config is strict, so avoid untyped defs when possible.

- Use `list[str]`, `dict[str, str]`, etc. (PEP 585 style)
- Prefer explicit `Optional[T]` via `T | None`
- Avoid implicit `Any` in new code

## Naming Conventions

- Modules, functions, variables: `snake_case`
- Classes, dataclasses: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private helpers: `_leading_underscore`

Follow existing naming in each module; avoid inventing new prefixes.

## File and Path Handling

The codebase favors `pathlib.Path`:

- Use `Path` instead of `os.path`
- For file IO, use `read_text`/`write_text`
- When reading text, pass `encoding="utf-8"` and `errors="replace"`
- Use `as_posix()` when storing relative paths

## Error Handling and Warnings

Keep error handling explicit and narrow:

- Raise `ValueError` for invalid user input
- Use `warnings.warn(..., RuntimeWarning)` for recoverable issues
- Avoid bare `except:` and broad `except Exception:` unless needed
- Prefer returning empty values over crashing when data is missing

## General Coding Practices

- Prefer small, focused helpers with explicit inputs/outputs
- Keep side effects near the CLI or IO boundaries
- Use dataclasses for structured data (see `codecrate/model.py`)
- Preserve existing section ordering in generated markdown

## Markdown and Output Formatting

Generated Markdown is line-sensitive. When modifying output:

- Preserve existing headings and section order
- Keep code fences exact (` ```python ` or ` ```diff `)
- Avoid adding trailing whitespace

## Tests and Fixtures

Tests are pytest-based and generally use `tmp_path`.
Keep tests deterministic and avoid external IO or network access.

- Use `tmp_path` for temp repos
- Use `Path.write_text(..., encoding="utf-8")`
- Prefer exact string comparisons for rendered output

## CLI and Commands

The CLI entrypoint is `codecrate.cli:main`.
When adding CLI flags, update both the parser and README if needed.

Quick reference:

- Pack: `codecrate pack . -o context.md`
- Unpack: `codecrate unpack context.md -o out_dir/`
- Patch: `codecrate patch baseline.md . -o changes.md`
- Apply: `codecrate apply changes.md .`
- Validate: `codecrate validate-pack context.md`

## Docs

Sphinx config lives under `docs/` (see `docs/conf.py`).
No automated doc build is configured in CI, but keep docs consistent
with CLI and configuration behavior.
