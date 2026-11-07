"""Evidence producer CLI -> real release CLI -> strict close-gate reader.

Rules / failure rows (synthetic kit only):
  successful run + both verifies -> checker accepts revision-bound evidence
  verify exits 7 -> exact nonzero recorded, nonzero producer exit, worktree removed
  child prints its key -> key removed before any log/output is written
  planted output/worktree -> refused without borrowing or deleting planted evidence
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import cli_env
from tests.run.run_helpers import build_kit, coarse_qis

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/overnight/release-evidence.ps1"
CHECKER = ROOT / "scripts/overnight/check-release-evidence.py"
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows evidence runner")


@pytest.fixture
def evidence_cli(tmp_path):
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    kit = build_kit(tmp_path / "kit", coarse_qis)
    out = tmp_path / "evidence"
    worktrees = tmp_path / "worktrees"

    def run(*extra, python=sys.executable):
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
             "-Sha", sha, "-Out", str(out), "-Kit", str(kit),
             "-Python", str(python), "-WorktreeRoot", str(worktrees), *extra],
            cwd=ROOT, env=cli_env(), capture_output=True, text=True, encoding="utf-8",
            timeout=180, check=False,
        )

    return run, sha, out, worktrees


def check(out, sha):
    return subprocess.run(
        [sys.executable, str(CHECKER), str(out), sha,
         "verify (limited) exit 0; verify --full exit 0"],
        cwd=ROOT, env=cli_env(), capture_output=True, text=True, encoding="utf-8", check=False,
    )


def test_real_cli_evidence_is_accepted_and_worktree_removed(evidence_cli):
    run, sha, out, worktrees = evidence_cli
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    accepted = check(out, sha)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    text = (out / "release-evidence.log").read_text(encoding="utf-8-sig")
    assert text.startswith(f"revision={sha}\n")
    assert "RELEASED: health-s1 (" in text
    assert "verify exit=0\n" in text
    assert "verify-full exit=0\n" in text
    assert not (worktrees / f"evidence-{sha[:7]}").exists()
    registered = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=ROOT, text=True)
    assert worktrees.as_posix() not in registered.replace("\\", "/")
    manifest = json.loads((out / "health-s1/privacy_manifest.json").read_text(encoding="utf-8"))
    assert {p.name for p in (out / "health-s1").iterdir()} == {
        "privacy_manifest.json", *manifest["bindings"]["files"],
    }
    assert {p.name for p in (out / "health-s1.scoring").iterdir()} == {"gate_report.json"}
    assert not (out / "health-s1.measure").exists()
    assert not list(out.rglob("rowmap_*.csv"))


def test_failing_verify_records_actual_exit_and_removes_worktree(evidence_cli, tmp_path):
    """CLI boundary injection fails only limited verify; the release is real."""
    run, sha, out, worktrees = evidence_cli
    wrapper = tmp_path / "failing-python.ps1"
    wrapper.write_text(
        "if ($args -contains 'verify' -and $args -notcontains '--full') { exit 7 }\n"
        f"& '{sys.executable}' @args\nexit $LASTEXITCODE\n", encoding="utf-8",
    )
    result = run(python=wrapper)
    assert result.returncode != 0, result.stdout + result.stderr
    text = (out / "release-evidence.log").read_text(encoding="utf-8-sig")
    assert "verify exit=7\n" in text
    assert "verify-full exit=0\n" in text
    assert check(out, sha).returncode == 1
    assert not (worktrees / f"evidence-{sha[:7]}").exists()


def test_key_is_scrubbed_before_any_output_is_written(evidence_cli, tmp_path):
    """A hostile native boundary echoes key encodings; never persist any of them."""
    run, _, out, _ = evidence_cli
    wrapper = tmp_path / "echoing-python.ps1"
    wrapper.write_text(
        "$key = $env:PETS_HMAC_KEY\n"
        "$forms = @($key, $key.ToUpperInvariant(), "
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($key)))\n"
        "foreach ($form in $forms) { Write-Output ('key-canary=' + $form) }\n"
        # The scanner holds the real fresh key only in process memory. It never
        # returns it to pytest or writes it to a fixture / diagnostic file.
        "if ($args -contains '--full') {\n"
        "  $folder = Split-Path -Parent $args[-1]\n"
        "  foreach ($file in Get-ChildItem -LiteralPath $folder -Recurse -File) {\n"
        "    $text = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($file.FullName))\n"
        "    foreach ($form in $forms) { if ($text.Contains($form)) { exit 9 } }\n"
        "  }\n"
        "  Write-Output 'key-scan=clean'\n"
        "}\n"
        f"& '{sys.executable}' @args\nexit $LASTEXITCODE\n", encoding="utf-8",
    )
    result = run(python=wrapper)
    code = result.returncode  # Do not let pytest print the native output on a red.
    assert code == 0, "key scanner or real CLI failed (output withheld)"
    text = (out / "release-evidence.log").read_text(encoding="utf-8-sig")
    assert "key-scan=clean" in text
    for output in (result.stdout, text):
        canaries = [line for line in output.splitlines() if line.startswith("key-canary=")]
        assert canaries == ["key-canary=[REDACTED]"] * 9, "key canary not fully redacted"


@pytest.mark.parametrize("planted", ["output", "worktree"])
def test_planted_paths_are_not_reused_or_removed(evidence_cli, planted):
    """A planted success log or worktree cannot stand in for this invocation."""
    run, sha, out, worktrees = evidence_cli
    folder = out if planted == "output" else worktrees / f"evidence-{sha[:7]}"
    folder.mkdir(parents=True)
    marker = folder / "planted.log"
    content = f"revision={sha}\nverify exit=0\nverify-full exit=0\n"
    marker.write_text(content, encoding="utf-8")
    result = run()
    assert result.returncode != 0
    assert marker.read_text(encoding="utf-8") == content
    assert not (out / "health-s1/privacy_manifest.json").exists()


def test_failing_run_is_not_reported_as_verified(evidence_cli, tmp_path):
    run, sha, out, worktrees = evidence_cli
    wrapper = tmp_path / "failed-run.ps1"
    wrapper.write_text("exit 13\n", encoding="utf-8")
    result = run(python=wrapper)
    assert result.returncode != 0
    text = (out / "release-evidence.log").read_text(encoding="utf-8-sig")
    assert "run exit=13\n" in text
    assert "verify exit=" not in text
    assert "verify-full exit=" not in text
    assert not (worktrees / f"evidence-{sha[:7]}").exists()
