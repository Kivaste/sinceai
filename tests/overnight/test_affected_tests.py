"""Affected-test selection through the real PowerShell CLI, never the product suite."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows selector")
@pytest.mark.parametrize("case", ["planted", "missing", "marker", "tooling"])
def test_affected_test_selection(case):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(root / "scripts/overnight/test-affected-tests.ps1"), "-Case", case,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {case}:" in result.stdout
