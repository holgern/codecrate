Pack Format
===========

Codecrate outputs a single Markdown file. When ``--split-max-chars`` is used,
it can also emit ``.index.md`` and ``.partN.md`` files intended for LLM
consumption containing enough information to:

* browse code quickly (directory tree + symbol index)
* reconstruct original files (full layout) or via stubs + canonical sources (stub layout)


High-level structure
--------------------

A typical pack includes:

* **How to Use This Pack**: reading guidance for LLMs
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

Codecrate can also emit JSON sidecars:

* ``codecrate.manifest-json.v1``: manifest-focused tooling export
* ``codecrate.index-json.v1``: retrieval-oriented file/symbol/part index for agents and tools

See :doc:`index_json` for the detailed sidecar contract.

Profiles can change output defaults without changing the underlying pack format:

* ``human`` keeps current markdown-first behavior
* ``agent`` implies compact navigation and minimal v2 index JSON output
* ``hybrid`` keeps current markdown behavior and also emits index JSON output

The index sidecar includes deterministic per-repository metadata for:

* emitted markdown part files
* file-to-part lookup
* symbol-to-file and symbol-to-canonical-body lookup
* direct href-style links for file and symbol navigation
* unsplit markdown line ranges for file sections, symbol index entries, and canonical bodies
* explicit reverse lookup indexes for files and symbols
* part character and token estimates
* part oversize status and effective split policy
* safety findings
* per-file language detection and symbol extraction backend/status reporting

Split part membership is captured directly during split generation rather than
recovered later by reparsing emitted markdown.

For non-Python files, the index sidecar reports:

* ``language_detected``
* ``symbol_backend_requested``
* ``symbol_backend_used``
* ``symbol_extraction_status``

This makes it explicit whether symbol extraction was unavailable, disabled,
unsupported for the file type, or completed successfully.

The index sidecar also separates human-facing and machine-facing identifiers:

* ``display_id`` / ``display_local_id`` keep the current short pack IDs used by markdown anchors
* ``canonical_id`` / ``local_id`` use stronger SHA-256 based machine IDs for tooling
* ``display_id_format_version`` and ``canonical_id_format_version`` record both schemes explicitly

Per-file entries also include lightweight review metadata such as byte, character,
and token estimates for both original and effective packed content.

Machine Header includes:

* ``format``
* ``repo_label`` / ``repo_slug``
* ``manifest_sha256``


Protocol constants
------------------

* pack format: ``codecrate.v4``
* patch metadata format: ``codecrate.patch.v1``
* manifest-json format: ``codecrate.manifest-json.v1``
* index-json format: ``codecrate.index-json.v1``
* machine header fence: ``codecrate-machine-header``
* manifest fence: ``codecrate-manifest``
* patch metadata fence: ``codecrate-patch-meta``

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


Patch metadata
--------------

Generated patch markdown includes a ``codecrate-patch-meta`` fence with:

* patch format id (``codecrate.patch.v1``)
* baseline manifest checksum
* baseline per-file original checksums

``apply`` uses this metadata to verify that baseline files still match before
applying hunks.


Determinism
-----------

Pack ordering is deterministic by normalized relative path and stable id order.
Split outputs preserve deterministic section/file/function ordering and avoid
splitting inside fenced code blocks.

When a single logical block exceeds ``--split-max-chars``, Codecrate keeps it
intact in an oversize part by default. Use ``--split-strict`` to fail instead,
or ``--split-allow-cut-files`` to explicitly cut oversized file blocks across
multiple parts.

When binary files are detected during packing, they are skipped and reported as
``Skipped as binary: N file(s)`` in the pack header and Safety Report (when enabled).


Line ranges
-----------

The Symbol Index can include markdown line ranges ``(Lx-y)`` that refer to line numbers
inside the packed Markdown file itself.

When a pack is split into ``.partN.md`` files, these markdown line ranges are omitted in
the split parts because they are not stable across files. Use the per-part links
instead (for example ``context.part3.md#src-...`` / ``#func-...``).
