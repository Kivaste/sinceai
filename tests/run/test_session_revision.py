"""CLI seam: a cached real-CLI release must not outlive its test-session HEAD.

Failure row: build session release -> commit in a temporary checkout -> later
full verification is stopped with an explicit session-drift error, not a
misleading toolRevision mismatch. A planted revision file cannot bless drift.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_head_movement_is_reported_before_cached_release_verification(tmp_path):
    """Seam: real run/verify CLI, exercised by an isolated pytest session."""
    checkout = tmp_path / "checkout"
    tests = checkout / "tests"
    run = tests / "run"
    run.mkdir(parents=True)
    shutil.copytree(ROOT / "src", checkout / "src")
    shutil.copytree(ROOT / "tests" / "fixtures" / "minikit", tests / "fixtures" / "minikit")
    for name in ("conftest.py", "slow_tests.txt"):
        shutil.copyfile(ROOT / "tests" / name, tests / name)
    for name in ("conftest.py", "run_helpers.py"):
        shutil.copyfile(ROOT / "tests" / "run" / name, run / name)
    shutil.copyfile(ROOT / "pyproject.toml", checkout / "pyproject.toml")
    # Inherited Git overrides must never redirect these commits to the caller's checkout.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(PYTHONPATH=str(checkout / "src"), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    for args in (("init",), ("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "commit", "--allow-empty", "-m", "initial revision")):
        subprocess.run(["git", *args], cwd=checkout, env=env, capture_output=True, check=True)
    (run / "test_drift.py").write_text(
        "import subprocess\n"
        "from pathlib import Path\n"
        "from run_helpers import cli\n"
        "def test_build_then_move_head(released):\n"
        "    kit, out, proc = released\n"
        "    assert proc.returncode == 0, proc.stdout + proc.stderr\n"
        "    root = Path(__file__).resolve().parents[2]\n"
        "    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',\n"
        "                    'commit', '--allow-empty', '-m', 'mid-session revision'],\n"
        "                   cwd=root, capture_output=True, check=True)\n"
        "    (root / 'tool_revision.txt').write_text(subprocess.check_output(\n"
        "        ['git', 'rev-parse', 'HEAD'], cwd=root, text=True), encoding='utf-8')\n"
        "def test_verify_cached_release(released):\n"
        "    kit, out, proc = released\n"
        "    result = cli('verify', '--full', '--kit', str(kit), str(out))\n"
        "    assert result.returncode == 0, result.stdout + result.stderr\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/run/test_drift.py", "-q", "-p", "no:cacheprovider"],
        cwd=checkout, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "1 passed" in output, output  # the real release was built and the commit actually happened
    assert "HEAD moved during the test session" in output, output
    assert "ERROR tests/run/test_drift.py::test_verify_cached_release" in output, output
    assert "toolRevision: mismatch" not in output, output
    assert "FAILED tests/run/test_drift.py::test_verify_cached_release" not in output, output
