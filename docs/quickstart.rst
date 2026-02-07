Quickstart
==========

Configuration
-------------

Codecrate reads configuration from the repository root. It will look for:

* ``.codecrate.toml`` (preferred, if present)
* ``codecrate.toml`` (fallback)
* ``pyproject.toml`` under ``[tool.codecrate]`` (fallback if no codecrate TOML file exists)

Precedence (highest first):

* CLI flags
* ``.codecrate.toml`` / ``codecrate.toml``
* ``pyproject.toml`` ``[tool.codecrate]``

Example:

.. code-block:: toml

   [codecrate]
   output = "context.md"
   security_check = true
   security_content_sniff = false
   symbol_backend = "auto"
   max_file_bytes = 0
   max_total_bytes = 0
   max_file_tokens = 0
   max_total_tokens = 0
   max_workers = 0

Installation
------------

From source (recommended while iterating):

.. code-block:: console

   pip install -e .

If you build docs locally, install doc deps too (example):

.. code-block:: console

   pip install -U sphinx sphinx-rtd-theme


Create a context pack
---------------------

Pack a repository into ``context.md``:

.. code-block:: console

   codecrate pack /path/to/repo -o context.md
   codecrate pack /path/to/repo -o context.md --manifest-json

Pack multiple repositories into a single output:

.. code-block:: console

   codecrate pack --repo /path/to/repo1 --repo /path/to/repo2 -o multi.md

Common options:

* ``--dedupe``: deduplicate identical function bodies (enables stub layout when effective)
* ``--layout {auto,stubs,full}``: control output layout
* ``--manifest/--no-manifest``: include or omit the Manifest section (omit only for LLM-only packs)
* ``--split-max-chars N``: keep the main output unsplit, and additionally emit ``.partN.md`` files for LLMs
* ``--max-file-bytes`` / ``--max-file-tokens``: skip oversized single files with a warning
* ``--max-total-bytes`` / ``--max-total-tokens``: fail fast when total included size exceeds budget
* ``--security-redaction``: mask flagged files instead of skipping
* ``--safety-report``: include a Safety Report section with reasons
* ``--stdin`` / ``--stdin0``: pack an explicit file list from stdin
* ``--print-files`` / ``--print-skipped``: debug selected and skipped files
* ``--print-rules``: debug-print effective include/exclude/ignore/safety rules
* ``--include-preset``: switch between ``python-only``, ``python+docs``, and ``everything``
* ``--encoding-errors {replace,strict}``: UTF-8 decode policy while reading files


Unpack a context pack
---------------------

Reconstruct files from a pack into a directory:

.. code-block:: console

   codecrate unpack context.md -o /tmp/reconstructed
   codecrate unpack context.md -o /tmp/reconstructed --strict

.. note::

   Packs created with ``--no-manifest`` are LLM-only and cannot be used for
   ``unpack``, ``patch``, or ``validate-pack``.


Generate a patch Markdown
-------------------------

Given an older pack as baseline and a current repo root, generate a diff-only patch:

.. code-block:: console

   codecrate patch old_context.md /path/to/repo -o patch.md


Apply a patch Markdown
----------------------

Apply the patch to a repo:

.. code-block:: console

   codecrate apply patch.md /path/to/repo
   codecrate apply patch.md /path/to/repo --dry-run
   codecrate apply patch.md /path/to/repo --check-baseline
   codecrate apply patch.md /path/to/repo --ignore-baseline

Apply validates baseline metadata embedded in generated patches and refuses to
apply when baseline file hashes do not match.

Use ``--check-baseline`` to require metadata and ``--ignore-baseline`` to skip
baseline verification.


Validate a context pack
-----------------------

Validate internal consistency (and optionally compare against a repo on disk):

.. code-block:: console

   codecrate validate-pack context.md
   codecrate validate-pack context.md --root /path/to/repo
   codecrate validate-pack context.md --strict
   codecrate validate-pack context.md --json


Doctor checks
-------------

Inspect config precedence, ignore files, and backend availability:

.. code-block:: console

   codecrate --version
   codecrate doctor /path/to/repo
