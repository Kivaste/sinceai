"""Exercise the affected-tests CLI with real Git, PowerShell and pytest.

Rules / failure rows (the issue's agreed seam is print mode and real -Run):
* A fixture change selects tests as ONE argument, not its individual characters.
* A package-only change selects its mapped directory as ONE argument.
* A changed test file remains ONE argument; a slow test is not executed.
* A linked script checkout without a venv uses its shared checkout's interpreter.
* Pytest failure and empty collection keep their nonzero exit status.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "overnight" / "affected-tests.ps1"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def write(repo: Path, name: str, content: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def commit(repo: Path) -> None:
    git(repo, "add", ".")
    git(
        repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "synthetic baseline",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # Spaces also exercise native argument forwarding and -Worktree resolution.
    repo = tmp_path / "tiny worktree"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, "tests/scaffold/test_tiny.py", "def test_fast():\n    assert True\n")
    commit(repo)
    return repo


def invoke(repo: Path, *, run: bool = False) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONUTF8="1", TZ="UTC")
    env["PYTHONPYCACHEPREFIX"] = str(Path(env["LOCALAPPDATA"]) / "sinceai-pycache")
    return subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Worktree", str(repo), "-Base", "HEAD", *(["-Run"] if run else []),
        ],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=90,
    )


def test_fixture_change_prints_and_runs_one_directory(repo: Path) -> None:
    write(repo, "tests/gen_fixtures/trigger.py", "# synthetic fixture change\n")
    printed = invoke(repo)
    assert printed.returncode == 0, printed.stdout + printed.stderr
    assert printed.stdout.strip() == "changed files: 1; selection: tests"

    ran = invoke(repo, run=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "1 passed" in ran.stdout


def test_package_only_change_uses_selected_worktree_source(repo: Path) -> None:
    write(repo, "src/pets_release/__init__.py", "")
    write(repo, "src/pets_release/tooling/__init__.py", "ENABLED = False\n")
    write(
        repo, "tests/tooling/test_package.py",
        "from pets_release.tooling import ENABLED\n"
        "def test_worktree_source():\n    assert ENABLED\n",
    )
    commit(repo)
    # The only difference is src/pets_release/<pkg>/, never a test file.
    write(repo, "src/pets_release/tooling/__init__.py", "ENABLED = True\n")
    printed = invoke(repo)
    assert printed.returncode == 0, printed.stdout + printed.stderr
    assert printed.stdout.strip() == "changed files: 1; selection: tests/tooling"
    ran = invoke(repo, run=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "1 passed" in ran.stdout


def test_single_changed_test_file_preserves_marker_expression(repo: Path) -> None:
    write(
        repo, "tests/scaffold/test_tiny.py",
        "import pytest\n"
        "def test_fast():\n    assert True\n"
        "@pytest.mark.slow\ndef test_slow():\n    assert False\n",
    )
    ran = invoke(repo, run=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "selection: tests/scaffold/test_tiny.py" in ran.stdout
    assert "1 passed" in ran.stdout


@pytest.mark.parametrize(
    ("content", "exit_code", "summary"),
    [
        ("def test_failure():\n    assert False\n", 1, "1 failed"),
        ("# No test functions collected.\n", 5, "no tests ran"),
    ],
    ids=["failed-test", "empty-collection"],
)
def test_pytest_nonzero_status_is_preserved(
    repo: Path, content: str, exit_code: int, summary: str,
) -> None:
    write(repo, "tests/scaffold/test_tiny.py", content)
    ran = invoke(repo, run=True)
    assert ran.returncode == exit_code, ran.stdout + ran.stderr
    assert summary in ran.stdout
