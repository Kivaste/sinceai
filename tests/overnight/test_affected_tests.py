"""Affected-tests CLI seam: real script and Git identities, no real main checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell 5.1 required")


@pytest.fixture
def affected_cli(tmp_path):
    repo = tmp_path / "MainRepo"
    script = repo / "scripts" / "overnight" / "affected-tests.ps1"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts" / "overnight" / script.name, script)
    smoke = repo / "tests" / "scaffold" / "test_smoke.py"
    smoke.parent.mkdir(parents=True)
    smoke.write_text("def test_synthetic_smoke():\n    assert 2 + 2 == 4\n", encoding="ascii")

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("add", "scripts", "tests")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-q", "-m", "synthetic")
    linked = tmp_path / "LinkedTree"
    git("worktree", "add", "-q", "-b", "ticket/synthetic", str(linked))
    # The production script uses a shared venv next to its script checkout.
    # Point that filesystem boundary at the actual pytest environment, not a stub.
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(repo / ".venv"), str(Path(sys.prefix))],
        check=True, capture_output=True,
    )

    def run(worktree, *, execute=False):
        env = dict(os.environ, PYTHONUTF8="1", TZ="UTC", PYTHONPATH="src")
        env["PYTHONPYCACHEPREFIX"] = str(Path(env["LOCALAPPDATA"]) / "sinceai-pycache")
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-Worktree", str(worktree), "-Base", "HEAD", *(["-Run"] if execute else [])],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=90,
        )

    return repo, linked, run


@pytest.mark.parametrize("variant", ["native", "upper", "forward"])
@pytest.mark.parametrize("execute", [False, True], ids=["select", "run"])
def test_main_checkout_is_refused_before_selection_or_tests(affected_cli, variant, execute):
    repo, linked, run = affected_cli
    # A real linked worktree exists; a path spelling must not turn the main into it.
    assert (linked / ".git").is_file()
    path = {"native": str(repo), "upper": str(repo).upper(), "forward": repo.as_posix()}[variant]
    result = run(path, execute=execute)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "main checkout" in result.stdout.lower()
    assert "linked worktree" in result.stdout.lower()
    assert "changed files:" not in result.stdout
    assert "passed" not in result.stdout


@pytest.mark.parametrize("variant", ["native", "upper", "forward"])
def test_linked_worktree_still_runs_real_selected_tests(affected_cli, variant):
    _, linked, run = affected_cli
    path = {"native": str(linked), "upper": str(linked).upper(), "forward": linked.as_posix()}[variant]
    result = run(path, execute=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "selection: tests/scaffold" in result.stdout
    assert "1 passed" in result.stdout


def test_planted_git_marker_in_non_repository_is_not_identity(affected_cli, tmp_path):
    _, _, run = affected_cli
    planted = tmp_path / "not-a-repository"
    planted.mkdir()
    (planted / ".git").write_text("gitdir: missing-git-dir\n", encoding="ascii")
    result = run(planted, execute=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "cannot establish linked worktree identity" in result.stdout
    assert "changed files:" not in result.stdout
