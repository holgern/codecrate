from __future__ import annotations

import importlib
import json
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

from .config import (
    CONFIG_FILENAMES,
    PYPROJECT_FILENAME,
    Config,
    ConfigValueProvenance,
    ConfigWarning,
    config_schema_payload,
    load_config_details,
)
from .security import build_ruleset
from .tokens import TokenCounter


def _doctor_find_selected_config(root: Path) -> Path | None:
    for name in CONFIG_FILENAMES:
        p = root / name
        if p.exists():
            return p
    pyproject = root / PYPROJECT_FILENAME
    if pyproject.exists():
        return pyproject
    return None


def _doctor_config_state(path: Path, *, pyproject: bool) -> str:
    if not path.exists():
        return "missing"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"present (parse error: {type(e).__name__})"

    if not isinstance(data, dict):
        return "present (invalid TOML root)"

    section_found = False
    if pyproject:
        tool = data.get("tool")
        section_found = isinstance(tool, dict) and isinstance(
            tool.get("codecrate"), dict
        )
    else:
        cc = data.get("codecrate")
        if isinstance(cc, dict):
            section_found = True
        else:
            tool = data.get("tool")
            section_found = isinstance(tool, dict) and isinstance(
                tool.get("codecrate"), dict
            )

    return "present (section found)" if section_found else "present (section missing)"


def _doctor_tree_sitter_status() -> str:
    try:
        tsl = importlib.import_module("tree_sitter_languages")
    except ModuleNotFoundError:
        return "missing"
    except Exception as e:  # pragma: no cover
        return f"error ({type(e).__name__})"

    get_parser = getattr(tsl, "get_parser", None)
    if not callable(get_parser):
        return "installed (get_parser missing)"

    try:
        get_parser("javascript")
    except Exception as e:
        return f"installed (unusable: {type(e).__name__})"
    return "available"


def _config_values(cfg: Config, *, effective: bool) -> dict[str, object]:
    values: dict[str, object] = {}
    for field in fields(cfg):
        values[field.name] = getattr(cfg, field.name)
    if effective:
        values["security_path_patterns"] = list(
            build_ruleset(
                path_patterns=cfg.security_path_patterns,
                path_patterns_add=getattr(cfg, "security_path_patterns_add", []),
                path_patterns_remove=getattr(cfg, "security_path_patterns_remove", []),
                content_patterns=[],
            ).path_patterns
        )
    return values


def _config_warning_payloads(
    config_warnings: Sequence[ConfigWarning],
) -> list[dict[str, object]]:
    return [
        {
            "key": warning.key,
            "raw_value": warning.raw_value,
            "fallback": warning.fallback,
            "message": warning.message,
        }
        for warning in config_warnings
    ]


def _format_config_warning(warning: ConfigWarning) -> str:
    raw_value = json.dumps(warning.raw_value, ensure_ascii=True)
    fallback = json.dumps(warning.fallback, ensure_ascii=True)
    return (
        f"{warning.key}: {warning.message} raw_value={raw_value}; fallback={fallback}"
    )


def _config_provenance_payloads(
    provenance: dict[str, ConfigValueProvenance],
) -> dict[str, dict[str, object]]:
    return {
        key: {"source": value.source, "config_key": value.config_key}
        for key, value in provenance.items()
    }


def _format_config_provenance(key: str, value: ConfigValueProvenance) -> str:
    if value.config_key is None:
        return f"{key}: {value.source}"
    return f"{key}: {value.source} (key: {value.config_key})"


def _run_config_show(root: Path, *, effective: bool, as_json: bool) -> None:
    root = root.resolve()
    details = load_config_details(root)
    selected = details.selected_path
    cfg = details.config
    config_warnings = details.warnings
    provenance = details.provenance
    mode = "effective"
    if not effective:
        # The command currently supports only effective configuration rendering.
        mode = "effective"

    values = _config_values(cfg, effective=True)
    selected_text = (
        "none (defaults only)"
        if selected is None
        else selected.relative_to(root).as_posix()
    )
    precedence = [
        ".codecrate.toml",
        "codecrate.toml",
        "pyproject.toml[tool.codecrate]",
    ]

    if as_json:
        payload = {
            "root": root.as_posix(),
            "mode": mode,
            "precedence": precedence,
            "selected": selected_text,
            "config_warnings": _config_warning_payloads(config_warnings),
            "provenance": _config_provenance_payloads(provenance),
            "values": values,
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
        return

    print("Codecrate Config")
    print(f"Root: {root.as_posix()}")
    print(f"Mode: {mode}")
    print(
        "Precedence: .codecrate.toml > codecrate.toml > pyproject.toml[tool.codecrate]"
    )
    print(f"Selected: {selected_text}")
    print()
    print("Config warnings:")
    if config_warnings:
        for warning in config_warnings:
            print(f"- {_format_config_warning(warning)}")
    else:
        print("- none")
    print()
    print("Value provenance:")
    for key, value in provenance.items():
        print(f"- {_format_config_provenance(key, value)}")
    print()
    print("Effective values:")
    for key, rendered_value in values.items():
        print(f"{key} = {json.dumps(rendered_value, ensure_ascii=True)}")


def _run_doctor(root: Path) -> None:
    root = root.resolve()
    details = load_config_details(root)
    selected = details.selected_path
    config_warnings = details.warnings
    provenance = details.provenance

    print("Codecrate Doctor")
    print(f"Root: {root.as_posix()}")
    print()

    print("Config discovery:")
    print(
        "- precedence: .codecrate.toml > codecrate.toml > "
        "pyproject.toml[tool.codecrate]"
    )
    for name in CONFIG_FILENAMES:
        p = root / name
        print(f"- {name}: {_doctor_config_state(p, pyproject=False)}")
    pyproject = root / PYPROJECT_FILENAME
    print(f"- {PYPROJECT_FILENAME}: {_doctor_config_state(pyproject, pyproject=True)}")
    if selected is None:
        print("- selected: none (defaults only)")
    else:
        print(f"- selected: {selected.relative_to(root).as_posix()}")

    print()
    print("Config warnings:")
    if config_warnings:
        for warning in config_warnings:
            print(f"- {_format_config_warning(warning)}")
    else:
        print("- none")

    print()
    print("Resolved config fields:")
    explicit_values = [
        (key, value) for key, value in provenance.items() if value.source != "default"
    ]
    if explicit_values:
        for key, value in explicit_values:
            print(f"- {_format_config_provenance(key, value)}")
    else:
        print("- all defaults")

    print()
    print("Ignore files:")
    print(f"- .gitignore: {'yes' if (root / '.gitignore').exists() else 'no'}")
    print(
        f"- .codecrateignore: {'yes' if (root / '.codecrateignore').exists() else 'no'}"
    )

    print()
    print("Token backend:")
    token_counter = TokenCounter("o200k_base")
    print(f"- backend: {token_counter.backend}")
    try:
        token_counter.count("def _doctor_probe():\n    return 1\n")
        print("- encoding o200k_base: ok")
    except Exception as e:
        print(f"- encoding o200k_base: error ({type(e).__name__})")

    print()
    print("Optional parsing backends:")
    print(f"- tree-sitter: {_doctor_tree_sitter_status()}")


def _run_config_schema(*, as_json: bool) -> None:
    payload = config_schema_payload()
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=False))
        return

    print("Codecrate Config Schema")
    print(
        "Precedence: .codecrate.toml > codecrate.toml > pyproject.toml[tool.codecrate]"
    )
    print()
    print("Fields:")
    for field in payload["fields"]:
        line = (
            f"- {field['name']} ({field['type']}, access={field['access']}, "
            f"default={json.dumps(field['default'], ensure_ascii=True)})"
        )
        print(line)
        if field["cli_flags"]:
            print(f"  CLI: {', '.join(field['cli_flags'])}")
        if field["aliases"]:
            print(f"  Aliases: {', '.join(field['aliases'])}")
        if field["choices"]:
            print(f"  Choices: {', '.join(field['choices'])}")
        print(f"  {field['description']}")
