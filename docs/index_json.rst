Index JSON Sidecar
==================

``codecrate.index-json.v1`` is the machine-facing companion to the Markdown
pack. The Markdown output stays optimized for human reading, patch/apply, and
round-trip reconstruction; the sidecar exists so tools can answer common
retrieval questions without scraping markdown.


Generation
----------

Generate the sidecar explicitly:

.. code-block:: console

   codecrate pack . -o context.md --index-json

Or let the profile enable it:

.. code-block:: console

   codecrate pack . -o context.md --profile agent
   codecrate pack . -o context.md --profile hybrid

By default, the sidecar is written next to the markdown output as
``<output>.index.json``.


Contract and compatibility
--------------------------

The sidecar is versioned independently as ``codecrate.index-json.v1``.

Compatibility rules for v1:

* existing fields are preserved
* new metadata is added additively
* machine-facing lookups should prefer explicit IDs and lookup maps over
  markdown scraping

The pack and sidecar are generated from the same export model, so repository,
file, symbol, and split-part metadata describe the markdown that was actually
written.


Top-level shape
---------------

The payload has this high-level structure:

.. code-block:: json

   {
     "format": "codecrate.index-json.v1",
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

``markdown_path``
   Present for unsplit output; ``null`` for split output.

``has_manifest`` / ``has_machine_header``
   Trust and round-trip signals for machine consumers.

``parts``
   Metadata for the emitted markdown files belonging to the repository.

``files``
   File-level retrieval, integrity, language, and location metadata.

``symbols``
   Symbol-level occurrence and canonical-body metadata.

``lookup``
   Reverse indexes for direct access by path or ID.


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
   Declares whether source anchors, index anchors, unsplit line ranges, and
   part-relative line ranges are available.

``markdown_lines``
   Unsplit line range for the file section when line ranges are available.

``language`` / ``fence_language`` / ``language_family``
   Rendering and retrieval-oriented language metadata.

``sha256_original`` / ``sha256_stubbed`` / ``sha256_effective``
   Integrity hashes for original file content, stubbed content, and the actual
   packed body.

``sizes``
   Character, byte, and token estimates for original and effective file bodies.

``symbol_ids`` / ``display_symbol_ids`` / ``symbol_canonical_ids``
   Direct symbol membership for the file.


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
   Same locator-availability contract used by file entries.


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


Locator semantics
-----------------

Locator fields are intended to be truthful with respect to the emitted markdown.

In unsplit output:

* anchor hrefs are available
* line ranges are also available
* compact navigation still preserves machine-targetable anchors

In split output:

* hrefs still point to the actual ``.index.md`` or ``.partN.md`` file
* unsplit line ranges are omitted
* consumers should follow ``part_path`` and hrefs instead of assuming a single
  markdown file

If a locator field is present, it should resolve against the written output.


Validation helper
-----------------

``codecrate.validate_index_json.validate_index_payload()`` validates internal
sidecar consistency.

It checks:

* output file existence when a base directory is provided
* href targets and anchor existence
* part/file/symbol cross references
* line-range validity
* lookup map consistency

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
