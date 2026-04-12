from __future__ import annotations

import subprocess
import sys


def test_python_m_codecrate_version_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codecrate", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("codecrate ")
