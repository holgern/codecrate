from __future__ import annotations

import json
from pathlib import Path

import pytest

from codecrate.cli import main


def test_doctor_reports_config_precedence_and_selected_file(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.codecrate]\noutput = 'pyproject.md'\n",
        encoding="utf-8",
    )
    (tmp_path / "codecrate.toml").write_text(
        "[codecrate]\noutput = 'codecrate.md'\n",
        encoding="utf-8",
    )
    (tmp_path / ".codecrate.toml").write_text(
        "[codecrate]\noutput = 'dot.md'\n",
        encoding="utf-8",
    )

    main(["doctor", str(tmp_path)])

    captured = capsys.readouterr()
    assert "Codecrate Doctor" in captured.out
    assert (
        ".codecrate.toml > codecrate.toml > pyproject.toml[tool.codecrate]"
        in captured.out
    )
    assert "- selected: .codecrate.toml" in captured.out


def test_doctor_reports_ignore_token_and_tree_sitter_status(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / ".codecrateignore").write_text("secret.py\n", encoding="utf-8")

    main(["doctor", str(tmp_path)])

    captured = capsys.readouterr()
    assert "Ignore files:" in captured.out
    assert "- .gitignore: yes" in captured.out
    assert "- .codecrateignore: yes" in captured.out
    assert "Token backend:" in captured.out
    assert "- backend:" in captured.out
    assert "Optional parsing backends:" in captured.out
    assert "- tree-sitter:" in captured.out


def test_doctor_reports_invalid_numeric_config_warnings(tmp_path: Path, capsys) -> None:
    (tmp_path / "codecrate.toml").write_text(
        '[codecrate]\nmax_total_tokens = "bad"\n',
        encoding="utf-8",
    )

    main(["doctor", str(tmp_path)])

    captured = capsys.readouterr()
    assert "Config warnings:" in captured.out
    assert "max_total_tokens" in captured.out


def test_doctor_reports_unknown_keys_and_explicit_fields(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "codecrate.toml").write_text(
        '[codecrate]\noutput = "custom.md"\nunknown_toggle = true\n',
        encoding="utf-8",
    )

    main(["doctor", str(tmp_path)])

    captured = capsys.readouterr()
    assert "unknown_toggle" in captured.out
    assert "Resolved config fields:" in captured.out
    assert "output: codecrate.toml (key: output)" in captured.out


def test_config_show_reports_value_provenance_and_json_payload(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "codecrate.toml").write_text(
        "[codecrate]\ninclude_manifest = false\n",
        encoding="utf-8",
    )

    main(["config", "show", str(tmp_path)])
    captured = capsys.readouterr()
    assert "Value provenance:" in captured.out
    assert "manifest: codecrate.toml (key: include_manifest)" in captured.out

    main(["config", "show", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["provenance"]["manifest"] == {
        "source": "codecrate.toml",
        "config_key": "include_manifest",
    }


def test_config_schema_json_lists_supported_fields(capsys) -> None:
    main(["config", "schema", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["format"] == "codecrate.config-schema.v1"
    names = {field["name"] for field in payload["fields"]}
    assert "index_json_enabled" in names
    assert "manifest_json_output" in names
    assert "standalone_unpacker_output" in names


def test_doctor_rejects_non_directory_root(tmp_path: Path) -> None:
    not_dir = tmp_path / "file.txt"
    not_dir.write_text("x\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["doctor", str(not_dir)])

    assert excinfo.value.code == 2
