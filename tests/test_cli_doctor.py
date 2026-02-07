from __future__ import annotations

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


def test_doctor_rejects_non_directory_root(tmp_path: Path) -> None:
    not_dir = tmp_path / "file.txt"
    not_dir.write_text("x\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["doctor", str(not_dir)])

    assert excinfo.value.code == 2
