Command Line Interface
======================

Codecrate provides a small CLI with subcommands.

Configuration file
------------------

Codecrate reads configuration from the repository root. It will look for:

* ``.codecrate.toml`` (preferred, if present)
* ``codecrate.toml`` (fallback)
* ``pyproject.toml`` under ``[tool.codecrate]`` (fallback if no codecrate TOML file exists)

Precedence (highest first):

* CLI flags
* ``.codecrate.toml`` / ``codecrate.toml``
* ``pyproject.toml`` ``[tool.codecrate]``

Supported keys include (non-exhaustive):

.. code-block:: toml

   [codecrate]
   output = "context.md"
   include_preset = "python+docs"
   include = ["**/*.py", "**/*.toml", "**/*.rst"]
   exclude = ["tests/**"]
   manifest = true
   profile = "human"
   layout = "auto"
   nav_mode = "auto"
   split_max_chars = 0
   split_strict = false
   split_allow_cut_files = false
   symbol_backend = "auto"
   encoding_errors = "replace"
   security_check = true
   security_content_sniff = false
   security_redaction = false
   safety_report = false
   security_path_patterns = [".env", "*.pem", "*secrets*"]
   security_path_patterns_add = ["*.vault"]
   security_path_patterns_remove = ["*secrets*"]
   security_content_patterns = ["private-key=(?i)-----BEGIN\\s+[A-Z ]*PRIVATE KEY-----"]

   # Token diagnostics (printed to stderr, not added to output markdown)
   token_count_encoding = "o200k_base"
   token_count_tree = false
   token_count_tree_threshold = 0
   top_files_len = 5
   max_file_bytes = 0
   max_total_bytes = 0
   max_file_tokens = 0
   max_total_tokens = 0
   max_workers = 0
   file_summary = true

Overview
--------

.. code-block:: console

   codecrate --version
   codecrate pack [ROOT] [--repo REPO ...] [options]
   codecrate unpack PACK.md -o OUT_DIR [--strict]
   codecrate patch OLD_PACK.md ROOT [-o patch.md]
   codecrate apply PATCH.md ROOT [--check-baseline|--ignore-baseline]
   codecrate validate-pack PACK.md [--root ROOT] [--strict] [policy flags]
   codecrate doctor [ROOT]
   codecrate config show [ROOT] [--effective] [--json]


pack
----

Create a packed Markdown context file from one or more repositories.

.. code-block:: console

   codecrate pack . -o context
   codecrate pack --repo /path/to/repo1 --repo /path/to/repo2 -o multi.md

When using ``--repo``, omit the positional ``ROOT``. Specifying both is an error.

Useful flags:

* ``--dedupe / --no-dedupe``: enable or disable deduplication
   * ``--profile human|agent|hybrid|portable``: choose output defaults profile
   * ``--layout auto|stubs|full``: choose layout (auto selects best token efficiency)
* ``--nav-mode auto|compact|full``: navigation density; auto uses compact for
  unsplit output and full when split outputs are requested
* ``--symbol-backend auto|python|tree-sitter|none``: optional non-Python symbol
  extraction backend (Python files always use AST)
* ``--keep-docstrings / --no-keep-docstrings``: keep docstrings in stubbed views
* ``--manifest / --no-manifest``: include or omit the Manifest section
* ``--respect-gitignore / --no-respect-gitignore``: include ignored files or not
* ``--security-check / --no-security-check``: enable or disable sensitive-file
  safety filtering
* ``--security-content-sniff / --no-security-content-sniff``: optionally scan
  file content for key/token patterns
* ``--security-redaction / --no-security-redaction``: redact flagged files instead
  of skipping them
* ``--safety-report / --no-safety-report``: include Safety Report section in output
* ``--security-path-pattern GLOB`` (repeatable): override sensitive path rule set
* ``--security-path-pattern-add GLOB`` (repeatable): append sensitive path rules
* ``--security-path-pattern-remove GLOB`` (repeatable): remove sensitive path rules
* ``--security-content-pattern RULE`` (repeatable): override sensitive content
  rule set (``name=regex`` or ``regex``)
* ``.codecrateignore``: gitignore-style ignore file in repo root (always respected)
* ``--include GLOB`` (repeatable): include patterns
* ``--include-preset python-only|python+docs|everything``: include preset
* ``--exclude GLOB`` (repeatable): exclude patterns
* ``--stdin``: read file paths from stdin (one per line) instead of scanning
* ``--stdin0``: read file paths from stdin as NUL-separated entries
* ``--print-files``: debug-print selected files after filtering
* ``--print-skipped``: debug-print skipped files and reasons
* ``--print-rules``: debug-print effective include/exclude/ignore/safety rules
* ``--split-max-chars N``: additionally emit ``.index.md`` and ``.partN.md`` files for LLMs
* ``--split-strict / --no-split-strict``: fail instead of writing oversize logical blocks
* ``--split-allow-cut-files / --no-split-allow-cut-files``: explicitly cut oversized
  file blocks across multiple part files
* ``--token-count-tree [threshold]``: show file tree with token counts; optional
  threshold shows only files with >=N tokens (for example,
  ``--token-count-tree 100``)
* ``--top-files-len N``: show N largest files by token count in stderr report
* ``--token-count-encoding NAME``: tokenizer encoding (for tiktoken backend)
* ``--file-summary / --no-file-summary``: enable or disable pack summary output
* ``--max-file-bytes N``: skip files larger than N bytes
* ``--max-total-bytes N``: fail if included files exceed N bytes
* ``--max-file-tokens N``: skip files above N tokens
* ``--max-total-tokens N``: fail if included files exceed N tokens
* ``--max-workers N``: cap thread pool size for IO/parsing/token counting
   * ``--manifest-json [PATH]``: write manifest JSON for tooling (default:
     ``<output>.manifest.json``)
   * ``--index-json [PATH]``: write index JSON for agent/tooling lookup (default:
     ``<output>.index.json``; explicit ``--index-json`` defaults to full mode)
* ``--index-json-mode full|compact|minimal``: choose sidecar mode and enable
  index-json output (``agent`` defaults to ``minimal``; ``hybrid`` defaults to
  ``full``)
* ``--index-json-lookup / --no-index-json-lookup``: include or trim lookup maps
  in compact/minimal v2 sidecars
   * ``--index-json-symbol-index-lines / --no-index-json-symbol-index-lines``:
     include or trim compact v2 symbol index line ranges
   * ``--no-index-json``: disable index JSON output, including profile-implied defaults
   * ``--emit-standalone-unpacker``: write ``<output>.unpack.py`` for zero-install
     reconstruction of manifest-enabled packs
   * ``--encoding-errors replace|strict``: UTF-8 decode policy when reading files
   * ``-o/--output PATH``: output markdown path (defaults to config ``output`` or ``context.md``)

Profile defaults:

* ``human``: current markdown-first behavior
* ``agent``: compact navigation plus minimal v2 ``index-json`` output
* ``hybrid``: current markdown behavior plus full ``index-json`` output
* ``portable``: manifest-enabled ``full`` layout intended for standalone unpack

Portable reconstruction example:

.. code-block:: console

   codecrate pack . -o context.md --profile portable --emit-standalone-unpacker
   python context.unpack.py -o reconstructed/

The emitted script uses only the Python standard library. It supports both
``full`` and ``stubs`` layouts; ``portable`` remains the recommended profile
when you want a reconstruction-first ``full`` pack.

When ``--emit-standalone-unpacker`` is used together with ``--split-max-chars``,
Codecrate still writes the unsplit markdown to the main output path because that
unsplit pack remains the authoritative machine-readable reconstruction source.

``--stdin`` / ``--stdin0`` notes:

* ``--stdin`` accepts one path per line from stdin.
* ``--stdin0`` accepts NUL-separated paths from stdin.
* ``--stdin`` ignores blank lines and lines starting with ``#``.
* Requires a single ``ROOT`` (cannot be combined with ``--repo``).
* Include globs are not applied to explicit stdin files.
* Exclude rules and ignore files still apply.
* Outside-root and missing explicit paths are skipped.
* With ``--print-skipped``, explicit file filtering reports reasons like
  ``not-a-file``, ``outside-root``, ``duplicate``, ``ignored``, and ``excluded``.

Include precedence:

* explicit ``--include``
* explicit ``--include-preset``
* config ``include``
* config ``include_preset``
* built-in default preset (``python+docs``)

Token diagnostics notes:

* Token diagnostics are CLI-only and do not modify generated markdown.
* If ``tiktoken`` is not installed, counting falls back to an approximate method.
* If tokenizer initialization fails, codecrate still reports top-N largest files
  using heuristic counts.
* Safety scanning uses conservative defaults; you can override both path and
  content rule sets.
* With redaction enabled, flagged files remain in output with masked content.
* A compact ``Pack Summary`` (files/tokens/chars/output path) is printed by
  default and can be disabled with ``--no-file-summary`` or
  ``file_summary = false`` in config.
* File code fences are automatically widened when file content contains backticks,
  so generated markdown remains parsable.


unpack
------

Reconstruct files into an output directory:

.. code-block:: console

   codecrate unpack context.md -o /tmp/out

Use ``--strict`` to fail on missing/broken part mappings.
If the input pack omits the Manifest section (for example from
``codecrate pack --no-manifest``), unpack fails with a clear hint to re-pack with
manifest enabled.


patch
-----

Generate a diff-only Markdown patch between an old pack and the current repo:

.. code-block:: console

   codecrate patch old_context.md . -o patch.md

The output is Markdown containing one or more `````diff`` fences.
Patch requires a pack with Manifest; ``--no-manifest`` packs are rejected with a
clear hint.
Patch output includes a ``codecrate-patch-meta`` fence with baseline hashes.


apply
-----

Apply a patch Markdown to a repo root:

.. code-block:: console

   codecrate apply patch.md .
   codecrate apply patch.md . --dry-run
   codecrate apply patch.md . --check-baseline
   codecrate apply patch.md . --ignore-baseline

Use ``--dry-run`` to parse and validate hunks without writing files.
Baseline policy:

* default: verify baseline hashes when metadata is present
* ``--check-baseline``: require metadata and verify
* ``--ignore-baseline``: skip baseline verification


validate-pack
-------------

Validate pack internals (sha/markers/canonical consistency). Optionally compare with
files on disk:

.. code-block:: console

   codecrate validate-pack context.md
   codecrate validate-pack context.md --root .

Use ``--strict`` to treat unresolved marker mapping as validation errors.
Use ``--fail-on-warning`` to turn any warning into a non-zero exit.
Use ``--fail-on-root-drift`` with ``--root`` to fail when disk content differs from the pack.
Use ``--fail-on-redaction`` or ``--fail-on-safety-skip`` for stricter safety policy enforcement.
Validation output groups issues by repository section and includes short hints.
Packs created with ``--no-manifest`` are rejected with a consistent error message.
Use ``--json`` for machine-readable report output.
For an end-to-end agent-oriented usage guide, see :doc:`agent_workflows`.


doctor
------

Inspect configuration and runtime capabilities:

.. code-block:: console

   codecrate doctor .

Doctor reports:

* config discovery and precedence
* selected config source (if any)
* ignore file detection (``.gitignore``, ``.codecrateignore``)
* token backend availability
* optional parsing backend availability (tree-sitter)


config show
-----------

Inspect the resolved configuration for a repository root:

.. code-block:: console

   codecrate config show . --effective
   codecrate config show . --effective --json

The command reports:

* selected config source (or defaults-only)
* effective values after precedence resolution
* full resolved ``security_path_patterns`` list (after add/remove)
* configured ``security_content_patterns`` list
