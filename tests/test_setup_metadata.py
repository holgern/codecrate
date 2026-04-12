from __future__ import annotations

from pathlib import Path

from codecrate.markdown import render_markdown
from codecrate.packer import pack_repo


def _render_for_files(root: Path, files: dict[str, str]) -> str:
    root.mkdir()
    packed_files: list[Path] = []
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if path.suffix in {".py", ".js", ".rs", ".go"}:
            packed_files.append(path)

    pack, canonical = pack_repo(root, packed_files, keep_docstrings=True, dedupe=False)
    return render_markdown(pack, canonical, layout="full", include_manifest=True)


def test_render_environment_setup_for_python_pyproject(tmp_path: Path) -> None:
    md = _render_for_files(
        tmp_path / "repo",
        {
            "a.py": "def f():\n    return 1\n",
            "pyproject.toml": (
                "[project]\n"
                'name = "demo"\n'
                'version = "0.1.0"\n'
                'dependencies = ["pathspec >= 1.0.0", "requests>=2"]\n'
                "\n"
                "[project.optional-dependencies]\n"
                'dev = ["pytest>=8", "ruff>=0.5"]\n'
            ),
        },
    )

    assert "## Environment Setup" in md
    assert "- Ecosystem: Python" in md
    assert "- Detected from: `pyproject.toml`" in md
    assert "- Prepare command: `python -m pip install -e .`" in md
    assert 'Optional dev command: `python -m pip install -e ".[dev]"`' in md
    assert "`pathspec >= 1.0.0`" in md
    assert "`requests>=2`" in md
    assert "`pytest>=8`" in md


def test_render_environment_setup_for_node_package_json(tmp_path: Path) -> None:
    md = _render_for_files(
        tmp_path / "repo",
        {
            "index.js": "function main() { return 1 }\n",
            "package.json": (
                "{\n"
                '  "name": "demo",\n'
                '  "dependencies": {"express": "^5.0.0"},\n'
                '  "devDependencies": {"vitest": "^2.0.0"}\n'
                "}\n"
            ),
            "package-lock.json": "{}\n",
        },
    )

    assert "## Environment Setup" in md
    assert "- Ecosystem: Node.js" in md
    assert "- Detected from: `package.json`" in md
    assert "- Prepare command: `npm install`" in md
    assert "`express ^5.0.0`" in md
    assert "`vitest ^2.0.0`" in md


def test_render_environment_setup_for_rust_cargo_toml(tmp_path: Path) -> None:
    md = _render_for_files(
        tmp_path / "repo",
        {
            "src/main.rs": "fn main() {}\n",
            "Cargo.toml": (
                "[package]\n"
                'name = "demo"\n'
                'version = "0.1.0"\n'
                'edition = "2021"\n'
                "\n"
                "[dependencies]\n"
                'serde = "1.0"\n'
            ),
        },
    )

    assert "## Environment Setup" in md
    assert "- Ecosystem: Rust" in md
    assert "- Detected from: `Cargo.toml`" in md
    assert "- Prepare command: `cargo fetch`" in md
    assert "`serde 1.0`" in md


def test_render_environment_setup_for_go_mod(tmp_path: Path) -> None:
    md = _render_for_files(
        tmp_path / "repo",
        {
            "main.go": "package main\nfunc main() {}\n",
            "go.mod": (
                "module example.com/demo\n\n"
                "go 1.22\n\n"
                "require github.com/spf13/cobra v1.8.0\n"
            ),
        },
    )

    assert "## Environment Setup" in md
    assert "- Ecosystem: Go" in md
    assert "- Detected from: `go.mod`" in md
    assert "- Prepare command: `go mod download`" in md
    assert "`github.com/spf13/cobra v1.8.0`" in md
