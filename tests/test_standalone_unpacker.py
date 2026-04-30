from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from codecrate import mdparse, repositories, unpacker
from codecrate.cli import main
from codecrate.standalone_unpacker import render_standalone_unpacker

FIXTURES = Path(__file__).parent / "fixtures"
PACKS = FIXTURES / "packs"
REPOS = FIXTURES / "repos"


def _write_repo(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run_script(script: Path, *args: Path | str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        check=False,
    )


def _mutate_fence_openers(text: str) -> str:
    out = text
    out = out.replace(
        "```codecrate-machine-header",
        "```   codecrate-machine-header extra",
        1,
    )
    out = out.replace(
        "```codecrate-manifest",
        "```   codecrate-manifest extra-tokens",
        1,
    )
    return out.replace("```python", "```   python extra", 1)


def _break_first_marker(markdown: str) -> str:
    return re.sub(
        r"FUNC:(?:v\d+:)?[0-9A-Fa-f]{8}",
        "BROKEN:DEADBEEF",
        markdown,
        count=1,
    )


def _rename_first_function_library_id(markdown: str, replacement: str) -> str:
    return re.sub(
        r"^###\s+[0-9A-F]{8}\b",
        f"### {replacement}",
        markdown,
        count=1,
        flags=re.MULTILINE,
    )


def test_pack_emit_standalone_unpacker_writes_deterministic_script(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--include",
            "**/*.py",
            "--include",
            "**/*.md",
            "--emit-standalone-unpacker",
        ]
    )

    script = tmp_path / "context.unpack.py"
    first = script.read_text(encoding="utf-8")
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--include",
            "**/*.py",
            "--include",
            "**/*.md",
            "--emit-standalone-unpacker",
        ]
    )

    second = script.read_text(encoding="utf-8")
    assert first == second
    assert "Supported pack format: codecrate.v4" in first
    assert 'DEFAULT_PACK_FILENAME = "context.md"' in first
    assert "import codecrate" not in first


def test_pack_prints_standalone_reconstruction_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    main(
        [
            "pack",
            str(repo),
            "-o",
            str(tmp_path / "context.md"),
            "--profile",
            "portable-agent",
        ]
    )

    out = capsys.readouterr().out
    assert "Wrote" in out
    assert "context.unpack.py" in out
    assert "Reconstruct with:" in out
    assert "python3 -S" in out
    assert "context.md" in out
    assert "--check-machine-header" in out
    assert "--strict" in out
    assert "--fail-on-warning" in out


def test_standalone_unpacker_embeds_shared_runtime_sources() -> None:
    script = render_standalone_unpacker(
        pack_format_version="codecrate.v4",
        default_pack_filename="context.md",
    )

    for obj in (
        repositories.split_repository_sections,
        mdparse.parse_packed_markdown,
        unpacker._apply_canonical_into_stub,
    ):
        assert textwrap.dedent(inspect.getsource(obj)).strip() in script


def test_standalone_unpacker_reconstructs_single_repo_from_sibling_pack(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def alpha():\n    return 1\n",
            "README.md": "# Hello\n",
        },
    )

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(tmp_path / "context.unpack.py", "-o", tmp_path / "out")

    assert result.returncode == 0
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == (
        repo / "a.py"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "out" / "README.md").read_text(encoding="utf-8") == (
        repo / "README.md"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_progress_reports_stages(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(
        tmp_path / "context.unpack.py",
        str(packed),
        "-o",
        tmp_path / "out",
        "--progress",
    )

    assert result.returncode == 0
    assert "[codecrate-unpack] reading" in result.stderr
    assert "[codecrate-unpack] parsing manifest" in result.stderr
    assert "[codecrate-unpack] writing files to" in result.stderr
    assert "[codecrate-unpack] done" in result.stderr


def test_standalone_unpacker_fail_on_warning_fails_on_sha_mismatch(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )

    text = packed.read_text(encoding="utf-8")
    packed.write_text(text.replace("return 1", "return 2", 1), encoding="utf-8")

    default_result = _run_script(
        tmp_path / "context.unpack.py",
        str(packed),
        "-o",
        tmp_path / "default-out",
    )
    strict_result = _run_script(
        tmp_path / "context.unpack.py",
        str(packed),
        "-o",
        tmp_path / "strict-out",
        "--fail-on-warning",
    )

    assert default_result.returncode == 0
    assert strict_result.returncode == 2
    assert "SHA256 mismatch" in strict_result.stderr


def test_standalone_unpacker_reconstructs_empty_py_typed_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "pkg/a.py": "def alpha():\n    return 1\n",
            "pkg/py.typed": "",
        },
    )

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--include",
            "**/*.py",
            "--include",
            "**/py.typed",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(tmp_path / "context.unpack.py", "-o", tmp_path / "out")

    assert result.returncode == 0
    assert (tmp_path / "out" / "pkg" / "a.py").read_text(encoding="utf-8") == (
        repo / "pkg" / "a.py"
    ).read_text(encoding="utf-8")
    py_typed = tmp_path / "out" / "pkg" / "py.typed"
    assert py_typed.exists()
    assert py_typed.read_text(encoding="utf-8") == ""
    assert py_typed.stat().st_size == 0


def test_standalone_unpacker_reconstructs_markdown_with_internal_headings(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def alpha():\n    return 1\n",
            "AGENTS.md": (
                "# AGENTS.md\n\n"
                "## Repository Overview\n\n"
                "- Project: codecrate\n\n"
                "## Build, Lint, Format, Test Commands\n\n"
                "- pytest\n"
            ),
        },
    )

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--include",
            "**/*.py",
            "--include",
            "**/*.md",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(tmp_path / "context.unpack.py", "-o", tmp_path / "out")

    assert result.returncode == 0
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == (
        repo / "a.py"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "out" / "AGENTS.md").read_text(encoding="utf-8") == (
        repo / "AGENTS.md"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_reconstructs_multi_repo_pack(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, {"a.py": "def alpha():\n    return 1\n"})
    _write_repo(repo2, {"b.py": "def beta():\n    return 2\n"})

    packed = tmp_path / "combined.md"
    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(tmp_path / "combined.unpack.py", "-o", tmp_path / "out")

    assert result.returncode == 0
    assert (tmp_path / "out" / "repo1" / "a.py").read_text(encoding="utf-8") == (
        repo1 / "a.py"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "out" / "repo2" / "b.py").read_text(encoding="utf-8") == (
        repo2 / "b.py"
    ).read_text(encoding="utf-8")


def test_standalone_enabled_agent_sidecar_defaults_to_reconstructed_locators(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "agent",
            "--emit-standalone-unpacker",
        ]
    )

    payload = json.loads((tmp_path / "context.index.json").read_text(encoding="utf-8"))
    repo_entry = payload["repositories"][0]

    assert payload["mode"] == "normalized"
    assert repo_entry["locator_space"] == "reconstructed"
    assert repo_entry["files"][0]["loc"]["r"] == [1, 3]
    assert repo_entry["symbols"][0]["loc"]["r"]["l"] == [1, 2]


def test_standalone_unpacker_matches_codecrate_unpack_for_full_packs(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def alpha():\n    return 1\n",
            "README.md": "# hello\n",
        },
    )

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "full",
            "--emit-standalone-unpacker",
        ]
    )

    standalone_out = tmp_path / "standalone-out"
    builtin_out = tmp_path / "builtin-out"
    result = _run_script(
        tmp_path / "context.unpack.py", str(packed), "-o", standalone_out
    )
    assert result.returncode == 0

    main(["unpack", str(packed), "-o", str(builtin_out)])
    assert (standalone_out / "a.py").read_text(encoding="utf-8") == (
        builtin_out / "a.py"
    ).read_text(encoding="utf-8")
    assert (standalone_out / "README.md").read_text(encoding="utf-8") == (
        builtin_out / "README.md"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_reconstructs_stub_pack(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def f():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "stubs",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(
        tmp_path / "context.unpack.py", str(packed), "-o", tmp_path / "out"
    )

    assert result.returncode == 0
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == (
        repo / "a.py"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_reconstructs_multi_repo_stub_pack(tmp_path: Path) -> None:
    repo1 = tmp_path / "repo1"
    repo2 = tmp_path / "repo2"
    _write_repo(repo1, {"a.py": "def alpha():\n    return 1\n"})
    _write_repo(repo2, {"b.py": "def beta():\n    return 2\n"})

    packed = tmp_path / "combined.md"
    main(
        [
            "pack",
            "--repo",
            str(repo1),
            "--repo",
            str(repo2),
            "-o",
            str(packed),
            "--layout",
            "stubs",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(
        tmp_path / "combined.unpack.py", str(packed), "-o", tmp_path / "out"
    )

    assert result.returncode == 0
    assert (tmp_path / "out" / "repo1" / "a.py").read_text(encoding="utf-8") == (
        repo1 / "a.py"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "out" / "repo2" / "b.py").read_text(encoding="utf-8") == (
        repo2 / "b.py"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_stub_strict_fails_on_broken_marker(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def f():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "stubs",
            "--emit-standalone-unpacker",
        ]
    )
    packed.write_text(
        _break_first_marker(packed.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    result = _run_script(
        tmp_path / "context.unpack.py",
        str(packed),
        "-o",
        tmp_path / "out",
        "--strict",
    )

    assert result.returncode == 2
    assert "missing marker for" in result.stderr


def test_standalone_unpacker_stub_non_strict_warns_on_broken_marker(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def f():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "stubs",
            "--emit-standalone-unpacker",
        ]
    )
    packed.write_text(
        _break_first_marker(packed.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    result = _run_script(
        tmp_path / "context.unpack.py", str(packed), "-o", tmp_path / "out"
    )

    assert result.returncode == 0
    assert "Unresolved marker mapping" in result.stderr
    assert (tmp_path / "out" / "a.py").exists()


def test_standalone_unpacker_stub_strict_fails_on_missing_canonical_source(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def f():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "stubs",
            "--emit-standalone-unpacker",
        ]
    )
    packed.write_text(
        _rename_first_function_library_id(
            packed.read_text(encoding="utf-8"),
            "DEADC0DE",
        ),
        encoding="utf-8",
    )

    result = _run_script(
        tmp_path / "context.unpack.py",
        str(packed),
        "-o",
        tmp_path / "out",
        "--strict",
    )

    assert result.returncode == 2
    assert "missing canonical source" in result.stderr


def test_standalone_unpacker_reconstructs_deduped_stub_pack(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def f():\n    return 1\n\ndef g():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "stubs",
            "--dedupe",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(
        tmp_path / "context.unpack.py", str(packed), "-o", tmp_path / "out"
    )

    assert result.returncode == 0
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == (
        repo / "a.py"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_supports_old_marker_compat_pack(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    main(
        [
            "pack",
            str(repo),
            "-o",
            str(tmp_path / "context.md"),
            "--layout",
            "stubs",
            "--emit-standalone-unpacker",
        ]
    )

    result = _run_script(
        tmp_path / "context.unpack.py",
        PACKS / "golden_stub_compat.md",
        "-o",
        tmp_path / "out",
        "--strict",
    )

    assert result.returncode == 0
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == (
        REPOS / "golden_stub" / "a.py"
    ).read_text(encoding="utf-8")


def test_standalone_unpacker_rejects_missing_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(["pack", str(repo), "-o", str(packed), "--layout", "full"])
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(tmp_path / "portable.md"),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )
    packed.write_text(
        packed.read_text(encoding="utf-8").replace(
            "```codecrate-manifest", "```json", 1
        ),
        encoding="utf-8",
    )

    result = _run_script(
        tmp_path / "portable.unpack.py",
        str(packed),
        "-o",
        tmp_path / "out",
    )

    assert result.returncode == 2
    assert "No codecrate-manifest block found" in result.stderr


def test_standalone_unpacker_checks_machine_header_when_requested(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )
    text = packed.read_text(encoding="utf-8")
    match = re.search(r'"manifest_sha256":"([0-9a-f]{64})"', text)
    assert match is not None
    packed.write_text(
        text.replace(match.group(1), "0" * 64, 1),
        encoding="utf-8",
    )

    result = _run_script(
        tmp_path / "context.unpack.py",
        str(packed),
        "-o",
        tmp_path / "out",
        "--check-machine-header",
    )

    assert result.returncode == 2
    assert "Machine header checksum mismatch" in result.stderr


def test_standalone_unpacker_rejects_path_traversal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"safe.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )
    text = packed.read_text(encoding="utf-8")
    text = text.replace('"path": "safe.py"', '"path": "../evil.py"', 1)
    text = text.replace("## Files\n\n### `safe.py`", "## Files\n\n### `../evil.py`", 1)
    packed.write_text(text, encoding="utf-8")

    result = _run_script(
        tmp_path / "context.unpack.py", str(packed), "-o", tmp_path / "out"
    )

    assert result.returncode == 2
    assert "Refusing to write outside out_dir" in result.stderr


def test_standalone_unpacker_tolerates_fence_variants_and_crlf(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--profile",
            "portable",
            "--emit-standalone-unpacker",
        ]
    )
    text = packed.read_text(encoding="utf-8")
    packed.write_text(
        _mutate_fence_openers(text).replace("\n", "\r\n"),
        encoding="utf-8",
        newline="",
    )

    result = _run_script(
        tmp_path / "context.unpack.py", str(packed), "-o", tmp_path / "out"
    )

    assert result.returncode == 0
    assert (tmp_path / "out" / "a.py").read_text(encoding="utf-8") == (
        repo / "a.py"
    ).read_text(encoding="utf-8")


def test_pack_emit_standalone_unpacker_requires_manifest(
    tmp_path: Path, capsys
) -> None:
    repo = tmp_path / "repo"
    _write_repo(repo, {"a.py": "def alpha():\n    return 1\n"})

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "pack",
                str(repo),
                "-o",
                str(tmp_path / "context.md"),
                "--layout",
                "full",
                "--no-manifest",
                "--emit-standalone-unpacker",
            ]
        )

    assert excinfo.value.code == 2
    assert "requires a manifest-enabled pack" in capsys.readouterr().err


def test_pack_emit_standalone_unpacker_keeps_unsplit_markdown_with_split_output(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_repo(
        repo,
        {
            "a.py": "def alpha():\n    return 1\n\n" + "# a\n" * 40,
            "b.py": "def beta():\n    return 2\n\n" + "# b\n" * 40,
        },
    )

    packed = tmp_path / "context.md"
    main(
        [
            "pack",
            str(repo),
            "-o",
            str(packed),
            "--layout",
            "full",
            "--split-max-chars",
            "500",
            "--emit-standalone-unpacker",
        ]
    )

    assert packed.exists()
    assert (tmp_path / "context.unpack.py").exists()
    assert (tmp_path / "context.index.md").exists()
    assert list(tmp_path.glob("context.part*.md"))
