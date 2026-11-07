"""Done-report CLI seam: real PS 5.1 script, local Git, UTF-8 gh process boundary."""

from __future__ import annotations

import json
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
def done_report_cli(tmp_path):
    # Isolate git fetch/head checks from the network, without replacing any check.
    repo = tmp_path / "repo"
    script = repo / "scripts" / "overnight" / "check-done-report.ps1"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts" / "overnight" / script.name, script)

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-q", "--allow-empty", "-m", "synthetic",
    )
    head = git("rev-parse", "HEAD")
    git("remote", "add", "origin", str(repo))
    git("update-ref", "refs/remotes/origin/ticket/synthetic", head)
    git("update-ref", "refs/remotes/origin/integration/pets-release", head)

    body = f"""## Done-report
- Issue: #102
- Branch: ticket/synthetic
- Head: {head}
- Implementer: openai/gpt-6.1-sol
### TDD evidence
- Rule: synthetic check refuses incomplete reports
  - Red: `synthetic red` ARROW exit 1
  - Green: `synthetic green` ARROW exit 0
### Affected tests
- `affected-tests.ps1 -Run` ARROW exit 0
### Real-run evidence
- Revision: {head}
- Artefacts: {tmp_path}
- Outcome: synthetic script gate exit 0
### Reviews
- Standards: xai/grok-4.7 APPROVE @ {head}
- Spec: claude-agent/sonnet APPROVE @ {head}
### Unknowns
- none
"""
    payload = tmp_path / "issue.json"
    fake_process = tmp_path / "fake_gh.py"
    fake_process.write_text(
        "import pathlib, sys\n"
        f"sys.stdout.buffer.write(pathlib.Path({str(payload)!r}).read_bytes())\n",
        encoding="utf-8",
    )
    gh = tmp_path / "gh.cmd"
    gh.write_text(f'@echo off\n"{sys.executable}" "{fake_process}"\n', encoding="ascii")
    runner = tmp_path / "run.ps1"
    # Reproduce the non-UTF-8 console code page even on UTF-8 developer machines.
    runner.write_text(
        "param([string]$Script, [string]$BodyFile, [string]$GhExe)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [Text.Encoding]::GetEncoding(1252)\n"
        "if ($BodyFile) { & $Script -Issue 102 -BodyFile $BodyFile }\n"
        "else { & $Script -Issue 102 -GhExe $GhExe }\n"
        "$result = $LASTEXITCODE\n"
        "if ([Console]::OutputEncoding.CodePage -ne 1252) { throw 'Console encoding leaked' }\n"
        "exit $result\n",
        encoding="ascii",
    )

    def run(report, *, via_gh, unreadable=False):
        body_file = tmp_path / "body.md"
        body_file.write_text(report, encoding="utf-8")
        payload.write_text(
            json.dumps(
                {"number": 102, "title": "synthetic", "labels": [], "comments": [{"body": report}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if unreadable:
            gh.write_text("@echo off\nexit /b 1\n", encoding="ascii")
        env = dict(os.environ, PYTHONUTF8="1", TZ="UTC")
        env["PYTHONPYCACHEPREFIX"] = str(Path(env["LOCALAPPDATA"]) / "sinceai-pycache")
        return subprocess.run(
            [
                POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner),
                str(script), *(["-GhExe", str(gh)] if via_gh else ["-BodyFile", str(body_file)]),
            ],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=60,
        )

    return body, run


@pytest.mark.parametrize("arrow", ["\u2192", "->"], ids=["unicode", "ascii"])
def test_valid_report_passes_body_file_and_gh(done_report_cli, arrow):
    body, run = done_report_cli
    report = body.replace("ARROW", arrow)
    for via_gh in (False, True):
        result = run(report, via_gh=via_gh)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS #102" in result.stdout


@pytest.mark.parametrize("arrow", ["\u2192", "->"], ids=["unicode", "ascii"])
def test_missing_green_fails_even_with_a_planted_valid_report(done_report_cli, tmp_path, arrow):
    body, run = done_report_cli
    report = body.replace("ARROW", arrow)
    (tmp_path / "planted-valid-report.md").write_text(report, encoding="utf-8")
    missing_green = "\n".join(line for line in report.splitlines() if "Green:" not in line)
    for via_gh in (False, True):
        result = run(missing_green, via_gh=via_gh)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "TDD evidence: no green run (exit 0)" in result.stdout
        assert "1 evidence gap(s)" in result.stdout


def test_unreadable_issue_is_unknown_not_a_pass(done_report_cli):
    body, run = done_report_cli
    result = run(body.replace("ARROW", "->"), via_gh=True, unreadable=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "UNKNOWN: could not read issue #102" in result.stdout
