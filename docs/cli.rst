Command Line Interface
======================

Codecrate provides a small CLI with subcommands.

Configuration file
------------------

Codecrate reads configuration from the repository root. It will look for:

* ``.codecrate.toml`` (preferred, if present)
* ``codecrate.toml`` (fallback)

Supported keys include (non-exhaustive):

.. code-block:: toml

   [codecrate]
   output = "context.md"
   include = ["**/*.py", "**/*.toml", "**/*.rst"]
   exclude = ["tests/**"]
   manifest = true

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
* ``--keep-docstrings / --no-keep-docstrings``: keep docstrings in stubbed views
* ``--manifest / --no-manifest``: include or omit the Manifest section (required for unpack/patch/validate-pack)
* ``--respect-gitignore / --no-respect-gitignore``: include ignored files or not
* ``--include GLOB`` (repeatable): include patterns
* ``--exclude GLOB`` (repeatable): exclude patterns
* ``--split-max-chars N``: additionally emit ``.partN.md`` files for LLMs (the
  main output stays unsplit). For multi-repo packs, parts are named
  ``output.<repo>.partN.md``
* ``-o/--output PATH``: output path (defaults to config ``output`` or ``context.md``)


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
   codecrate validate-pack context.md --root .Command Line Interface
======================

Codecrate provides a small CLI with subcommands.

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
* ``--keep-docstrings / --no-keep-docstrings``: keep docstrings in stubbed views
* ``--respect-gitignore / --no-respect-gitignore``: include ignored files or not
* ``--include GLOB`` (repeatable): include patterns
* ``--exclude GLOB`` (repeatable): exclude patterns
* ``--split-max-chars N``: additionally emit ``.partN.md`` files for LLMs (the
  main output stays unsplit). For multi-repo packs, parts are named
  ``output.<repo>.partN.md``


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
