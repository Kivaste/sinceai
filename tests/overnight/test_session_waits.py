"""Production monitor CLI against synthetic OpenCode and OS process boundaries."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows monitor")
@pytest.mark.parametrize("case", ["idle", "wait", "long-waits", "workers", "discovery", "reports", "unknown", "scope", "unreadable", "mapped", "delivery", "pagination"])
def test_session_wait_monitor(case):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(root / "scripts/overnight/test-session-waits.ps1"), "-Case", case,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {case}:" in result.stdout
