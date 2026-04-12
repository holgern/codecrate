Index JSON Sidecar
==================

``index-json`` is the machine-facing companion to the Markdown pack. The
Markdown output stays optimized for human reading, patch/apply, and round-trip
reconstruction; the sidecar exists so tools can answer common retrieval
questions without scraping markdown.


Generation
----------

Generate the sidecar explicitly:

.. code-block:: console

   codecrate pack . -o context.md --index-json

Or let the profile enable it:

.. code-block:: console

   codecrate pack . -o context.md --profile agent
   codecrate pack . -o context.md --profile lean-agent
   codecrate pack . -o context.md --profile hybrid

``--profile agent`` resolves to the normalized v3 sidecar by default, while
``--profile lean-agent`` keeps normalized v3 but trims analysis-heavy payloads
and pretty-print whitespace by default, while ``--profile hybrid`` keeps the
full v1-compatible sidecar.

Or choose a specific sidecar mode:

.. code-block:: console

   codecrate pack . -o context.md --index-json-mode compact
   codecrate pack . -o context.md --index-json-mode minimal
   codecrate pack . -o context.md --index-json-mode normalized
   codecrate pack . -o context.md --index-json-mode minimal --locator-space dual

``--index-json`` alone defaults to the full compatibility surface. Use
``--index-json-mode compact``, ``--index-json-mode minimal``, or
``--index-json-mode normalized`` when you want a machine-first sidecar
explicitly.

Use ``normalized`` for the smallest recommended sidecar in agent workflows.
Use ``minimal`` for the smallest v2-compatible sidecar.

By default, the sidecar is written next to the markdown output as
``<output>.index.json``.


Contract and compatibility
--------------------------

The sidecar is versioned independently:

* ``codecrate.index-json.v1``: full sidecar surface
* ``codecrate.index-json.v2``: compact or minimal sidecar surface
* ``codecrate.index-json.v3``: normalized sidecar surface

The top-level ``mode`` field distinguishes ``full``, ``compact``, and
``minimal``, and ``normalized`` output.

Compatibility rules:

* v1 remains the full-fidelity compatibility surface
* v2 is a machine-first retrieval surface that removes redundant display and
  reverse-index duplication by default
* v3 is the most compact analysis-oriented surface and interns repeated paths,
  qualnames, and strings into shared tables
* machine-facing lookups should prefer explicit IDs and lookup maps over
  markdown scraping

The pack and sidecar are generated from the same export model, so repository,
file, symbol, and split-part metadata describe the markdown that was actually
written.

Locator targets are configurable independently from sidecar mode:

* ``--locator-space markdown`` keeps locators pointed at the markdown pack
* ``--locator-space reconstructed`` points locators at the reconstructed file tree
* ``--locator-space dual`` emits both families
* ``--locator-space auto`` resolves to ``reconstructed`` when
  ``--emit-standalone-unpacker`` is enabled and otherwise to ``markdown``


Top-level shape
---------------

The payload has this high-level structure:

.. code-block:: json

    {
      "format": "codecrate.index-json.v3",
      "mode": "normalized",
      "pack": { ... },
      "repositories": [ ... ]
    }

``pack``
   Global metadata about the emitted artifact set.

``repositories``
   Per-repository entries for both single-repo and multi-repo output.


Pack metadata
-------------

Useful ``pack`` fields include:

``index_json_mode``
   The resolved sidecar mode used for the emitted payload.

``format``
   The markdown pack protocol version.

``is_split``
   Whether markdown was emitted as a single pack or as ``.index.md`` plus
   ``.partN.md`` files.

``output_files``
   Relative paths to all emitted markdown files.

``display_id_format_version`` / ``canonical_id_format_version``
   Explicit ID schemes for display IDs and machine IDs.

``capabilities``
   Boolean feature flags such as manifest availability and whether unsplit line
   ranges are available.

``authority``
   Declares which artifact is authoritative for full layout, stub layout, and
   patch flows.


Repository metadata
-------------------

Each entry in ``repositories[]`` describes one packed repository.

Useful fields include:

``label`` / ``slug``
   Human-facing and path-safe repository identifiers.

``layout`` / ``effective_layout``
   Requested and resolved layout behavior.

``nav_mode``
   The actual navigation density reflected in the rendered markdown.

``locator_mode``
   How direct locators should be interpreted:

   * ``anchors+line-ranges`` for unsplit markdown
   * ``anchors`` for split output

``locator_space`` / ``secondary_locator_space``
   The primary machine-facing locator family, plus an optional secondary family
   when both markdown and reconstructed locators are emitted.

``reconstructed_root``
   Present for combined multi-repo packs when reconstructed locators are
   enabled. Reconstructed paths are relative to the unpack output root, so
   combined packs use ``<slug>/...`` paths.

``markdown_path``
   Present for unsplit output; ``null`` for split output.

``has_manifest`` / ``has_machine_header``
   Trust and round-trip signals for machine consumers.

``parts``
   Metadata for the emitted markdown files belonging to the repository.

``index_json_features``
   Declares optional v2 retrieval families such as lookup-map emission and
   compact symbol index lines.

``files``
    File-level retrieval, integrity, language, and location metadata.

``symbols``
   Symbol-level occurrence and canonical-body metadata.

``lookup``
     Reverse indexes for direct access by path or ID.

``graph`` / ``test_links`` / ``guide``
    Optional analysis metadata: import edges, heuristic test coupling, and a
    repository guide.


Mode summary
------------

``full`` (v1)
   Preserves the current compatibility surface, including display IDs, richer
   file and symbol metadata, and the larger reverse lookup set.

``compact`` (v2)
   Keeps machine-first retrieval with direct file and symbol navigation while
   dropping display-oriented duplication and heavyweight membership metadata.
   When ``index_json_features.lookup`` is true, the lookup maps are:

   * ``file_by_path``
   * ``part_by_file``
   * ``file_by_symbol``
   * ``symbol_by_local_id``

``minimal`` (v2)
   Starts from compact mode and trims additional convenience duplication.
   It is the smallest v2-compatible sidecar surface rather than the smallest
   overall sidecar. When ``index_json_features.lookup`` is true, the lookup
   maps are:

   * ``file_by_path``
   * ``symbol_by_local_id``

``normalized`` (v3)
   Interns repeated strings into ``repositories[].tables`` and replaces
   path/module/qualname references with integer indexes. It keeps the same
   machine-facing essentials as the richer modes while omitting markdown href
   duplication and v2 lookup maps.


Analysis metadata
-----------------

When analysis metadata is enabled, the sidecar also exposes:

* ``repositories[].classes[]`` with first-class class entries
* ``repositories[].files[].imports``
* ``repositories[].files[].exports``
* ``repositories[].files[].module_docstring_lines``
* ``repositories[].files[].role_hint``
* ``repositories[].symbols[].owner_class``
* ``repositories[].symbols[].decorators``
* ``repositories[].graph.import_edges``
* ``repositories[].test_links``
* ``repositories[].guide``

Use ``--no-analysis-metadata`` when you want a smaller sidecar and do not need
those architecture-oriented hints.

``--profile lean-agent`` applies that smaller-sidecar posture by default and
also minifies the JSON payload unless you opt back into ``--index-json-pretty``.


Part metadata
-------------

``repositories[].parts[]`` records the markdown files that contain repository
content.

Useful fields include:

``part_id``
   Stable repository-scoped identifier such as ``repo:pack`` or ``repo:part3``.

``path`` / ``kind``
   Relative output path and whether the part is the unsplit pack, split index,
   or a split content part.

``char_count`` / ``line_count`` / ``token_estimate``
   Lightweight sizing information for retrieval and UI decisions.

``sha256_content``
   Integrity hash of the emitted markdown file content.

``contains``
   Precomputed membership lists for file paths, canonical IDs, display
   canonical IDs, and section types contained in the part.


File metadata
-------------

``repositories[].files[]`` is the main entrypoint for locating source files in
the emitted markdown.

Useful fields include:

``path`` / ``module``
   Repository-relative file path and Python module name when applicable.

``part_path`` / ``markdown_path``
   Output file holding the file body and the unsplit pack path when present.

``hrefs`` / ``anchors``
   Direct markdown targets for the file index entry and source body.

``locators``
   Locator metadata for the file entry. In v1 payloads this still includes the
   legacy availability booleans plus ``markdown`` and/or ``reconstructed``
   locator objects. In v2 payloads it carries the locator objects directly.

``markdown_lines``
   Unsplit line range for the file section when line ranges are available.

``language`` / ``fence_language`` / ``language_family``
   Rendering and retrieval-oriented language metadata.

``sha256_original`` / ``sha256_stubbed`` / ``sha256_effective``
   Integrity hashes for original file content, stubbed content, and the actual
   packed body.

``sizes``
   Character, byte, and token estimates for original and effective file bodies.

``summary.summary_text``
   Deterministic short prose describing the file's role and primary symbols.

``symbol_ids`` / ``display_symbol_ids`` / ``symbol_canonical_ids``
   Direct symbol membership for the file.

In normalized v3 payloads, file entries instead use indexed fields such as
``p`` (path), ``part`` (part path), ``lang`` (language), ``mod`` (module), and
optional analysis fields like ``imp`` (imports), ``exp`` (exports), ``doc``
(``[start_line, end_line]``), ``role``, and ``sum.st`` (summary text).


Symbol metadata
---------------

``repositories[].symbols[]`` provides both occurrence-level and canonical-body
metadata.

Useful fields include:

``display_id`` / ``display_local_id``
   Short markdown-facing IDs.

``canonical_id`` / ``local_id``
   Machine-facing SHA-256 based IDs.

``ids``
   Nested alias object containing both display and machine IDs.

``path`` / ``qualname`` / ``kind`` / ``def_line``
   Source identity and location.

``file_part`` / ``file_href`` / ``file_anchor``
   Direct location of the file body containing the symbol occurrence.

``canonical_part`` / ``canonical_href`` / ``canonical_anchor``
   Canonical function-library location for stub layout.

``index_markdown_lines`` / ``file_markdown_lines`` / ``canonical_markdown_lines``
   Unsplit markdown line ranges when available.

``occurrence_count_for_canonical_id``
   Number of source occurrences sharing the same canonical body.

``locators``
   Symbol locator metadata. ``markdown`` can include file, symbol-index, and
   canonical markdown ranges; ``reconstructed`` points at the reconstructed file
   span and body span.

``purpose_text``
   Deterministic short prose summarizing the symbol's role, ownership, and
   signature hints.

In normalized v3 payloads, symbol entries use compact indexed fields such as
``i`` (local machine ID), ``c`` (canonical machine ID when needed), ``p`` (path
 index), ``q`` (qualname index), ``k`` (kind index), ``l1`` / ``l2`` (line
 range), plus optional ``o`` (owner class ID), ``d`` (decorator indexes), and
 ``pt`` (purpose-text index).


Lookup maps
-----------

Use ``repositories[].lookup`` when you need constant-shape access instead of
scanning arrays.

Useful maps include:

``file_by_path``
   Path to a compact file summary with part and href metadata.

``part_by_file``
   Path to the emitted markdown file containing that file body.

``symbols_by_file`` / ``display_symbols_by_file``
   File-to-symbol membership by machine or display IDs.

``file_by_symbol`` / ``file_by_display_symbol``
   Symbol-to-file reverse indexes.

``symbol_by_local_id`` / ``symbol_by_display_local_id``
   Direct symbol entry lookup by occurrence ID.

``symbols_by_canonical_id`` / ``symbols_by_display_id``
   Grouped symbol entries for canonical-body lookups.

In v2 payloads, check ``repositories[].index_json_features`` first. If
``lookup`` is false, consumers should scan ``files[]`` and ``symbols[]``
directly instead of assuming ``lookup`` is present. If
``symbol_index_lines`` is false, compact payloads intentionally omit
``index_markdown_lines`` even for unsplit packs.

Normalized v3 payloads intentionally do not include the v2 lookup maps. Use the
intern tables plus ``files[]``, ``classes[]``, ``symbols[]``, and the optional
analysis sections directly.


Locator semantics
-----------------

Locator fields are intended to be truthful with respect to the emitted markdown.

In unsplit output:

* anchor hrefs are available
* line ranges are also available
* compact navigation still preserves machine-targetable anchors
* ``locator_space = markdown`` points ``locators.markdown`` into ``context.md``

In split output:

* hrefs still point to the actual ``.index.md`` or ``.partN.md`` file
* unsplit line ranges are omitted
* consumers should follow ``part_path`` and hrefs instead of assuming a single
  markdown file

When ``--emit-standalone-unpacker`` is enabled:

* ``locator_space = auto`` resolves to reconstructed locators
* file and symbol ``locators.reconstructed`` point at the unpacked file tree
* combined multi-repo packs prefix reconstructed paths with the repository slug

If a locator field is present, it should resolve against the written output.


Validation helper
-----------------

``codecrate.validate_index_json.validate_index_payload()`` validates internal
sidecar consistency.

It checks:

* output file existence when a base directory is provided
* href targets and anchor existence for v1/v2 payloads
* part/file/symbol cross references
* line-range validity
* lookup map consistency for v1/v2 payloads
* normalized-table index validity for v3 payloads

Example:

.. code-block:: python

   import json
   from pathlib import Path

   from codecrate.validate_index_json import validate_index_payload

   payload = json.loads(Path("context.index.json").read_text(encoding="utf-8"))
   errors = validate_index_payload(payload, base_dir=Path("."))
   if errors:
       raise SystemExit("\n".join(errors))


Consumer guidance
-----------------

For most tooling:

1. start with ``repositories[].lookup`` when you already know a path or ID
2. use ``repositories[].files[]`` to locate the rendered file body
3. use ``repositories[].symbols[]`` when symbol identity or canonical bodies
   matter
4. use ``repositories[].parts[]`` to drive split-output retrieval UIs

Prefer machine IDs for stable automation and display IDs only when you need to
match existing markdown anchors or present short identifiers to users.
