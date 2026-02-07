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
   include = ["**/*.py", "**/*.toml", "**/*.rst"]
   exclude = ["tests/**"]
   manifest = true
   layout = "auto"
   nav_mode = "auto"
   symbol_backend = "auto"
   encoding_errors = "replace"
   security_check = true
   security_content_sniff = false
   security_redaction = false
   safety_report = false
   security_path_patterns = [".env", "*.pem", "*secrets*"]
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

   codecrate pack [ROOT] [--repo REPO ...] [options]
   codecrate unpack PACK.md -o OUT_DIR [--strict]
   codecrate patch OLD_PACK.md ROOT [-o patch.md]
   codecrate apply PATCH.md ROOT
   codecrate validate-pack PACK.md [--root ROOT] [--strict]
   codecrate doctor [ROOT]


pack
----

Create a packed Markdown context file from one or more repositories.

.. code-block:: console

   codecrate pack . -o context.md
   codecrate pack --repo /path/to/repo1 --repo /path/to/repo2 -o multi.md

When using ``--repo``, omit the positional ``ROOT``. Specifying both is an error.

Useful flags:

* ``--dedupe / --no-dedupe``: enable or disable deduplication
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
* ``--security-content-pattern RULE`` (repeatable): override sensitive content
  rule set (``name=regex`` or ``regex``)
* ``.codecrateignore``: gitignore-style ignore file in repo root (always respected)
* ``--include GLOB`` (repeatable): include patterns
* ``--exclude GLOB`` (repeatable): exclude patterns
* ``--stdin``: read file paths from stdin (one per line) instead of scanning
* ``--stdin0``: read file paths from stdin as NUL-separated entries
* ``--print-files``: debug-print selected files after filtering
* ``--print-skipped``: debug-print skipped files and reasons
* ``--split-max-chars N``: additionally emit ``.partN.md`` files for LLMs
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
* ``--encoding-errors replace|strict``: UTF-8 decode policy when reading files
* ``-o/--output PATH``: output path (defaults to config ``output`` or ``context.md``)

``--stdin`` / ``--stdin0`` notes:

* ``--stdin`` accepts one path per line from stdin.
* ``--stdin0`` accepts NUL-separated paths from stdin.
* ``--stdin`` ignores blank lines and lines starting with ``#``.
* Requires a single ``ROOT`` (cannot be combined with ``--repo``).
* Include globs are not applied to explicit stdin files.
* Exclude rules and ignore files still apply.
* With ``--print-skipped``, explicit file filtering reports reasons like
  ``not-a-file``, ``outside-root``, ``duplicate``, ``ignored``, and ``excluded``.

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

Use ``--strict`` to fail when marker-based reconstruction cannot be fully resolved.
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

Use ``--dry-run`` to parse and validate hunks without writing files.
When baseline metadata is present, apply verifies baseline file hashes and refuses
to apply on mismatch.


validate-pack
-------------

Validate pack internals (sha/markers/canonical consistency). Optionally compare with
files on disk:

.. code-block:: console

   codecrate validate-pack context.md
   codecrate validate-pack context.md --root .

Use ``--strict`` to treat unresolved marker mapping as validation errors.
Validation output groups issues by repository section and includes short hints.
Packs created with ``--no-manifest`` are rejected with a consistent error message.
Use ``--json`` for machine-readable report output.


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
