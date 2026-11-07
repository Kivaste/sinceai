"""Run-command fixtures (synthetic rows only)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_helpers import build_kit, cli, coarse_qis, run_args


@pytest.fixture(scope="session")
def released(tmp_path_factory):
    """One real-CLI fixture release shared by the read-only tests."""
    base = tmp_path_factory.mktemp("run")
    kit = build_kit(base / "kit", coarse_qis)
    out = base / "out" / "rel"
    proc = cli(*run_args(kit, out))
    return kit, out, proc
