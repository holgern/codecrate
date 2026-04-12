from __future__ import annotations

import json
from typing import Any

from .config import CONFIG_FIELD_METADATA, Config, _config_default, config_field_names


def config_field_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name in config_field_names():
        metadata = CONFIG_FIELD_METADATA[name]
        specs.append(
            {
                "name": name,
                "type": metadata.type_name,
                "default": _config_default(name),
                "description": metadata.description,
                "cli_flags": list(metadata.cli_flags),
                "aliases": list(metadata.aliases),
                "access": metadata.access,
                "choices": list(metadata.choices),
            }
        )
    return specs


def config_schema_payload() -> dict[str, Any]:
    return {
        "format": "codecrate.config-schema.v1",
        "precedence": [
            "CLI flags",
            ".codecrate.toml",
            "codecrate.toml",
            "pyproject.toml[tool.codecrate]",
        ],
        "fields": config_field_specs(),
    }


def render_config_reference_rst() -> str:
    def _csv_cell(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    lines = [
        "Configuration Reference",
        "=======================",
        "",
        ".. NOTE:: This page is generated from ``codecrate.config``. Update the",
        "   config metadata in code and regenerate the file instead of editing it",
        "   by hand.",
        "",
        "Precedence",
        "----------",
        "",
        "1. CLI flags",
        "2. ``.codecrate.toml`` / ``codecrate.toml``",
        "3. ``pyproject.toml`` under ``[tool.codecrate]``",
        "",
        "Profile chooser",
        "---------------",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        "",
        "   * - Use case",
        "     - Profile",
        "     - Notes",
        "   * - Review-only markdown",
        "     - ``human``",
        "     - Markdown-first output without profile-implied index-json sidecars.",
        "   * - Retrieval and agent lookup",
        "     - ``agent``",
        "     - Compact navigation plus normalized v3 index-json output.",
        "   * - Lean agent retrieval",
        "     - ``lean-agent``",
        (
            "     - Compact navigation plus minified normalized v3 sidecars with "
            "lean analysis defaults."
        ),
        "   * - Review plus tooling",
        "     - ``hybrid``",
        "     - Rich markdown plus the full v1-compatible index-json sidecar.",
        "   * - Portable reconstruction",
        "     - ``portable``",
        "     - Manifest-enabled ``full`` layout tuned for standalone unpacking.",
        "   * - Portable retrieval + reconstruction",
        "     - ``portable-agent``",
        (
            "     - Full layout, standalone unpacker, dual locators, and "
            "normalized sidecar defaults."
        ),
        "",
        "TOML versus CLI",
        "---------------",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        "",
        "   * - Capability",
        "     - TOML",
        "     - CLI",
        "     - Notes",
        "   * - Pack-shaping settings below",
        "     - Yes",
        "     - Yes",
        "     - Shared config and CLI support.",
        "   * - Explicit file lists (``--stdin`` / ``--stdin0``)",
        "     - No",
        "     - Yes",
        "     - Operational input mode, not stored in TOML.",
        (
            "   * - Debug printing (``--print-files``, ``--print-skipped``, "
            "``--print-rules``)"
        ),
        "     - No",
        "     - Yes",
        "     - Operational diagnostics only.",
        "   * - Root / multi-repo selection",
        "     - No",
        "     - Yes",
        "     - Runtime repository selection stays CLI-only.",
        "",
        "Supported keys",
        "--------------",
        "",
        ".. csv-table::",
        (
            '   :header: "Key", "Type", "Default", "Access", "CLI", '
            '"Aliases", "Choices", "Description"'
        ),
        "",
    ]
    for field_spec in config_field_specs():
        row = [
            field_spec["name"],
            field_spec["type"],
            json.dumps(field_spec["default"], ensure_ascii=True),
            field_spec["access"],
            ", ".join(field_spec["cli_flags"]) or "none",
            ", ".join(field_spec["aliases"]) or "none",
            ", ".join(field_spec["choices"]) or "none",
            field_spec["description"],
        ]
        lines.append("   " + ", ".join(_csv_cell(str(value)) for value in row))
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "Config",
    "config_field_specs",
    "config_schema_payload",
    "render_config_reference_rst",
]
