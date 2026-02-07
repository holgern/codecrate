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
   security_check = true
   security_content_sniff = false

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
   codecrate unpack PACK.md -o OUT_DIR
   codecrate patch OLD_PACK.md ROOT [-o patch.md]
   codecrate apply PATCH.md ROOT
   codecrate validate-pack PACK.md [--root ROOT]


pack
----

Create a packed Markdown context file from one or more repositories.

.. code-block:: console

   codecrate pack . -o context.md
   codecrate pack --repo /path/to/repo1 --repo /path/to/repo2 -o multi.md

When using ``--repo``, omit the positional ``ROOT``. Specifying both is an error.

Useful flags:

* ``--dedupe``: deduplicate identical function bodies
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
* ``.codecrateignore``: gitignore-style ignore file in repo root (always respected)
* ``--include GLOB`` (repeatable): include patterns
* ``--exclude GLOB`` (repeatable): exclude patterns
* ``--stdin``: read file paths from stdin (one per line) instead of scanning
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
* ``-o/--output PATH``: output path (defaults to config ``output`` or ``context.md``)

``--stdin`` notes:

* Accepts one path per line from stdin.
* Blank lines and lines starting with ``#`` are ignored.
* Requires a single ``ROOT`` (cannot be combined with ``--repo``).
* Include globs are not applied to explicit stdin files.
* Exclude rules and ignore files still apply.

Token diagnostics notes:

* Token diagnostics are CLI-only and do not modify generated markdown.
* If ``tiktoken`` is not installed, counting falls back to an approximate method.
* If tokenizer initialization fails, codecrate still reports top-N largest files
  using heuristic counts.
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


patch
-----

Generate a diff-only Markdown patch between an old pack and the current repo:

.. code-block:: console

   codecrate patch old_context.md . -o patch.md

The output is Markdown containing one or more `````diff`` fences.


apply
-----

Apply a patch Markdown to a repo root:

.. code-block:: console

   codecrate apply patch.md .


validate-pack
-------------

Validate pack internals (sha/markers/canonical consistency). Optionally compare with
files on disk:

.. code-block:: console

   codecrate validate-pack context.md
   codecrate validate-pack context.md --root .
