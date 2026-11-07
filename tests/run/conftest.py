"""Run-command fixtures (synthetic rows only)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_helpers import build_kit, cli, coarse_qis, run_args

from pets_release.verify import current_tool_revision


@pytest.fixture(scope="session", autouse=True)
def session_tool_revision():
    """Pin this worker's revision before any run-command fixture is built."""
    revision = current_tool_revision()
    if revision is None:
        pytest.fail("cannot pin HEAD for the test session", pytrace=False)
    return revision


@pytest.fixture(autouse=True)
def _stable_session_head(session_tool_revision):
    """Never diagnose a stale cached release as a production verify failure."""
    def check():
        current = current_tool_revision()
        if current != session_tool_revision:
            pytest.fail(
                "HEAD moved during the test session: "
                f"pinned {session_tool_revision}, current {current or 'unavailable'}. "
                "Keep this worktree unchanged and restart pytest.",
                pytrace=False,
            )

    check()
    yield
    check()


@pytest.fixture(scope="session")
def released(tmp_path_factory, session_tool_revision):
    """One real-CLI fixture release shared by the read-only tests."""
    base = tmp_path_factory.mktemp("run")
    kit = build_kit(base / "kit", coarse_qis)
    out = base / "out" / "rel"
    proc = cli(*run_args(kit, out))
    return kit, out, proc
