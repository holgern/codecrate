# Changelog

## v0.4.3

### Added

- **Portable agent reconstruction workflow**: Generated portable-agent markdown now includes a machine reconstruction section with an explicit `python3 -S` standalone unpack command, machine-header checking, strict warning failure guidance, fallback interpreter guidance, and a warning not to scrape markdown manually.
- **Agent workflow JSON fence**: Generated portable-agent markdown includes a deterministic `codecrate-agent-workflow` JSON fence. `validate-pack --strict` accepts packs containing that fence.
- **Reconstruction command output**: After writing a standalone unpacker, `codecrate pack` prints a copy-pasteable reconstruction command using `python3 -S`, the markdown filename, `-o reconstructed`, `--check-machine-header`, `--strict`, and `--fail-on-warning`.
- **`--fail-on-warning` for unpack**: Installed and standalone unpacker paths support `--fail-on-warning`, which makes SHA mismatch, unresolved markers in non-strict mode, and missing non-empty file blocks fail with exit code 2. Default behavior still warns without failing.
- **`--progress` for standalone unpacker**: The standalone unpacker supports `--progress` and prints compact stage markers to stderr for reading, parsing, reconstructing/writing, and done.
- **`--check-machine-header` for installed unpack**: `codecrate unpack` now supports `--check-machine-header`, which verifies the machine-header manifest checksum before writing files. Fails for corrupt or missing machine headers when requested.

### Fixed

- **Spurious marker collision warnings**: `validate-pack --fail-on-warning` no longer reports repo-scope marker-collision warnings for literal marker examples embedded inside ordinary file content. Only active manifest markers are considered for collision checks.

### Documentation

- Updated README and Sphinx docs to use `python3 -S` for standalone unpack examples, including Windows `py -3 -S` guidance.
- Documented fallback reconstruction instructions without whole-file regex scraping.
- Added `codecrate-agent-workflow` fence documentation to `docs/format.rst`.
- Documented agent fallback reconstruction flow in `docs/agent_workflows.rst`.
- Updated CLI help, `docs/cli.rst`, and `docs/quickstart.rst` with `--check-machine-header` and strict unpack examples.
