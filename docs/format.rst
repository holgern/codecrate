Pack Format
===========

Codecrate outputs a single Markdown file. When ``--split-max-chars`` is used,
it also emits additional ``.partN.md`` files intended for LLM consumption
containing enough information to:

* browse code quickly (directory tree + symbol index)
* reconstruct original files (full layout) or via stubs + canonical sources (stub layout)


High-level structure
--------------------

A typical pack includes:

* **How to Use This Pack**: reading guidance for LLMs
* **Machine Header**: compact metadata in a ``codecrate-machine-header`` fence
* **Manifest (optional)**: machine-readable metadata in a ``codecrate-manifest`` fence
* **Safety Report (optional)**: skipped/redacted files and reasons
* **Directory Tree**: a simple text tree of files
* **Symbol Index**: per-file symbol list with line ranges
* **Function Library** (stub layout only): canonical function bodies keyed by ID
* **Files**: full file content (full layout) or stubbed files (stub layout)

The Manifest is required for machine operations (unpack/patch/validate-pack). For token
efficiency, split ``.partN.md`` files omit it, and you can disable it entirely with
``--no-manifest`` (LLM-only packs).

Manifest metadata also records explicit ID/marker schemes for forward compatibility:

* ``id_format_version`` (currently ``sha1-8-upper:v1``)
* ``marker_format_version`` (currently ``v1``)
* per-definition ``has_marker`` hints in stub layouts (for validation accuracy)

Machine Header includes:

* ``format``
* ``repo_label`` / ``repo_slug``
* ``manifest_sha256``

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

   ...  # ↪ FUNC:v1:XXXXXXXX

The marker references the function definition occurrence. During unpack, Codecrate
locates the marker, finds the ``def`` line above it (including decorators), and
replaces that region with the canonical function body from the Function Library.

When binary files are detected during packing, they are skipped and reported as
``Skipped as binary: N file(s)`` in the pack header and Safety Report (when enabled).


Line ranges
-----------

The Symbol Index can include markdown line ranges ``(Lx-y)`` that refer to line numbers inside the packed Markdown file itself.

When a pack is split into ``.partN.md`` files, these markdown line ranges are omitted in the split parts because they are not stable across files.
Use the per-part links (e.g. ``context.part3.md#src-...`` / ``#func-...``)
nstead.
