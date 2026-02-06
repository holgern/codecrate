[![PyPI - Version](https://img.shields.io/pypi/v/codecrate)](https://pypi.org/project/codecrate/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/codecrate)
![PyPI - Downloads](https://img.shields.io/pypi/dm/codecrate)
[![codecov](https://codecov.io/gh/holgern/codecrate/graph/badge.svg?token=iCHXwbjAXG)](https://codecov.io/gh/holgern/codecrate)

# codecrate

`codecrate` turns a Python repository into a Markdown "context pack" optimized for LLM consumption, with full round-trip support:

- `pack`: repo → context.md
- `unpack`: context.md → reconstructed files
- `patch`: old context.md + current repo → diff-only patch.md
- `apply`: patch.md → apply changes to repo

## Features

- **Markdown-native output**: Generates self-contained Markdown files with syntax highlighting
- **Symbol index**: Quick navigation to functions and classes
- **Deduplication**: Optionally deduplicate identical function bodies to save tokens
- **Two layout modes**:
  - `stubs`: Compact file stubs with function bodies in a separate "Function Library"
  - `full`: Complete file contents (no stubbing)
- **Round-trip support**: Reconstruct original files exactly from Markdown packs
- **Diff generation**: Create minimal patch Markdown files showing only changed code
- **Gitignore support**: Respect `.gitignore` when scanning files
- **Tool ignore support**: Respect `.codecrateignore` (always)
- **Targeted packing**: Optional `--stdin` mode to pack an explicit file list
- **Token diagnostics**: Optional CLI token reports (encoding, tree, top files)

## Installation

```bash
pip install -e .
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Quick Start

### Pack a Repository

Pack your current directory into `context.md`:

```bash
codecrate pack .
```

Pack with specific output file:

```bash
codecrate pack . -o my_project.md
```

### Unpack to Reconstruct Files

Reconstruct files from a packed Markdown:

```bash
codecrate unpack context.md -o reconstructed/
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

Create a `codecrate.toml` file in your repository root:

```toml
[codecrate]
# File patterns to include (default: ["**/*.py"])
include = ["**/*.py"]

# File patterns to exclude
exclude = ["**/test_*.py", "**/tests/**"]

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

# Split output into multiple files if char count exceeds this (0 = no split)
split_max_chars = 0

# Token diagnostics (CLI stderr output only; not written into context.md)
token_count_encoding = "o200k_base"
token_count_tree = false
token_count_tree_threshold = 0
top_files_len = 5
file_summary = true
```

## Command Reference

### `pack` - Pack Repository to Markdown

```bash
codecrate pack <root> [OPTIONS]
```

**Options:**

- `-o, --output PATH`: Output markdown path (default: `context.md`)
- `--dedupe`: Deduplicate identical function bodies
- `--layout {auto,stubs,full}`: Output layout mode
- `--nav-mode {auto,compact,full}`: Navigation density mode
- `--keep-docstrings` / `--no-keep-docstrings`: Keep docstrings in stubs
- `--respect-gitignore` / `--no-respect-gitignore`: Respect `.gitignore`
- `--include GLOB`: Include glob pattern (repeatable)
- `--exclude GLOB`: Exclude glob pattern (repeatable)
- `--stdin`: Read file paths from stdin (one per line)
- `--split-max-chars N`: Split output into `.partN.md` files
- `--token-count-tree [threshold]`: Show file tree with token counts; optional
  threshold shows only files with >=N tokens (for example,
  `--token-count-tree 100`)
- `--top-files-len N`: Show top N largest files by token count
- `--token-count-encoding NAME`: Tokenizer encoding for token counting
- `--file-summary` / `--no-file-summary`: Enable or disable pack summary output

When `--stdin` is used, only stdin-listed files are considered. Include globs are
not applied, but exclude patterns and ignore files still apply.

By default, codecrate prints a compact pack summary (total files, total tokens,
total chars, output path). Disable it with `--no-file-summary` or
`file_summary = false` in config.

### `unpack` - Reconstruct Files from Markdown

```bash
codecrate unpack <markdown> -o <out-dir>
```

**Options:**

- `-o, --out-dir PATH`: Output directory for reconstructed files (required)

### `patch` - Generate Diff-Only Patch

```bash
codecrate patch <old_markdown> <root> [OPTIONS]
```

**Options:**

- `-o, --output PATH`: Output patch markdown (default: `patch.md`)

### `apply` - Apply Patch to Repository

```bash
codecrate apply <patch_markdown> <root>
```

### `validate-pack` - Validate Pack

```bash
codecrate validate-pack <markdown> [--root PATH]
```

**Options:**

- `--root PATH`: Optional repo root to compare reconstructed files against

## Layout Modes

### Stubs Mode (Default for `auto` when dedupe is effective)

Creates compact file stubs with function bodies replaced by markers:

```python
def f(x):
    ...  # ↪ FUNC:0F203CE2

class C:
    def m(self):
        ...  # ↪ FUNC:6F8ECF73
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

## Workflow Example

### Initial Pack

```bash
# Create a baseline pack of your repository
codecrate pack . -o baseline.md

# Send baseline.md to an LLM for analysis
# LLM can navigate using the Symbol Index
# and read full code in the Files section
```

### Iterate with LLM

```bash
# After the LLM suggests changes, generate a patch
codecrate patch baseline.md . -o iteration1.md

# Send iteration1.md to the LLM (much smaller than full pack)
# Apply the LLM's changes
codecrate apply iteration1.md .

# Create new baseline for next iteration
codecrate pack . -o baseline.md
```

## Advanced Usage

### Packing Multiple Projects

```bash
# Pack different directories separately
codecrate pack src/backend -o backend.md
codecrate pack src/frontend -o frontend.md

# Or pack with specific include patterns
codecrate pack . --include "**/*.py" --exclude "**/migrations/**"
```

### Handling Large Contexts

```bash
# Split into multiple files to fit context windows
codecrate pack . --split-max-chars 50000

# This creates context.md, context.part1.md, context.part2.md, etc.
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
2. **Parsing**: Extracts symbol information (functions, classes) using Python's AST
3. **Packing**: Creates a structured manifest and canonical function definitions
4. **Rendering**: Generates Markdown with directory tree, symbol index, and file contents
5. **Validation**: Ensures round-trip consistency with SHA256 checksums

The Markdown format is designed to be:

- **Self-contained**: All necessary information in one file
- **Navigable**: Symbol index with jump links
- **Reversible**: Can reconstruct original files exactly
- **Diff-friendly**: Easy to generate minimal patches

## License

MIT
