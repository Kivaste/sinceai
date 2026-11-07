"""Exercise the affected-tests CLI with real Git, PowerShell and pytest.

Rules / failure rows (the issue's agreed seam is print mode and real -Run):
* A fixture change selects tests as ONE argument, not its individual characters.
* A package-only change selects its mapped directory as ONE argument.
* A changed test file remains ONE argument; a slow test is not executed.
* A linked script checkout ignores planted Python and uses Git's shared checkout.
* A missing shared interpreter fails closed even when a linked interpreter exists.
* Pytest failure and empty collection keep their nonzero exit status.
* Main checkouts are refused before selection, regardless of path spelling.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "overnight" / "affected-tests.ps1"
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
    # The production script uses a shared venv identified through Git.
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
def shared_repo(tmp_path: Path) -> Path:
    # Spaces also exercise native argument forwarding and -Worktree resolution.
    repo = tmp_path / "tiny worktree"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, "tests/scaffold/test_tiny.py", "def test_fast():\n    assert True\n")
    commit(repo)
    return repo


@pytest.fixture
def repo(shared_repo: Path, tmp_path: Path) -> Path:
    linked = tmp_path / "selected linked worktree"
    git(shared_repo, "worktree", "add", "-b", "ticket/selected", str(linked), "HEAD")
    return linked


def invoke(
    repo: Path, *, run: bool = False, script: Path = SCRIPT,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONUTF8="1", TZ="UTC")
    env["PYTHONPYCACHEPREFIX"] = str(Path(env["LOCALAPPDATA"]) / "sinceai-pycache")
    return subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
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


@pytest.fixture
def linked_script_repo(shared_repo: Path, tmp_path: Path) -> tuple[Path, Path]:
    repo = shared_repo
    write(repo, "scripts/overnight/affected-tests.ps1", SCRIPT.read_text(encoding="utf-8"))
    commit(repo)
    linked = tmp_path / "linked worktree"
    git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    planted = linked / ".venv" / "Scripts" / "python.exe"
    planted.parent.mkdir(parents=True)
    # A real executable that exits successfully without importing or running pytest.
    subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "Add-Type -TypeDefinition 'public class FakePython { "
            "public static int Main(string[] args) { return 0; } }' "
            "-OutputType ConsoleApplication -OutputAssembly $env:PLANTED_PYTHON",
        ],
        env=dict(os.environ, PLANTED_PYTHON=str(planted)),
        check=True, capture_output=True, text=True, timeout=60,
    )
    return repo, linked


def test_linked_worktree_ignores_planted_interpreter(
    linked_script_repo: tuple[Path, Path],
) -> None:
    """Rule: Git identity wins; planted exit-0 Python must not suppress pytest."""
    shared, linked = linked_script_repo
    shared_venv = shared / ".venv"
    venv.EnvBuilder(with_pip=False).create(shared_venv)
    # Reuse installed dependencies without installing anything into either venv.
    write(shared_venv, "Lib/site-packages/shared.pth", sysconfig.get_path("purelib") + "\n")
    ran = invoke(linked, run=True, script=linked / "scripts/overnight/affected-tests.ps1")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "1 passed" in ran.stdout, ran.stdout + ran.stderr
    assert f"interpreter: {shared_venv / 'Scripts' / 'python.exe'}" in ran.stdout
    main = invoke(shared, run=True, script=shared / "scripts/overnight/affected-tests.ps1")
    assert main.returncode == 2, main.stdout + main.stderr
    assert "main checkout" in main.stdout
    assert "interpreter:" not in main.stdout
    assert "1 passed" not in main.stdout


def test_missing_shared_interpreter_does_not_use_planted_fallback(
    linked_script_repo: tuple[Path, Path],
) -> None:
    """Rule: missing identity-selected Python is failure, never fallback success."""
    shared, linked = linked_script_repo
    ran = invoke(linked, run=True, script=linked / "scripts/overnight/affected-tests.ps1")
    assert ran.returncode != 0, ran.stdout + ran.stderr
    assert f"interpreter: {shared / '.venv' / 'Scripts' / 'python.exe'}" in ran.stdout
    assert "1 passed" not in ran.stdout
