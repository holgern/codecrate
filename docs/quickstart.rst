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

Pack multiple repositories into a single output:

.. code-block:: console

   codecrate pack --repo /path/to/repo1 --repo /path/to/repo2 -o multi.md

Common options:

* ``--dedupe``: deduplicate identical function bodies (enables stub layout when effective)
* ``--layout {auto,stubs,full}``: control output layout
* ``--manifest/--no-manifest``: include or omit the Manifest section (omit only for LLM-only packs)
* ``--split-max-chars N``: keep the main output unsplit, and additionally emit ``.partN.md`` files for LLMs


Unpack a context pack
---------------------

Reconstruct files from a pack into a directory:

.. code-block:: console

   codecrate unpack context.md -o /tmp/reconstructed


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


Validate a context pack
-----------------------

Validate internal consistency (and optionally compare against a repo on disk):

.. code-block:: console

   codecrate validate-pack context.md
   codecrate validate-pack context.md --root /path/to/repo
