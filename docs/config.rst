Configuration Reference
=======================

.. NOTE:: This page is generated from ``codecrate.config``. Update the
   config metadata in code and regenerate the file instead of editing it
   by hand.

Precedence
----------

1. CLI flags
2. ``.codecrate.toml`` / ``codecrate.toml``
3. ``pyproject.toml`` under ``[tool.codecrate]``

Profile chooser
---------------

.. list-table::
   :header-rows: 1

   * - Use case
     - Profile
     - Notes
   * - Review-only markdown
     - ``human``
     - Markdown-first output without profile-implied index-json sidecars.
   * - Retrieval and agent lookup
     - ``agent``
     - Compact navigation plus normalized v3 index-json output.
   * - Lean agent retrieval
     - ``lean-agent``
     - Compact navigation plus minified normalized v3 sidecars with lean analysis defaults.
   * - Review plus tooling
     - ``hybrid``
     - Rich markdown plus the full v1-compatible index-json sidecar.
   * - Portable reconstruction
     - ``portable``
     - Manifest-enabled ``full`` layout tuned for standalone unpacking.
   * - Portable retrieval + reconstruction
     - ``portable-agent``
     - Full layout, standalone unpacker, dual locators, and normalized sidecar defaults.

TOML versus CLI
---------------

.. list-table::
   :header-rows: 1

   * - Capability
     - TOML
     - CLI
     - Notes
   * - Pack-shaping settings below
     - Yes
     - Yes
     - Shared config and CLI support.
   * - Explicit file lists (``--stdin`` / ``--stdin0``)
     - No
     - Yes
     - Operational input mode, not stored in TOML.
   * - Debug printing (``--print-files``, ``--print-skipped``, ``--print-rules``)
     - No
     - Yes
     - Operational diagnostics only.
   * - Root / multi-repo selection
     - No
     - Yes
     - Runtime repository selection stays CLI-only.

Supported keys
--------------

.. csv-table::
   :header: "Key", "Type", "Default", "Access", "CLI", "Aliases", "Choices", "Description"

   "output", "string", """context.md""", "both", "-o, --output", "none", "none", "Default markdown output path for pack runs."
   "keep_docstrings", "boolean", "true", "both", "--keep-docstrings, --no-keep-docstrings", "none", "none", "Keep docstrings in stubbed file output."
   "dedupe", "boolean", "false", "both", "--dedupe, --no-dedupe", "none", "none", "Deduplicate identical function bodies."
   "respect_gitignore", "boolean", "true", "both", "--respect-gitignore, --no-respect-gitignore", "none", "none", "Respect .gitignore during file discovery."
   "include", "list[string]", "[""**/*.py"", ""pyproject.toml"", ""project.toml"", ""setup.cfg"", ""README*"", ""LICENSE*"", ""docs/**/*.rst"", ""docs/**/*.md""]", "both", "--include", "none", "none", "Include glob patterns."
   "include_preset", "enum", """python+docs""", "both", "--include-preset", "none", "python-only, python+docs, everything", "Fallback include preset when include is not set."
   "exclude", "list[string]", "[]", "both", "--exclude", "none", "none", "Exclude glob patterns."
   "split_max_chars", "integer", "0", "both", "--split-max-chars", "none", "none", "Split markdown output when it exceeds this many characters."
   "split_strict", "boolean", "false", "both", "--split-strict, --no-split-strict", "none", "none", "Fail when a logical split block exceeds split_max_chars."
   "split_allow_cut_files", "boolean", "false", "both", "--split-allow-cut-files, --no-split-allow-cut-files", "none", "none", "Allow oversized files to be cut across split parts."
   "manifest", "boolean", "true", "both", "--manifest, --no-manifest", "include_manifest", "none", "Include the Manifest section in generated markdown."
   "profile", "enum", """human""", "both", "--profile", "none", "human, agent, lean-agent, hybrid, portable, portable-agent", "Output defaults profile."
   "layout", "enum", """auto""", "both", "--layout", "none", "auto, stubs, full", "Markdown layout mode."
   "token_count_encoding", "string", """o200k_base""", "both", "--token-count-encoding", "none", "none", "Tokenizer encoding for CLI token diagnostics."
   "token_count_tree", "boolean", "false", "both", "--token-count-tree", "none", "none", "Enable CLI token tree reporting."
   "token_count_tree_threshold", "integer", "0", "both", "none", "none", "none", "Minimum token threshold for token tree reporting."
   "top_files_len", "integer", "5", "both", "--top-files-len", "none", "none", "Number of largest files to print in CLI token diagnostics."
   "max_file_bytes", "integer", "0", "both", "--max-file-bytes", "none", "none", "Skip files larger than this many bytes."
   "max_total_bytes", "integer", "0", "both", "--max-total-bytes", "none", "none", "Fail if the included file set exceeds this many bytes."
   "max_file_tokens", "integer", "0", "both", "--max-file-tokens", "none", "none", "Skip files larger than this many tokens."
   "max_total_tokens", "integer", "0", "both", "--max-total-tokens", "none", "none", "Fail if the included file set exceeds this many tokens."
   "max_workers", "integer", "0", "both", "--max-workers", "none", "none", "Worker count for IO, parsing, and token counting."
   "file_summary", "boolean", "true", "both", "--file-summary, --no-file-summary", "none", "none", "Print the CLI pack summary block."
   "security_check", "boolean", "true", "both", "--security-check, --no-security-check", "none", "none", "Enable sensitive-file safety checks."
   "security_content_sniff", "boolean", "false", "both", "--security-content-sniff, --no-security-content-sniff", "none", "none", "Scan file content for sensitive patterns."
   "security_redaction", "boolean", "false", "both", "--security-redaction, --no-security-redaction", "none", "none", "Redact flagged files instead of skipping them."
   "safety_report", "boolean", "false", "both", "--safety-report, --no-safety-report", "none", "none", "Include the Safety Report section in generated markdown."
   "security_path_patterns", "list[string]", "["".env"", "".env.*"", ""*.pem"", ""*.key"", ""*.p12"", ""*.pfx"", ""*.jks"", ""*.kdbx"", ""*.crt"", ""*.cer"", ""*.der"", ""*.asc"", ""*.gpg"", "".npmrc"", "".pypirc"", ""id_rsa"", ""id_rsa*"", ""id_dsa"", ""id_dsa*"", ""id_ed25519"", ""id_ed25519*"", ""credentials.json"", ""*secrets*""]", "both", "--security-path-pattern", "none", "none", "Base sensitive-path glob rules."
   "security_path_patterns_add", "list[string]", "[]", "both", "--security-path-pattern-add", "none", "none", "Additional sensitive-path glob rules."
   "security_path_patterns_remove", "list[string]", "[]", "both", "--security-path-pattern-remove", "none", "none", "Sensitive-path glob rules to remove from the base set."
   "security_content_patterns", "list[string]", "[""private-key=(?i)-----BEGIN\\s+[A-Z ]*PRIVATE KEY-----"", ""aws-access-key-id=\\b(?:AKIA|ASIA)[0-9A-Z]{16}\\b"", ""aws-secret-access-key=aws_secret_access_key\\s*[:=]\\s*['\\\""]?[A-Za-z0-9/+=]{20,}"", ""generic-api-key=(?i)\\b(?:api[_-]?key|x-api-key)\\b\\s*[:=]\\s*['\\\""]?[A-Za-z0-9_\\-]{16,}""]", "both", "--security-content-pattern", "none", "none", "Sensitive-content regex rules."
   "nav_mode", "enum", """auto""", "both", "--nav-mode", "none", "auto, compact, full", "Navigation density in generated markdown."
   "index_json_mode", "enum|null", "null", "both", "--index-json-mode", "none", "full, compact, minimal, normalized", "Index-json format mode."
   "index_json_enabled", "boolean|null", "null", "both", "--index-json, --no-index-json", "none", "none", "Explicitly enable or disable index-json output."
   "manifest_json_output", "string|null", "null", "both", "--manifest-json", "none", "none", "Optional manifest JSON output path; empty string uses the default sibling path."
   "index_json_output", "string|null", "null", "both", "--index-json", "none", "none", "Optional index-json output path; empty string uses the default sibling path."
   "emit_standalone_unpacker", "boolean", "false", "both", "--emit-standalone-unpacker", "none", "none", "Write a standalone unpacker next to the markdown output."
   "standalone_unpacker_output", "string|null", "null", "config-only", "none", "none", "none", "Optional standalone unpacker output path; empty string uses the default sibling path."
   "locator_space", "enum", """auto""", "both", "--locator-space", "none", "auto, markdown, reconstructed, dual", "Locator target space for index-json payloads."
   "index_json_pretty", "boolean|null", "null", "both", "--index-json-pretty, --no-index-json-pretty", "none", "none", "Pretty-print index-json output instead of minifying it."
   "index_json_include_lookup", "boolean|null", "null", "both", "--index-json-lookup, --no-index-json-lookup", "none", "none", "Include lookup tables in compact/minimal v2 index-json output."
   "index_json_include_symbol_index_lines", "boolean|null", "null", "both", "--index-json-symbol-index-lines, --no-index-json-symbol-index-lines", "none", "none", "Include unsplit symbol index line ranges in compact v2 index-json output."
   "index_json_include_graph", "boolean|null", "null", "both", "--index-json-graph, --no-index-json-graph", "none", "none", "Include import-graph metadata in index-json output."
   "index_json_include_test_links", "boolean|null", "null", "both", "--index-json-test-links, --no-index-json-test-links", "none", "none", "Include source-to-test links in index-json output."
   "index_json_include_guide", "boolean|null", "null", "both", "--index-json-guide, --no-index-json-guide", "none", "none", "Include repository guide metadata in index-json output."
   "index_json_include_file_imports", "boolean|null", "null", "both", "--index-json-file-imports, --no-index-json-file-imports", "none", "none", "Include per-file import metadata in index-json output."
   "index_json_include_classes", "boolean|null", "null", "both", "--index-json-classes, --no-index-json-classes", "none", "none", "Include class payloads in index-json output."
   "index_json_include_exports", "boolean|null", "null", "both", "--index-json-exports, --no-index-json-exports", "none", "none", "Include per-file export metadata in index-json output."
   "index_json_include_module_docstrings", "boolean|null", "null", "both", "--index-json-module-docstrings, --no-index-json-module-docstrings", "none", "none", "Include module docstring line ranges in index-json output."
   "index_json_include_semantic", "boolean|null", "null", "both", "--index-json-semantic, --no-index-json-semantic", "none", "none", "Include semantic signature metadata in index-json output."
   "index_json_include_purpose_text", "boolean|null", "null", "both", "--index-json-purpose-text, --no-index-json-purpose-text", "none", "none", "Include human-readable purpose text in index-json output."
   "index_json_include_symbol_locators", "boolean|null", "null", "both", "--index-json-symbol-locators, --no-index-json-symbol-locators", "none", "none", "Include symbol locator payloads in index-json output."
   "index_json_include_symbol_references", "boolean|null", "null", "both", "--index-json-symbol-references, --no-index-json-symbol-references", "none", "none", "Include symbol reference and call-like metadata in index-json output."
   "index_json_include_file_summaries", "boolean|null", "null", "both", "--index-json-file-summaries, --no-index-json-file-summaries", "none", "none", "Include per-file summary payloads in index-json output."
   "index_json_include_relationships", "boolean|null", "null", "both", "--index-json-relationships, --no-index-json-relationships", "none", "none", "Include per-file relationship payloads in index-json output."
   "analysis_metadata", "boolean|null", "null", "both", "--analysis-metadata, --no-analysis-metadata", "none", "none", "Default on/off switch for analysis-oriented metadata in generated outputs."
   "markdown_include_repository_guide", "boolean|null", "null", "both", "--markdown-repository-guide, --no-markdown-repository-guide", "none", "none", "Include the Repository Guide section in generated markdown."
   "markdown_include_symbol_index", "boolean|null", "null", "both", "--markdown-symbol-index, --no-markdown-symbol-index", "none", "none", "Include the Symbol Index section in generated markdown."
   "markdown_include_directory_tree", "boolean|null", "null", "both", "--markdown-directory-tree, --no-markdown-directory-tree", "none", "none", "Include the Directory Tree section in generated markdown."
   "markdown_include_environment_setup", "boolean|null", "null", "both", "--markdown-environment-setup, --no-markdown-environment-setup", "none", "none", "Include the Environment Setup section in generated markdown."
   "markdown_include_how_to_use", "boolean|null", "null", "both", "--markdown-how-to-use, --no-markdown-how-to-use", "none", "none", "Include the How to Use This Pack section in generated markdown."
   "focus_file", "list[string]", "[]", "both", "--focus-file", "none", "none", "Focus pack generation on specific repo-relative files."
   "focus_symbol", "list[string]", "[]", "both", "--focus-symbol", "none", "none", "Focus pack generation on specific symbols."
   "include_import_neighbors", "integer", "0", "both", "--include-import-neighbors", "none", "none", "Include this many local import-neighbor hops around focused files."
   "include_reverse_import_neighbors", "integer", "0", "both", "--include-reverse-import-neighbors", "none", "none", "Include this many reverse local import-neighbor hops around focused files."
   "include_same_package", "boolean", "false", "both", "--include-same-package, --no-include-same-package", "none", "none", "Include same-package neighbors in focused packs."
   "include_entrypoints", "boolean", "false", "both", "--include-entrypoints, --no-include-entrypoints", "none", "none", "Include entrypoints that reach focused files."
   "include_tests", "boolean", "false", "both", "--include-tests, --no-include-tests", "none", "none", "Include heuristically related tests in focused packs."
   "symbol_backend", "enum", """auto""", "both", "--symbol-backend", "none", "auto, python, tree-sitter, none", "Optional non-Python symbol extraction backend."
   "encoding_errors", "enum", """replace""", "both", "--encoding-errors", "none", "replace, strict", "UTF-8 decoding policy for repository and markdown reads."
