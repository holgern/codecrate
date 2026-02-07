from __future__ import annotations

import pytest

from codecrate.cli import main


def test_main_without_command_prints_friendly_help(capsys) -> None:
    main([])

    captured = capsys.readouterr()
    assert "usage: codecrate" in captured.out
    assert "Quick start examples:" in captured.out
    assert "codecrate pack . -o context.md" in captured.out
    assert "codecrate unpack context.md -o out/ --strict" in captured.out
    assert "codecrate validate-pack context.md --strict" in captured.out


def test_main_help_flag_still_works(capsys) -> None:
    try:
        main(["-h"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "pack" in captured.out
    assert "unpack" in captured.out
    assert "validate-pack" in captured.out


def test_main_version_flag_prints_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("codecrate ")


def test_pack_help_clarifies_explicit_file_behavior(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["pack", "-h"])
    assert exc.value.code == 0

    captured = capsys.readouterr()
    assert "Include globs are not applied" in captured.out
    assert "exclude" in captured.out
    assert "ignore files still apply" in captured.out
