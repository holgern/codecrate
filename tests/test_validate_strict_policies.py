from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from codecrate.cli import main


def _break_first_marker(markdown: str) -> str:
    return re.sub(
        r"FUNC:(?:v\d+:)?[0-9A-Fa-f]{8}",
        "BROKEN:DEADBEEF",
        markdown,
        count=1,
    )


def test_validate_fail_on_warning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--layout", "stubs"])
    packed.write_text(
        _break_first_marker(packed.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed), "--fail-on-warning"])
    assert excinfo.value.code == 1


def test_validate_fail_on_root_drift_requires_root(tmp_path: Path) -> None:
    packed = tmp_path / "context.md"
    packed.write_text("# not a real pack\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed), "--fail-on-root-drift"])
    assert excinfo.value.code == 2


def test_validate_fail_on_root_drift_json_reports_policy_error(
    tmp_path: Path, capsys
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "a.py"
    target.write_text("def alpha():\n    return 1\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed)])
    target.write_text("def alpha():\n    return 2\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "validate-pack",
                str(packed),
                "--root",
                str(repo),
                "--fail-on-root-drift",
                "--json",
            ]
        )
    assert excinfo.value.code == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["root_drift_count"] == 1
    assert payload["policy_error_count"] == 1
    assert payload["policy_errors"]


def test_validate_fail_on_redaction(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("SECRET=123\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--include",
            "*",
            "--security-redaction",
        ]
    )

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed), "--fail-on-redaction"])
    assert excinfo.value.code == 1


def test_validate_fail_on_safety_skip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("SECRET=123\n", encoding="utf-8")

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--include", "*"])

    with pytest.raises(SystemExit) as excinfo:
        main(["validate-pack", str(packed), "--fail-on-safety-skip"])
    assert excinfo.value.code == 1
