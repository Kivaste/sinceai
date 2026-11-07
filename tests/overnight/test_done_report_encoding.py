"""Close-gate CLI regressions; synthetic reports and local Git only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="requires Windows PowerShell 5.1")


@pytest.fixture
def close_gate(tmp_path):
    # Install the unmodified production script in an isolated real Git repo so
    # its head checks run without fetching from GitHub or touching live refs.
    repo = tmp_path / "repo"
    script = repo / "scripts" / "overnight" / "check-done-report.ps1"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts" / "overnight" / script.name, script)
    helper = ROOT / "scripts" / "overnight" / "check-release-evidence.py"
    shutil.copyfile(helper, script.with_name(helper.name))
    env = os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], env=env, check=True,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        ).stdout.strip()

    git("init", "-q", "-b", "synthetic")
    git("-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid",
        "commit", "-q", "--allow-empty", "-m", "synthetic test head")
    head = git("rev-parse", "HEAD")
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", str(origin))
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "origin", "synthetic", "HEAD:integration/pets-release")

    # cmd's TYPE writes the fixture's raw UTF-8 bytes, like native gh does.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh.cmd").write_text(
        '@echo off\r\ntype "%DONE_REPORT_JSON%"\r\n', encoding="ascii",
    )
    body_file = tmp_path / "report.md"
    json_file = tmp_path / "issue.json"
    env.update(
        PATH=os.pathsep.join((str(bin_dir), str(Path(sys.executable).parent), env["PATH"])),
        CLOSE_GATE=str(script), DONE_REPORT_BODY=str(body_file), DONE_REPORT_JSON=str(json_file),
    )
    report = f"""## Done-report
- Branch: synthetic
- Head: {head}
- Implementer: openai/gpt-6.1-sol
### TDD evidence
- Rule: Synthetic close-gate encoding regression.
  - Red: `synthetic-check` → exit 1
  - Green: `synthetic-check` → exit 0
### Affected tests
- `affected-tests.ps1 -Run` → exit 0
### Real-run evidence
- Revision: {head}
- Artefacts: {repo}
- Outcome: N/A: test-only encoding fixture
### Reviews
- Standards: xai/grok-4.7 APPROVE @ {head}
- Spec: claude-agent/sonnet APPROVE @ {head}
### Unknowns
- none
"""

    def run(mode, body=report):
        body_file.write_text(body, encoding="utf-8")
        json_file.write_text(json.dumps({
            "number": 122, "title": "Synthetic encoding fixture", "labels": [],
            "comments": [{"body": body}],
        }, ensure_ascii=False), encoding="utf-8")
        command = """
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'requires Windows PowerShell 5.1' }
[Console]::OutputEncoding = [Text.Encoding]::GetEncoding(437)
"""
        command += "& $env:CLOSE_GATE -Issue 122"
        if mode == "body-file":
            command += " -BodyFile $env:DONE_REPORT_BODY"
        command += """
$code = $LASTEXITCODE
if ([Console]::OutputEncoding.CodePage -ne 437) { throw 'console encoding was not restored' }
exit $code
"""
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=False, cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
        )

    return run, report


@pytest.mark.parametrize("mode", ["body-file", "gh"])
def test_unicode_arrow_report_is_accepted_under_oem_console(close_gate, mode):
    """Seam: production close-gate CLI, with real Git and external gh bytes."""
    run, _ = close_gate
    result = run(mode)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS #122" in result.stdout


@pytest.mark.parametrize("mode", ["body-file", "gh"])
@pytest.mark.parametrize("green_line", ["", "  - Green: Same command → exit 0\n"])
def test_report_without_full_green_command_is_still_rejected(close_gate, mode, green_line):
    """Seam: close-gate CLI must not accept absent or abbreviated Green evidence."""
    run, report = close_gate
    result = run(mode, report.replace("  - Green: `synthetic-check` → exit 0\n", green_line))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 evidence gap(s)" in result.stdout
    assert "TDD evidence: no green run (exit 0)" in result.stdout
