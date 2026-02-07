from __future__ import annotations

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
