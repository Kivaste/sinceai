"""Helpers shared by the submission tests (synthetic rows only)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "run"))

from run_helpers import TEST_KEY, build_kit, cli, coarse_qis, run_args  # noqa: F401


def submission(*args, extra=None):
    return cli("submission", *args, extra=extra)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True)
