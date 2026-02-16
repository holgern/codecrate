from __future__ import annotations

import json
from pathlib import Path

import pytest

from codecrate.cli import main


def test_config_show_effective_prints_default_sensitive_path_patterns(
    tmp_path: Path, capsys
) -> None:
    main(["config", "show", str(tmp_path), "--effective"])

    captured = capsys.readouterr()
    assert "Codecrate Config" in captured.out
    assert "Mode: effective" in captured.out
    assert '"*secrets*"' in captured.out
    assert "security_path_patterns =" in captured.out


def test_config_show_effective_uses_selected_config_source(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.codecrate]\noutput = 'pyproject'\n",
        encoding="utf-8",
    )
    (tmp_path / "codecrate.toml").write_text(
        "[codecrate]\noutput = 'codecrate'\n",
        encoding="utf-8",
    )
    (tmp_path / ".codecrate.toml").write_text(
        "[codecrate]\noutput = 'dot'\nsecurity_path_patterns = ['*.pem']\n",
        encoding="utf-8",
    )

    main(["config", "show", str(tmp_path), "--effective"])

    captured = capsys.readouterr()
    assert "Selected: .codecrate.toml" in captured.out
    assert 'output = "dot.md"' in captured.out
    assert 'security_path_patterns = ["*.pem"]' in captured.out


def test_config_show_effective_json_output(tmp_path: Path, capsys) -> None:
    main(["config", "show", str(tmp_path), "--effective", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["mode"] == "effective"
    assert payload["selected"] == "none (defaults only)"
    assert "*secrets*" in payload["values"]["security_path_patterns"]


def test_config_show_effective_applies_path_add_remove(tmp_path: Path, capsys) -> None:
    (tmp_path / "codecrate.toml").write_text(
        """[codecrate]
security_path_patterns_add = ["*.vault"]
security_path_patterns_remove = ["*secrets*"]
""",
        encoding="utf-8",
    )

    main(["config", "show", str(tmp_path), "--effective", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    patterns = payload["values"]["security_path_patterns"]
    assert "*.vault" in patterns
    assert "*secrets*" not in patterns


def test_config_show_rejects_non_directory_root(tmp_path: Path) -> None:
    not_dir = tmp_path / "file.txt"
    not_dir.write_text("x\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["config", "show", str(not_dir), "--effective"])

    assert excinfo.value.code == 2
