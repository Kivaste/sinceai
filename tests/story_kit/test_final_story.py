"""#103's approved docs seam: the final-text CLI, on synthetic docs/story/final/.

Rule: final text is complete, resolved and within the submission limits.
Failure rows: a placeholder, comment/claim marker, editorial note, description
heading, oversized name/tagline/description, missing or empty deliverable -> refuse.
This checks text readiness only, never privacy evidence or final-SHA claim truth.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "docs" / "story" / "check_final.py"
FINAL = ROOT / "docs" / "story" / "final"


@pytest.fixture
def final_text(tmp_path):
    folder = tmp_path / "docs" / "story" / "final"
    folder.mkdir(parents=True)
    for name, text in {
        "name.txt": "Purpose-First PETs",
        "tagline.txt": "Share only what the purpose needs.",
        "description.md": "A protected release with a privacy manifest. Residual risk: not measured.",
        "built-with.txt": "Python, pandas, NumPy, jsonschema, Jinja2",
        "pitch-4min.md": "Explain the sharing scenario and its residual risks.",
        "video-script.md": "Show only synthetic fixture material.",
        "SOURCES.md": "Synthetic readiness fixture only; not release evidence.",
    }.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def check(folder):
    env = {**os.environ, "PYTHONUTF8": "1", "TZ": "UTC"}
    return subprocess.run(
        [sys.executable, str(CHECKER), str(folder)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
    )


@pytest.mark.parametrize(("file", "planted", "diagnostic"), [
    ("description.md", "Recall {{manifest.measured.redaction.status}}", "unresolved placeholder"),
    ("description.md", "Recall {{manifest.measured.redaction.status", "unresolved placeholder"),
    ("pitch-4min.md", "<!-- IF #24 -->CS-S1<!-- END IF -->", "comment marker"),
    ("SOURCES.md", "<!-- source note -->", "comment marker"),
    ("video-script.md", "IF #117 show protected rows", "claim marker"),
    ("description.md", "TODO: fill after proof", "editorial note"),
    ("description.md", "# Submission description\nBody", "description heading"),
    ("name.txt", "x" * 81, "over limit"),
    ("tagline.txt", "x" * 141, "over limit"),
    ("description.md", "x" * 5001, "over limit"),
    ("built-with.txt", "", "empty file"),
])
def test_planted_unready_final_text_is_refused(final_text, file, planted, diagnostic):
    (final_text / file).write_text(planted, encoding="utf-8")
    result = check(final_text)
    assert result.returncode == 1, result.stdout + result.stderr
    assert diagnostic in result.stdout
    if planted:
        assert planted not in result.stdout, "diagnostics must not echo submission content"


def test_complete_resolved_final_text_at_exact_limits_passes(final_text):
    for name, limit in (("name.txt", 80), ("tagline.txt", 140), ("description.md", 5000)):
        (final_text / name).write_text("x" * limit, encoding="utf-8")
    result = check(final_text)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_final_deliverable_is_refused(final_text):
    (final_text / "SOURCES.md").unlink()
    result = check(final_text)
    assert result.returncode == 1
    assert "missing file: SOURCES.md" in result.stdout


def test_missing_final_folder_is_not_ready(tmp_path):
    result = check(tmp_path / "docs" / "story" / "final")
    assert result.returncode == 1
    assert "missing final folder" in result.stdout


@pytest.mark.skipif(
    not FINAL.exists(),
    reason="story-finalisation-awaits-final-review-and-final-sha-proof (#103 PREP; not readiness evidence)",
)
def test_real_final_submission_text_is_ready():
    result = check(FINAL)
    assert result.returncode == 0, result.stdout + result.stderr
