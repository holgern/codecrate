Pack Format
===========

Codecrate outputs a single Markdown file (or multiple ``.partN.md`` files when split)
containing enough information to:

* browse code quickly (directory tree + symbol index)
* reconstruct original files (full layout) or via stubs + canonical sources (stub layout)


High-level structure
--------------------

A typical pack includes:

* **How to Use This Pack**: reading guidance for LLMs
* **Manifest**: machine-readable metadata in a ``codecrate-manifest`` fence
* **Directory Tree**: a simple text tree of files
* **Symbol Index**: per-file symbol list with line ranges
* **Function Library** (stub layout only): canonical function bodies keyed by ID
* **Files**: full file content (full layout) or stubbed files (stub layout)


Layouts
-------

``full``
   The pack includes full file contents under **Files**. The manifest is minimal and
   does not include function metadata.

``stubs``
   The pack includes stubbed file contents under **Files** and a **Function Library**
   with canonical function bodies.

``auto``
   Chooses ``stubs`` only when deduplication actually collapses something; otherwise
   chooses ``full`` for best token efficiency.


IDs and deduplication
---------------------

In stub layout, Codecrate distinguishes:

``local_id``
   Unique per definition occurrence (stable by file path + qualname + def line).

``id``
   Canonical body ID. When dedupe is enabled and identical bodies are detected,
   multiple ``local_id`` values may share the same canonical ``id``.


Stub markers
------------

Stubbed file bodies contain markers like:

.. code-block:: text

   ...  # ↪ FUNC:XXXXXXXX

The marker references the function definition occurrence. During unpack, Codecrate
locates the marker, finds the ``def`` line above it (including decorators), and
replaces that region with the canonical function body from the Function Library.


Line ranges
-----------

The Symbol Index contains line ranges ``(Lx-y)`` that refer to line numbers inside the
packed Markdown file itself. These ranges are intended to make it easy to jump to a
definition without needing external tools.
