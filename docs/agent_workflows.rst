Agent Workflows
===============

Codecrate can be used as a human-readable markdown exporter, but the current
pack and sidecar output is also intended to support coding-agent workflows.

This page focuses on how to use Codecrate when an agent needs to read,
retrieve, validate, diff, and apply changes safely.


Choose A Profile
----------------

Codecrate supports three output profiles:

* ``human``: keep the current markdown-first behavior
* ``agent``: compact navigation, manifest enabled, and ``index-json`` enabled
* ``hybrid``: current markdown richness plus ``index-json`` output

Example:

.. code-block:: console

   codecrate pack . -o context.md --profile agent

Explicit CLI flags still override profile defaults. For example, this keeps the
``agent`` profile but turns file-level navigation back on and disables the
index sidecar:

.. code-block:: console

   codecrate pack . -o context.md --profile agent --nav-mode full --no-index-json


Authority Model
---------------

Agents should treat different outputs as authoritative for different tasks.

``full`` layout
   The authoritative content is the file body under ``## Files``.

``stubs`` layout
   The authoritative reconstruction is the stubbed file body plus canonical
   bodies from ``## Function Library`` plus the Manifest mapping.

Patch flow
   The authoritative change representation is the unified diff inside patch
   markdown.

In practice:

* use ``full`` packs when you want one obvious file body per source file
* use ``stubs`` packs when token efficiency matters and your tool understands
  canonical function bodies
* use patch/apply when you want baseline-aware edit loops instead of directly
  rewriting packed markdown


Use The Index Sidecar
---------------------

``codecrate.index-json.v1`` is the main retrieval sidecar for tools and agents.
See :doc:`index_json` for the full sidecar contract and field guide.

Generate it directly:

.. code-block:: console

   codecrate pack . -o context.md --index-json

Or let the profile imply it:

.. code-block:: console

   codecrate pack . -o context.md --profile hybrid

The sidecar includes:

* per-repository metadata
* split part metadata
* file-to-part lookup
* symbol-to-file lookup
* symbol-to-canonical-body lookup in stub layout
* direct href-style navigation fields
* reverse lookup indexes
* unsplit markdown line ranges for review-oriented jumps
* safety findings
* language and backend reporting
* short display IDs and stronger machine IDs

Useful fields to inspect first:

* ``pack.output_files``
* ``repositories[].parts``
* ``repositories[].files``
* ``repositories[].symbols``


Locate Files And Symbols
------------------------

The index sidecar is designed so a tool does not need to scrape markdown to
answer common lookup questions.

Locate a file and its markdown part:

.. code-block:: console

   codecrate pack . -o context.md --index-json

Then inspect ``repositories[].files[]`` for:

* ``path``
* ``part_path``
* ``hrefs.index`` / ``hrefs.source``
* ``anchors.index``
* ``anchors.source``
* ``markdown_lines`` on unsplit packs

Locate a symbol and its canonical body in stub layout:

.. code-block:: console

   codecrate pack . -o context.md --layout stubs --index-json

Then inspect ``repositories[].symbols[]`` for:

* ``display_id`` / ``display_local_id``
* ``canonical_id`` / ``local_id``
* ``file_part``
* ``file_href``
* ``file_anchor``
* ``canonical_part``
* ``canonical_href``
* ``canonical_anchor``
* ``index_markdown_lines`` on unsplit packs
* ``canonical_markdown_lines`` on unsplit stub packs

If you need explicit reverse indexes instead of scanning arrays, inspect
``repositories[].lookup`` for:

* ``symbols_by_file``
* ``display_symbols_by_file``
* ``file_by_symbol``
* ``file_by_display_symbol``


Understand Split Output
-----------------------

When ``--split-max-chars`` is used, Codecrate can emit:

* ``context.index.md``
* ``context.partN.md`` files

Split output is intended for reading and retrieval, while the unsplit markdown
remains the machine-readable source for unpack and validate flows.

Split policy is explicit:

* default preserve behavior: keep an oversize logical block intact in an oversize part
* ``--split-strict``: fail if a logical block exceeds the limit
* ``--split-allow-cut-files``: explicitly cut oversize file blocks across parts

The sidecar records both the effective split policy and whether a specific part
is oversize.

Example:

.. code-block:: console

   codecrate pack . -o context.md --split-max-chars 20000 --split-allow-cut-files --index-json

Then inspect ``repositories[].parts[]`` for:

* ``kind``
* ``char_count``
* ``token_estimate``
* ``is_oversized``
* ``contains.files``
* ``contains.canonical_ids``

For review-oriented tooling, per-file entries also include packed size metadata:

* ``sizes.original``
* ``sizes.effective``


Check Safety And Trust Signals
------------------------------

Agent workflows often need to know whether a pack is safe to use for automated
editing.

The sidecar reports:

* ``repositories[].safety.skipped_count``
* ``repositories[].safety.redacted_count``
* ``repositories[].safety.findings``
* per-file ``is_redacted`` / ``is_binary_skipped`` / ``is_safety_skipped``

If you want stricter packaging behavior, use redaction and validation policy
flags together.


Validate Before Acting
----------------------

Use ``validate-pack`` before unpacking or applying edits in CI or autonomous
loops.

Examples:

.. code-block:: console

   codecrate validate-pack context.md
   codecrate validate-pack context.md --root .
   codecrate validate-pack context.md --strict
   codecrate validate-pack context.md --root . --fail-on-root-drift
   codecrate validate-pack context.md --fail-on-warning
   codecrate validate-pack context.md --fail-on-redaction
   codecrate validate-pack context.md --fail-on-safety-skip
   codecrate validate-pack context.md --json

Recommended CI-style validation for agent loops:

.. code-block:: console

   codecrate validate-pack context.md --root . --strict --fail-on-warning --fail-on-root-drift --json

JSON validation output includes:

* ``error_count``
* ``warning_count``
* ``policy_error_count``
* ``root_drift_count``
* ``redacted_count``
* ``safety_skip_count``


Use Patch And Apply Loops
-------------------------

For iterative edit workflows, patch/apply is often safer than directly editing
packed markdown.

Baseline pack:

.. code-block:: console

   codecrate pack . -o baseline.md --profile hybrid

Generate a patch after local changes:

.. code-block:: console

   codecrate patch baseline.md . -o changes.md

Validate or apply the patch:

.. code-block:: console

   codecrate apply changes.md . --dry-run
   codecrate apply changes.md . --check-baseline

This keeps the change representation in unified diff form and lets Codecrate
verify baseline hashes before applying edits.


Mixed-Language Repositories
---------------------------

For non-Python files, the index sidecar makes backend reporting explicit.

Per-file fields include:

* ``language_detected``
* ``symbol_backend_requested``
* ``symbol_backend_used``
* ``symbol_extraction_status``

This helps an agent distinguish between:

* a file type that is unsupported
* a backend that was disabled
* a backend that was unavailable
* a parse that succeeded but yielded no symbols

Example:

.. code-block:: console

   codecrate pack . -o context.md --include "*.java" --symbol-backend tree-sitter --index-json


Recommended Defaults
--------------------

For human review:

.. code-block:: console

   codecrate pack . -o context.md --profile human

For autonomous retrieval/edit loops:

.. code-block:: console

   codecrate pack . -o context.md --profile agent
   codecrate validate-pack context.md --root . --strict --fail-on-warning --fail-on-root-drift

For mixed workflows where humans and agents both read the result:

.. code-block:: console

   codecrate pack . -o context.md --profile hybrid
