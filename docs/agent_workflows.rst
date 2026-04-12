Agent Workflows
===============

Codecrate can be used as a human-readable markdown exporter, but the current
pack and sidecar output is also intended to support coding-agent workflows.

This page focuses on how to use Codecrate when an agent needs to read,
retrieve, validate, diff, and apply changes safely.


Choose A Profile
----------------

Codecrate supports six output profiles:

* ``human``: keep the current markdown-first behavior
* ``agent``: compact navigation plus normalized ``codecrate.index-json.v3``
* ``lean-agent``: normalized ``codecrate.index-json.v3`` with lean analysis and
  markdown defaults
* ``hybrid``: current markdown richness plus full ``codecrate.index-json.v1``
* ``portable``: manifest-enabled ``full`` layout for standalone reconstruction
* ``portable-agent``: reconstructable ``full`` layout plus normalized retrieval
  metadata and dual locators

Example:

.. code-block:: console

   codecrate pack . -o context.md --profile agent
   codecrate pack . -o context.md --profile lean-agent
   codecrate pack . -o context.md --profile portable-agent

If you relied on compact-only lookup convenience fields, request them
explicitly:

.. code-block:: console

   codecrate pack . -o context.md --profile agent --index-json-mode compact

Explicit CLI flags still override profile defaults. For example, this keeps the
``agent`` profile but turns file-level navigation back on and disables the
index sidecar:

.. code-block:: console

   codecrate pack . -o context.md --profile agent --nav-mode full --no-index-json

Use ``portable`` when reconstruction is the priority rather than retrieval:

.. code-block:: console

   codecrate pack . -o context.md --profile portable --emit-standalone-unpacker

If you also want an ``index-json`` sidecar that points at the reconstructed
tree, keep the default ``--locator-space auto`` and add a sidecar mode:

.. code-block:: console

   codecrate pack . -o context.md --profile portable \
     --emit-standalone-unpacker --index-json-mode normalized

Use ``portable-agent`` when you want those reconstruction and retrieval defaults
in one preset:

.. code-block:: console

   codecrate pack . -o context.md --profile portable-agent


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
* use ``portable`` profile when you want a generated ``context.unpack.py`` that
  reconstructs the pack with stock Python only
* use patch/apply when you want baseline-aware edit loops instead of directly
  rewriting packed markdown

The standalone unpacker itself supports both ``full`` and ``stubs`` packs.
The distinction is that ``portable`` chooses reconstruction-first defaults,
while an explicit ``--layout stubs --emit-standalone-unpacker`` combination
lets you keep the token-efficient stub layout and still reconstruct offline.


Use The Index Sidecar
---------------------

Codecrate now exposes three sidecar modes:

* ``full``: current v1-compatible retrieval surface
* ``compact``: machine-first v2 retrieval surface
* ``minimal``: smallest v2-compatible retrieval surface
* ``normalized``: table-interned v3 retrieval surface with the best default
  token efficiency for agent workflows

See :doc:`index_json` for the contract and field guide.

Generate it directly:

.. code-block:: console

   codecrate pack . -o context.md --index-json
   codecrate pack . -o context.md --index-json-mode minimal
   codecrate pack . -o context.md --index-json-mode normalized

``--index-json`` alone keeps the full v1-compatible sidecar. Use
``--index-json-mode compact|minimal|normalized`` when you want the leanest
machine-first sidecar surface.

Use ``--profile lean-agent`` when you want those lean defaults without spelling
out the individual toggles.

If you need to trim the v2 payload further, you can also disable the lookup maps
or compact-only symbol index line ranges:

.. code-block:: console

   codecrate pack . -o context.md --profile agent --no-index-json-lookup
   codecrate pack . -o context.md --index-json-mode compact --no-index-json-symbol-index-lines

Or let the profile imply it:

.. code-block:: console

   codecrate pack . -o context.md --profile hybrid
   codecrate pack . -o context.md --profile agent

The sidecar includes:

* per-repository metadata
* split part metadata
* file-to-part lookup
* symbol-to-file lookup
* symbol-to-canonical-body lookup in stub layout
* direct href-style navigation fields
* reverse lookup indexes appropriate to the chosen mode
* unsplit markdown line ranges for review-oriented jumps
* locator-space metadata describing whether the primary machine-facing locators
  point to markdown, reconstructed files, or both
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
* ``markdown_lines`` on unsplit packs
* ``locators.markdown`` and/or ``locators.reconstructed``

In full/v1 mode you also get ``anchors`` and richer size/hash metadata.

Locate a symbol and its canonical body in stub layout:

.. code-block:: console

   codecrate pack . -o context.md --layout stubs --index-json

Then inspect ``repositories[].symbols[]`` for:

* ``local_id``
* ``canonical_id`` when stub/dedupe behavior requires it
* ``file_part``
* ``file_href``
* ``canonical_part``
* ``canonical_href``
* ``index_markdown_lines`` on unsplit packs
* ``canonical_markdown_lines`` on unsplit stub packs
* ``locators.markdown`` and/or ``locators.reconstructed``

By default, review-oriented packs keep markdown locators. When
``--emit-standalone-unpacker`` is enabled, ``--locator-space auto`` switches the
primary sidecar locator space to reconstructed files instead.

If you need explicit reverse indexes instead of scanning arrays, inspect
``repositories[].lookup`` for:

* ``file_by_path``
* ``file_by_symbol``
* ``part_by_file``
* ``symbol_by_local_id``

``minimal`` mode trims that further to ``file_by_path`` and
``symbol_by_local_id`` only.


Understand Split Output
-----------------------

When ``--split-max-chars`` is used, Codecrate can emit:

* ``context.index.md``
* ``context.partN.md`` files

Split output is intended for reading and retrieval, while the unsplit markdown
remains the machine-readable source for unpack, validate, and standalone
reconstruction flows.

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
