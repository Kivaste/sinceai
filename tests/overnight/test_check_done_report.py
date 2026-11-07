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

    git("init", "-q", "-b", "main")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-q", "--allow-empty", "-m", "synthetic baseline",
    )
    baseline = git("rev-parse", "HEAD")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-q", "--allow-empty", "-m", "synthetic",
    )
    head = git("rev-parse", "HEAD")
    git("remote", "add", "origin", str(repo))
    git("update-ref", "refs/remotes/origin/ticket/synthetic", head)
    git("update-ref", "refs/remotes/origin/integration/pets-release", baseline)
    linked = tmp_path / "linked tree"
    git("worktree", "add", "-q", "-b", "ticket/synthetic", str(linked))

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
        "param([string]$Script, [string]$BodyFile, [string]$GhExe, [switch]$TestMode)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [Text.Encoding]::GetEncoding(1252)\n"
        "$mode = @{}; if ($TestMode) { $mode.TestMode = $true }\n"
        "if ($BodyFile) { & $Script -Issue 102 -BodyFile $BodyFile @mode }\n"
        "else { & $Script -Issue 102 -GhExe $GhExe @mode }\n"
        "$result = $LASTEXITCODE\n"
        "if ([Console]::OutputEncoding.CodePage -ne 1252) { throw 'Console encoding leaked' }\n"
        "exit $result\n",
        encoding="ascii",
    )

    def run(report, *, via_gh, unreadable=False, location="linked", merged=False, test_mode=True):
        if location == "main":
            git("-C", str(linked), "checkout", "-q", "--detach")
            git("checkout", "-q", "ticket/synthetic")
        elif location == "absent":
            git("worktree", "remove", str(linked))
        elif location == "missing":
            shutil.rmtree(linked)
        elif location == "planted-main":
            (linked / ".git").unlink()  # Git marks this file hidden on Windows.
            (linked / ".git").write_text(f"gitdir: {repo / '.git'}\n", encoding="utf-8")
        if merged:
            git("update-ref", "refs/remotes/origin/integration/pets-release", head)
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
                *(["-TestMode"] if test_mode else []),
            ],
            check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=60,
        )

    return body, run


def test_gh_substitute_requires_explicit_test_mode_despite_planted_file(done_report_cli, tmp_path):
    body, run = done_report_cli
    (tmp_path / "repo" / ".test-mode").write_text("enabled", encoding="ascii")
    result = run(body.replace("ARROW", "->"), via_gh=True, test_mode=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "UNKNOWN: -GhExe requires -TestMode" in result.stdout
    assert "PASS #102" not in result.stdout


def test_body_substitute_requires_explicit_test_mode_despite_planted_file(done_report_cli, tmp_path):
    body, run = done_report_cli
    (tmp_path / "repo" / ".test-mode").write_text("enabled", encoding="ascii")
    result = run(body.replace("ARROW", "->"), via_gh=False, test_mode=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "UNKNOWN: -BodyFile requires -TestMode" in result.stdout
    assert "PASS #102" not in result.stdout


@pytest.mark.parametrize("arrow", ["\u2192", "->"], ids=["unicode", "ascii"])
@pytest.mark.parametrize("via_gh", [False, True], ids=["body-file", "gh"])
def test_complete_substitute_report_is_not_a_close_pass(done_report_cli, arrow, via_gh):
    body, run = done_report_cli
    report = body.replace("ARROW", arrow)
    result = run(report, via_gh=via_gh)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "SUBSTITUTE-ONLY: evidence complete, not a close pass" in result.stdout
    assert "PASS #" not in result.stdout


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


def test_non_ticket_branch_fails_even_with_complete_evidence(done_report_cli):
    body, run = done_report_cli
    report = body.replace("ARROW", "->").replace("Branch: ticket/synthetic", "Branch: main")
    result = run(report, via_gh=False, merged=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Branch: must match ticket/*" in result.stdout


@pytest.mark.parametrize("location,merged", [
    ("main", False), ("absent", False), ("main", True),
    ("missing", True), ("planted-main", False),
])
def test_active_ticket_requires_a_linked_worktree(done_report_cli, tmp_path, location, merged):
    body, run = done_report_cli
    # A planted .git file and complete report are not proof of a branch checkout.
    planted = tmp_path / "planted-linked-tree"
    planted.mkdir()
    shutil.copyfile(tmp_path / "linked tree" / ".git", planted / ".git")
    result = run(body.replace("ARROW", "->"), via_gh=False, location=location, merged=merged)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Branch: ticket/synthetic must be checked out in a linked worktree" in result.stdout


def test_merged_ticket_removed_worktree_still_cannot_close_from_substitute(done_report_cli):
    body, run = done_report_cli
    result = run(body.replace("ARROW", "->"), via_gh=False, location="absent", merged=True)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "SUBSTITUTE-ONLY: evidence complete, not a close pass" in result.stdout
    assert "PASS #" not in result.stdout
