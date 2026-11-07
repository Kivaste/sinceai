"""Checkout isolation through the real pytest CLI, using disposable Git repos."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )


@pytest.fixture
def checkouts(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    git(main, "config", "user.email", "synthetic@example.invalid")
    git(main, "config", "user.name", "Synthetic test")
    tests = main / "tests"
    tests.mkdir()
    shutil.copyfile(ROOT / "tests" / "conftest.py", tests / "conftest.py")
    (tests / "slow_tests.txt").write_text("", encoding="utf-8")
    (tests / "test_sample.py").write_text("def test_sample(): pass\n", encoding="utf-8")
    (main / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    (main / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    kit: real kit\n    slow: heavy\n", encoding="utf-8",
    )
    git(main, "add", ".")
    git(main, "commit", "-qm", "Synthetic baseline")
    worktree = tmp_path / "linked"
    git(main, "worktree", "add", "--detach", "-q", str(worktree))
    return main, worktree


def run_pytest(worktree, source, *args, cwd=None):
    (worktree / "tests" / "test_sample.py").write_text(source, encoding="utf-8")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONUTF8="1", TZ="UTC")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--basetemp", str(worktree / ".test-tmp"), *args, str(worktree / "tests")],
        cwd=cwd or worktree, env=env, capture_output=True, text=True,
        encoding="utf-8", check=False, timeout=120,
    )


def test_planted_other_checkout_file_fails(checkouts):
    main, worktree = checkouts
    result = run_pytest(worktree,
        "from pathlib import Path\n"
        "def test_sample():\n"
        f"    Path({str(main / 'planted.txt')!r}).write_text('synthetic')\n")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "checkout write guard" in result.stdout
    assert "planted.txt" in result.stdout


@pytest.mark.parametrize("resolution", [
    "Path({main!r})",
    "Path(__file__).resolve().parents[2]",
    "Path(__file__).resolve().parents[0]",
])
def test_wrong_repo_root_fails_before_test_body(checkouts, resolution):
    main, worktree = checkouts
    result = run_pytest(worktree,
        "from pathlib import Path\n"
        "def test_sample():\n"
        f"    ROOT = {resolution.format(main=str(main))}\n"
        "    raise AssertionError('body must not run')\n")
    assert result.returncode != 0
    assert "checkout root guard" in result.stdout + result.stderr
    assert "body must not run" not in result.stdout
