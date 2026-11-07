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
    "Path(str({main!r}))",
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


@pytest.mark.parametrize("workers", [False, True], ids=["serial", "xdist"])
@pytest.mark.parametrize("checkout", ["main", "linked"])
@pytest.mark.parametrize("filename", ["new file.txt", "tracked.txt"])
def test_new_dirty_paths_fail_once_in_controller(checkouts, workers, checkout, filename):
    main, worktree = checkouts
    target = (main if checkout == "main" else worktree) / filename
    args = ("-p", "xdist.plugin", "-n", "2") if workers else ()
    result = run_pytest(worktree,
        "from pathlib import Path\n"
        "def test_sample():\n"
        f"    Path({str(target)!r}).write_text('synthetic change')\n",
        *args, cwd=main)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("checkout write guard: new dirty paths") == 1
    assert filename in result.stdout


@pytest.mark.parametrize("workers", [False, True], ids=["serial", "xdist"])
def test_existing_dirty_paths_and_pytest_tmp_are_allowed(checkouts, workers):
    main, worktree = checkouts
    for root in (main, worktree):
        (root / "existing untracked.txt").write_text("baseline", encoding="utf-8")
        (root / "tracked.txt").write_text("baseline modification", encoding="utf-8")
    args = ("-p", "xdist.plugin", "-n", "2") if workers else ()
    result = run_pytest(worktree,
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "def test_sample(tmp_path):\n"
        "    (tmp_path / 'allowed.txt').write_text('synthetic')\n"
        "    assert (ROOT / 'tracked.txt').is_file()\n", *args, cwd=main)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_unassigned_parent_resolution_cannot_escape_checkout(checkouts):
    _, worktree = checkouts
    result = run_pytest(worktree,
        "from pathlib import Path\n"
        "def test_sample():\n"
        "    assert Path(__file__).resolve().parents[2].is_dir()\n")
    assert result.returncode != 0
    assert "checkout root guard" in result.stdout + result.stderr


def test_missing_git_identity_fails_closed(checkouts):
    _, worktree = checkouts
    # Remove only this synthetic worktree's Git pointer, never the real checkout's.
    (worktree / ".git").unlink()
    result = run_pytest(worktree, "def test_sample(): pass\n")
    assert result.returncode != 0
    assert "Git identity/status unavailable" in result.stdout + result.stderr
