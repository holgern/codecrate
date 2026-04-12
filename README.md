[![PyPI - Version](https://img.shields.io/pypi/v/codecrate)](https://pypi.org/project/codecrate/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/codecrate)
![PyPI - Downloads](https://img.shields.io/pypi/dm/codecrate)
[![codecov](https://codecov.io/gh/holgern/codecrate/graph/badge.svg?token=iCHXwbjAXG)](https://codecov.io/gh/holgern/codecrate)

# codecrate

`codecrate` turns a repository into a Markdown "context pack" optimized for LLM and coding-agent workflows, with round-trip and patch/apply support:

- `pack`: repo → context.md
- `unpack`: context.md → reconstructed files
- `patch`: old context.md + current repo → diff-only patch.md
- `apply`: patch.md → apply changes to repo

## Features

- **Markdown-native output**: Generates self-contained Markdown files with syntax highlighting
- **Symbol index**: Quick navigation to functions and classes
- **Versioned retrieval sidecar**: Optional JSON index output with full v1, compact/minimal v2, and normalized v3 modes
- **Deduplication**: Optionally deduplicate identical function bodies to save tokens
- **Two layout modes**:
  - `stubs`: Compact file stubs with function bodies in a separate "Function Library"
  - `full`: Complete file contents (no stubbing)
- **Output profiles**: `human`, `agent`, `lean-agent`, `hybrid`, and `portable`
- **Portable reconstruction**: Optional generated standalone unpacker script using only the Python standard library
- **Round-trip support**: Reconstruct original files exactly from Markdown packs
- **Diff generation**: Create minimal patch Markdown files showing only changed code
- **Baseline-aware patches**: Patch metadata binds diffs to baseline file hashes; `apply` refuses mismatched baselines
- **Strict validation policies**: Optional fail-on-warning, fail-on-root-drift, fail-on-redaction, and fail-on-safety-skip checks
- **Gitignore support**: Respect `.gitignore` when scanning files
- **Tool ignore support**: Respect `.codecrateignore` (always)
- **Targeted packing**: Optional `--stdin` / `--stdin0` mode to pack an explicit file list
- **Focused packs**: Narrow output to selected files or symbols and optionally expand to import neighbors and related tests
- **Include presets**: `python-only`, `python+docs` (default), `everything`
- **Debug visibility**: Optional `--print-files` and `--print-skipped` diagnostics
- **Token diagnostics**: Optional CLI token reports (encoding, tree, top files)
- **Scale controls**: Per-file skip budgets and hard total budgets (bytes/tokens)
- **Machine header**: Compact checksum block for fast manifest validation
- **Tooling manifests**: Optional JSON manifest sidecar output (`--manifest-json`)
- **Split retrieval metadata**: Split parts carry direct file/symbol membership in `index-json`
- **Safety controls**: Configurable path/content scanning rules, optional redaction, optional safety report
- **Mixed-language reporting**: Per-file language detection plus requested/used backend and extraction status
- **Dual ID strategy**: Markdown keeps short display IDs while `index-json` exposes stronger machine IDs for tooling
- **Environment diagnostics**: `codecrate doctor` reports config precedence, ignore files, and backend availability
- **CLI ergonomics**: `--version`, `pack --print-rules`, `config show --effective`, `config schema --json`, and baseline policy flags for `apply`

## Installation

```bash
pip install -e .
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Release Check

Before publishing, run:

```bash
python -m pip install build
./scripts/release-check.sh
```

This runs the lint, format, test, build, and non-VCS-tree portability gate in one
command. CI also smoke installs the built wheel from `dist/`.

## Quick Start

### Pack a Repository

Pack your current directory into `context.md`:

```bash
codecrate pack . -o context.md
```

Pack for agent-oriented retrieval workflows:

```bash
codecrate pack . -o context.md --profile agent
```

This uses the normalized v3 sidecar by default.

Pack for the leanest recommended agent workflow:

```bash
codecrate pack . -o context.md --profile lean-agent
```

This keeps normalized v3, disables analysis-heavy sidecar payloads by default,
and trims markdown scaffolding.

Pack with rich markdown plus an agent sidecar:

```bash
codecrate pack . -o context.md --profile hybrid
```

See `docs/index_json.rst` for the sidecar contract and lookup model.

This keeps the full v1-compatible sidecar.

Pack for zero-install reconstruction workflows:

```bash
codecrate pack . -o context.md --profile portable --emit-standalone-unpacker
python context.unpack.py -o reconstructed/
```

This keeps the unsplit markdown as the authoritative reconstruction source and
does not require `index-json`.

The generated standalone unpacker now reconstructs both manifest-enabled
`full` and `stubs` packs. The `portable` profile remains the recommended
default when you want a reconstruction-first `full` pack.

If you also want a retrieval sidecar for the reconstructed tree, add
`--index-json` or `--index-json-mode ...`. With the default
`--locator-space auto`, standalone-enabled packs switch the sidecar to
reconstructed locators automatically:

```bash
codecrate pack . -o context.md --profile portable \
  --emit-standalone-unpacker --index-json-mode normalized
```

Pack with specific output file and write the sidecars explicitly:

```bash
codecrate pack . -o my_project.md --manifest-json --index-json
```

Explicit `--index-json` defaults to the full v1-compatible sidecar. Use
`--index-json-mode compact`, `--index-json-mode minimal`, or
`--index-json-mode normalized` when you want leaner machine-first sidecars.

Generate the smallest recommended sidecar for agent workflows:

```bash
codecrate pack . -o context.md --index-json-mode normalized
```

Generate the smallest v2-compatible retrieval sidecar:

```bash
codecrate pack . -o context.md --index-json-mode minimal
```

Focus a pack around one symbol plus nearby imports and tests:

```bash
codecrate pack . -o context.md \
  --focus-symbol codecrate.cli:main \
  --include-import-neighbors 1 \
  --include-tests
```

### Unpack to Reconstruct Files

Reconstruct files from a packed Markdown:

```bash
codecrate unpack context.md -o reconstructed/
```

Validate before acting in CI or autonomous loops:

```bash
codecrate validate-pack context.md --root . --strict --fail-on-warning --fail-on-root-drift
```

### Generate and Apply Patches

1. Pack your repository as a baseline:

```bash
codecrate pack . -o baseline.md
```

2. Make changes to your code

3. Generate a patch:

```bash
codecrate patch baseline.md . -o changes.md
```

4. Apply the patch:

```bash
codecrate apply changes.md .
```

## Configuration

Codecrate reads config from the repository root with this precedence:

1. CLI flags
2. `.codecrate.toml` / `codecrate.toml`
3. `pyproject.toml` under `[tool.codecrate]`

Use this quick chooser for profile defaults:

| Use case                 | Profile      | Behavior                                                   |
| ------------------------ | ------------ | ---------------------------------------------------------- |
| Review-only markdown     | `human`      | Markdown-first output without profile-implied `index-json` |
| Retrieval / agent lookup | `agent`      | Compact nav plus normalized v3 `index-json`                |
| Lean agent retrieval     | `lean-agent` | Compact nav plus lean normalized v3 `index-json`           |
| Review plus tooling      | `hybrid`     | Rich markdown plus full v1-compatible `index-json`         |
| Portable reconstruction  | `portable`   | Manifest-enabled `full` layout for standalone unpacking    |

See `docs/config.rst` for the generated config reference, or run `codecrate config schema --json` for the machine-readable schema.

Create a `.codecrate.toml` or `codecrate.toml` file in your repository root:

```toml
[codecrate]
# File patterns to include (default preset: "python+docs")
include = ["**/*.py"]

# Include preset fallback when `include` is not set:
# "python-only" | "python+docs" | "everything"
include_preset = "python+docs"

# File patterns to exclude
exclude = ["**/test_*.py", "**/tests/**"]

# Output profile: "human" | "agent" | "lean-agent" | "hybrid" | "portable"
profile = "human"

# Retrieval sidecar mode: "full" | "compact" | "minimal" | "normalized"
# - explicit mode also enables index-json output
# - agent defaults to "normalized"
# - lean-agent defaults to "normalized" with lean analysis defaults
# - hybrid defaults to "full"
index_json_mode = "normalized"

# Explicitly enable or disable index-json independent of profile defaults
index_json_enabled = true

# Optional sidecar output paths; "" means use the default sibling path
manifest_json_output = ""
index_json_output = ""

# Write a standard-library-only <output>.unpack.py next to the pack
emit_standalone_unpacker = false
standalone_unpacker_output = ""

# Sidecar locator targets: "auto" | "markdown" | "reconstructed" | "dual"
# - auto resolves to reconstructed when a standalone unpacker is emitted
# - otherwise auto resolves to markdown
locator_space = "auto"

# Include or omit analysis-oriented sidecar/markdown metadata
analysis_metadata = true
index_json_include_graph = true
index_json_include_test_links = true
index_json_include_guide = true
index_json_include_file_imports = true
index_json_include_classes = true
index_json_include_exports = true
index_json_include_module_docstrings = true

# Optional size controls
index_json_pretty = true
index_json_include_semantic = true
index_json_include_purpose_text = true
index_json_include_file_summaries = true
index_json_include_relationships = true
markdown_include_repository_guide = true
markdown_include_symbol_index = true
markdown_include_directory_tree = true
markdown_include_environment_setup = true
markdown_include_how_to_use = true

# Optional v2 sidecar trimming knobs
index_json_include_lookup = true
index_json_include_symbol_index_lines = true

# Optional focus controls
focus_file = ["codecrate/cli.py"]
focus_symbol = ["codecrate.cli:main"]
include_import_neighbors = 1
include_reverse_import_neighbors = 1
include_same_package = true
include_entrypoints = true
include_tests = true

# Deduplicate identical function bodies (default: false)
dedupe = true

# Keep docstrings in stubbed file view (default: true)
keep_docstrings = true

# Respect .gitignore when scanning (default: true)
respect_gitignore = true

# Always respected when present (separate file, gitignore syntax):
# .codecrateignore

# Output layout: "auto", "stubs", or "full" (default: "auto")
# - auto: use stubs only if dedupe collapses something
# - stubs: always use stubs + Function Library
# - full: emit complete file contents
layout = "auto"

# Navigation density: "auto", "compact", or "full"
# - auto: compact for unsplit packs, full when split outputs are requested
nav_mode = "auto"

# Optional non-Python symbol extraction backend: auto|python|tree-sitter|none
# (Python files always use built-in AST parsing)
symbol_backend = "auto"

# Text decode policy when reading files: "replace" or "strict"
encoding_errors = "replace"

# Sensitive file filtering
security_check = true
security_content_sniff = false
security_redaction = false
safety_report = false
security_path_patterns = [".env", "*.pem", "*secrets*"]
security_path_patterns_add = ["*.vault"]
security_path_patterns_remove = ["*secrets*"]
security_content_patterns = [
  "private-key=(?i)-----BEGIN\\s+[A-Z ]*PRIVATE KEY-----",
  "aws-access-key-id=\\b(?:AKIA|ASIA)[0-9A-Z]{16}\\b",
]

# Split output into multiple files if char count exceeds this (0 = no split)
split_max_chars = 0

# Split policy for oversize logical blocks
split_strict = false
split_allow_cut_files = false

# Token diagnostics (CLI stderr output only; not written into context.md)
token_count_encoding = "o200k_base"
token_count_tree = false
token_count_tree_threshold = 0
top_files_len = 5

# Scale / performance controls
# - per-file limits skip files with a warning
# - total limits fail the run when exceeded
max_file_bytes = 0
max_total_bytes = 0
max_file_tokens = 0
max_total_tokens = 0

# Worker threads for IO/parsing/token counting (0 = auto)
max_workers = 0
file_summary = true
```

## Command Reference

### `pack` - Pack Repository to Markdown

```bash
codecrate pack <root> [OPTIONS]
```

**Options:**

- `-o, --output PATH`: Output markdown path (default: `context.md`)
- `--dedupe` / `--no-dedupe`: Enable or disable deduplication
- `--profile {human,agent,lean-agent,hybrid,portable}`: Output defaults profile (`agent` implies compact nav + normalized v3 index-json; `lean-agent` keeps normalized but trims default sidecar and markdown payloads)
- `--layout {auto,stubs,full}`: Output layout mode
- `--nav-mode {auto,compact,full}`: Navigation density mode
- `--symbol-backend {auto,python,tree-sitter,none}`: Non-Python symbol backend
- `--keep-docstrings` / `--no-keep-docstrings`: Keep docstrings in stubs
- `--respect-gitignore` / `--no-respect-gitignore`: Respect `.gitignore`
- `--security-check` / `--no-security-check`: Scan for sensitive files (set
  `--no-security-check` to skip scanning for sensitive data like API keys and
  passwords)
- `--security-content-sniff` / `--no-security-content-sniff`: Optional content
  sniffing for key/token patterns
- `--security-redaction` / `--no-security-redaction`: Redact flagged files instead
  of skipping them
- `--safety-report` / `--no-safety-report`: Include Safety Report section in output
- `--security-path-pattern PATTERN`: Override path rule set (repeatable)
- `--security-path-pattern-add PATTERN`: Append path rule(s) without replacing base set
- `--security-path-pattern-remove PATTERN`: Remove path rule(s) from base set
- `--security-content-pattern RULE`: Override content rule set (repeatable;
  `name=regex` or `regex`)
- `--include GLOB`: Include glob pattern (repeatable)
- `--include-preset {python-only,python+docs,everything}`: Select include preset
- `--exclude GLOB`: Exclude glob pattern (repeatable)
- `--analysis-metadata` / `--no-analysis-metadata`: Include repository guide plus analysis-oriented sidecar metadata
- `--focus-file PATH`: Focus the pack on a repo-relative file path (repeatable)
- `--focus-symbol MODULE:QUALNAME`: Focus the pack on a symbol (repeatable)
- `--include-import-neighbors N`: Expand focused packs by N local import-graph hops
- `--include-tests` / `--no-include-tests`: Include heuristically related tests for focused packs
- `--stdin`: Read file paths from stdin (one per line)
- `--stdin0`: Read file paths from stdin as NUL-separated entries
- `--print-files`: Debug-print selected files after filtering
- `--print-skipped`: Debug-print skipped files and reasons
- `--print-rules`: Debug-print effective include/exclude/ignore/safety rules
- `--split-max-chars N`: Split output into `.index.md` and `.partN.md` files
- `--split-strict` / `--no-split-strict`: Fail instead of writing oversize logical blocks
- `--split-allow-cut-files` / `--no-split-allow-cut-files`: Explicitly cut oversize file blocks across parts
- `--token-count-tree [threshold]`: Show file tree with token counts; optional
  threshold shows only files with >=N tokens (for example,
  `--token-count-tree 100`)
- `--top-files-len N`: Show top N largest files by token count
- `--token-count-encoding NAME`: Tokenizer encoding for token counting
- `--file-summary` / `--no-file-summary`: Enable or disable pack summary output
- `--max-file-bytes N`: Skip files above this byte limit
- `--max-total-bytes N`: Fail if included files exceed this byte limit
- `--max-file-tokens N`: Skip files above this token limit
- `--max-total-tokens N`: Fail if included files exceed this token limit
- `--max-workers N`: Max worker threads for IO/parsing/token counting
- `--manifest-json [PATH]`: Write manifest JSON for tooling
- `--index-json [PATH]`: Write retrieval-oriented index JSON for agents and tools (`--index-json` alone defaults to full v1 compatibility mode)
- `--index-json-mode {full,compact,minimal,normalized}`: Select sidecar mode and enable index-json output (`agent` defaults to `normalized`, `hybrid` defaults to `full`)
- `--index-json-pretty` / `--no-index-json-pretty`: Pretty-print or minify index-json output
- `--index-json-lookup` / `--no-index-json-lookup`: Include or trim v2 lookup maps
- `--index-json-symbol-index-lines` / `--no-index-json-symbol-index-lines`: Include or trim compact v2 symbol index line ranges
- `--index-json-graph`, `--index-json-test-links`, `--index-json-guide`, `--index-json-file-imports`, `--index-json-classes`, `--index-json-exports`, `--index-json-module-docstrings`, `--index-json-semantic`, `--index-json-purpose-text`, `--index-json-file-summaries`, `--index-json-relationships`: Independently include or trim analysis sections
- `--markdown-repository-guide`, `--markdown-symbol-index`, `--markdown-directory-tree`, `--markdown-environment-setup`, `--markdown-how-to-use`: Independently include or trim markdown guide sections
- `--no-index-json`: Disable index JSON output, including profile-implied defaults
- `--emit-standalone-unpacker`: Write `<output>.unpack.py` for zero-install reconstruction
- `--locator-space {auto,markdown,reconstructed,dual}`: Choose whether sidecar locators point into the markdown pack, the reconstructed file tree, or both (`auto` switches to reconstructed when `--emit-standalone-unpacker` is enabled)
- `--encoding-errors {replace,strict}`: UTF-8 decode policy for input files

When `--stdin`/`--stdin0` is used, only explicitly listed files are considered.
Include globs are not applied, but exclude patterns and ignore files still apply.
Outside-root and missing entries are skipped (see `--print-skipped`).
With `--print-skipped`, explicit-file filtering also reports reasons such as
`not-a-file`, `outside-root`, `duplicate`, `ignored`, and `excluded`.

By default, codecrate prints a compact pack summary (total files, total tokens,
total chars, output path). Disable it with `--no-file-summary` or
`file_summary = false` in config.

If tokenization backend initialization fails, codecrate falls back to heuristic
token counting and still prints top-N largest file summaries.

Code fences are automatically widened when file content contains backticks, so
generated markdown remains parsable.

When redaction is enabled, flagged files are kept in the pack with masked content.
Use `--safety-report` to include file-level actions/reasons (`skipped`/`redacted`).

### `unpack` - Reconstruct Files from Markdown

```bash
codecrate unpack <markdown> -o <out-dir>
```

**Options:**

- `-o, --out-dir PATH`: Output directory for reconstructed files (required)
- `--strict`: Fail on missing/broken part mappings

For combined packs (multiple `# Repository: ...` sections), files are unpacked to
`<out-dir>/<repo-slug>/...` per repository section.

### `patch` - Generate Diff-Only Patch

```bash
codecrate patch <old_markdown> <root> [--repo <label-or-slug>] [OPTIONS]
```

**Options:**

- `--repo <label-or-slug>`: Required when `<old_markdown>` contains multiple
  `# Repository:` sections; selects which repository baseline to diff against
- `-o, --output PATH`: Output patch markdown (default: `patch.md`)
- `--encoding-errors {replace,strict}`: UTF-8 decode policy for baseline/current files

### `apply` - Apply Patch to Repository

```bash
codecrate apply <patch_markdown> <root> [--repo <label-or-slug>] [--dry-run] [--check-baseline|--ignore-baseline] [--encoding-errors {replace,strict}]
```

When `<patch_markdown>` contains multiple `# Repository:` sections, `--repo` is
required to select one section.

Use `--dry-run` to parse and validate hunks without writing files.
Baseline policy flags:

- `--check-baseline`: require metadata + verify baseline hashes
- `--ignore-baseline`: skip baseline verification

Default behavior verifies baseline hashes when metadata exists.

### `validate-pack` - Validate Pack

```bash
codecrate validate-pack <markdown> [--root PATH] [--strict] [policy flags] [--json]
```

**Options:**

- `--root PATH`: Optional repo root to compare reconstructed files against
- `--strict`: Treat unresolved marker mapping as validation errors
- `--json`: Emit machine-readable report (`ok`, counts, errors, warnings)
- `--fail-on-warning`: Exit non-zero when any warnings are present
- `--fail-on-root-drift`: Exit non-zero when disk content differs from the pack
- `--fail-on-redaction`: Exit non-zero when the pack reports redacted files
- `--fail-on-safety-skip`: Exit non-zero when the pack reports safety-skipped files
- `--encoding-errors {replace,strict}`: UTF-8 decode policy for pack/root file reads

For combined packs, validation runs per repository section and reports scope-aware
errors/warnings grouped by section, with short reproduction hints. Cross-repo
anchor collisions are reported as errors.

If a pack was created with `--no-manifest`, machine operations (`unpack`, `patch`,
`validate-pack`) fail with a consistent hint to re-pack with manifest enabled.

### `doctor` - Environment Diagnostics

```bash
codecrate doctor [root]
```

Reports:

- config discovery and precedence (`.codecrate.toml` > `codecrate.toml` > `pyproject.toml`)
- detected ignore files (`.gitignore`, `.codecrateignore`)
- token backend availability and encoding probe
- optional parsing backend availability (tree-sitter)

### `config show` - Effective Config Inspection

```bash
codecrate config show [root] --effective
```

Reports:

- selected config source (or defaults-only)
- effective values after precedence resolution
- full resolved lists like `security_path_patterns` (after add/remove)
- configured lists like `security_content_patterns`

Optional machine-readable output:

```bash
codecrate config show . --effective --json
```

## Layout Modes

### Stubs Mode (Default for `auto` when dedupe is effective)

Creates compact file stubs with function bodies replaced by markers:

```python
def f(x):
    ...  # ↪ FUNC:v1:0F203CE2

class C:
    def m(self):
        ...  # ↪ FUNC:v1:6F8ECF73
```

Function bodies are stored in a separate "Function Library" section:

````markdown
## Function Library

### 0F203CE2 — `a.f` (a.py:L1–L2)

```python
def f(x):
    return x + 1
```
````

### 6F8ECF73 — `a.C.m` (a.py:L5–L6)

```python
    def m(self):
        return 42
```

````

This is ideal for:
- LLMs with limited context windows
- Repositories with duplicate code (when using `--dedupe`)
- Code review and analysis workflows

### Full Mode

Emits complete file contents without stubbing:

```python
def f(x):
    return x + 1

class C:
    def m(self):
        return 42
````

This is ideal for:

- Repositories without much duplicate code
- When you need complete context in one place
- When token limits are not a concern

## Agent Workflow Example

### Initial Pack

```bash
# Create a baseline pack with retrieval sidecars
codecrate pack . -o baseline.md --profile hybrid

# Validate against disk before using it in an automated loop
codecrate validate-pack baseline.md --root . --strict --fail-on-warning --fail-on-root-drift
```

### Iterate with LLM

```bash
# After the LLM suggests changes, generate a patch
codecrate patch baseline.md . -o iteration1.md

# Validate the patch application path before writing
codecrate apply iteration1.md . --dry-run

# Apply the LLM's changes with baseline verification
codecrate apply iteration1.md . --check-baseline

# Create new baseline for next iteration
codecrate pack . -o baseline.md --profile hybrid
```

## Advanced Usage

### Version

```bash
codecrate --version
```

### Packing Multiple Projects

```bash
# Pack different directories separately
codecrate pack src/backend -o backend
codecrate pack src/frontend -o frontend

# Or pack with specific include patterns
codecrate pack . --include "**/*.py" --exclude "**/migrations/**"
```

### Handling Large Contexts

```bash
# Configure a soft cap per part file
codecrate pack . --split-max-chars 50000

# This creates context.md, context.index.md, context.part1.md, context.part2.md, etc.

# Force strict failure instead of writing oversize logical blocks
codecrate pack . --split-max-chars 50000 --split-strict

# Or explicitly cut oversize file blocks across parts
codecrate pack . --split-max-chars 50000 --split-allow-cut-files --index-json

# Skip single huge files, but fail if remaining total is still too large
codecrate pack . --max-file-bytes 200000 --max-total-bytes 4000000

# Same idea for token budgets
codecrate pack . --max-file-tokens 5000 --max-total-tokens 120000
```

### Deduplication

```bash
# Enable deduplication to save tokens on duplicate code
codecrate pack . --dedupe

# Deduplication is most effective when you have:
# - Copy-pasted functions
# - Boilerplate code
# - Similar utility functions across modules
```

## How It Works

1. **Discovery**: Scans files according to include/exclude patterns
2. **Parsing**: Extracts symbol information using Python AST and optional non-Python backends
3. **Packing**: Creates a structured manifest and canonical function definitions
4. **Rendering**: Generates Markdown plus optional manifest/index sidecars
5. **Validation**: Ensures round-trip consistency with SHA256 checksums

## Format Invariants

- Pack format version: `codecrate.v4`
- Patch metadata format: `codecrate.patch.v1`
- Manifest JSON format: `codecrate.manifest-json.v1`
- Index JSON format: `codecrate.index-json.v1` / `v2` / `v3`
- Exactly one `codecrate-machine-header` and one `codecrate-manifest` fence per repository section
- Ordering is deterministic by normalized relative path and stable ID ordering

The Markdown format is designed to be:

- **Self-contained**: All necessary information in one file
- **Navigable**: Symbol index with jump links
- **Reversible**: Can reconstruct original files exactly
- **Diff-friendly**: Easy to generate minimal patches

## License

MIT
