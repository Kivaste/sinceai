"""Must-fix #56 round 2 (Sol D31 review, high): text-check applicability must not rest on a few lowercase
probe phrases. An undeclared column whose regex form can accept whitespace together with a variable part
(a class, a category or "."), i.e. can carry several free words in a short cell, counts as free text: the text
checks error (never not_applicable, never proof of safety). A form that cannot accept whitespace, or accepts
only a closed set of literal phrases, stays not text. Production runner and the real checks CLI.

Rows (trigger -> result):
  no text-form column; short cells under ^[A-Z ]+$ (or similar)  -> was not_applicable; now error
  numeric / timestamp / code / closed-literal forms              -> stay not_applicable
All rows are hand-made synthetic text.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks

SRC = Path(__file__).resolve().parents[2] / "src"
UPPER_FORMS = ["^[A-Z ]+$", "^[A-Z]+ [A-Z]+$", "^[A-ZÅÄÖ0-9 ]{1,40}$", "^[A-Z\\t]+$",
               "^[A-Z]+(?:\\s[A-Z]+)?$"]
TIGHT_FORMS = ["^[A-Z][0-9]{2}$", "^[<>]?-?\\d+(?:\\.\\d+)?$", "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:00$",
               "^(?:\\d{1,2}-\\d{1,2}|90\\+)$", "^(call me|ok)$", "^[A-Z]+$"]


def _release(tmp_path, form):
    folder = tmp_path / "r"
    folder.mkdir()
    with open(folder / "notes.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["note_id", "note"])
        w.writerows([["N1", "HEART ATTACK"], ["N2", "CALL ME"], ["N3", "OK"]])
    contract = {"files": {"notes.csv": {"required": ["note_id", "note"], "columns": {
        "note_id": {"form": "^N[0-9]+$", "params": {}}, "note": {"form": form, "params": {}}}}},
        "qi": [], "tokens": [], "healthInTextRequired": True}
    return folder, contract


def _status(check, folder, contract):
    chk = {c.name: c for c in all_checks()}[check]
    (rec,) = run_checks(folder, contract, {"phase": "gate"}, checks=[chk]).records
    return rec.status


@pytest.mark.parametrize("form", UPPER_FORMS)
@pytest.mark.parametrize("check", ["text.health", "text.phones", "text.secrets"])
def test_whitespace_accepting_form_with_short_cells_is_an_error(tmp_path, form, check):
    folder, contract = _release(tmp_path, form)
    assert _status(check, folder, contract) == "error"


@pytest.mark.parametrize("form", TIGHT_FORMS)
def test_forms_without_free_words_stay_not_applicable(tmp_path, form):
    folder, contract = _release(tmp_path, form)
    assert _status("text.health", folder, contract) == "not_applicable"


def test_cli_refuses_whitespace_accepting_form(tmp_path):
    folder, contract = _release(tmp_path, "^[A-Z ]+$")
    c = tmp_path / "contract.json"
    c.write_text(json.dumps(contract), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "pets_release.checks", "--contract", str(c), "--phase", "gate",
                        "--check", "text.health", str(folder)], check=False, capture_output=True, text=True, env=env)
    assert r.returncode == 1, r.stderr
    summary = json.loads(r.stdout)
    assert summary["refused"] is True
    assert {x["check"]: x["status"] for x in summary["records"]}["text.health"] == "error"
    assert "HEART" not in r.stdout
