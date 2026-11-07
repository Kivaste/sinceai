"""Real monitor CLI against synthetic Git repos; only the OpenCode API is stubbed."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows monitor")
@pytest.mark.parametrize("case", ["planted", "git-failure", "identity", "snapshot", "delivery", "unicode"])
def test_main_checkout_write_monitor(case):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(root / "scripts/overnight/test-main-checkout-writes.ps1"), "-Case", case,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {case}:" in result.stdout
