"""Review r3 (a4144a2): case/separator-tolerant IBAN and plates, content-free structure output,
partial-selection marking, and the runner-level not_applicable status."""
import copy
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.checks import Check, Outcome, all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
GATE = {"phase": "gate"}
SRC = Path(__file__).resolve().parents[2] / "src"


def _own():
    return [c for c in all_checks() if c.run.__module__.startswith("pets_release.checks.cells.")]


def _valid(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    return out


def _plant_text(out, text):
    p = out / "notes.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows[2][2] = text
    with p.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)


@pytest.mark.parametrize("check,text", [
    ("rescan.ibans", "tili fi21 1234 5600 0007 85 ok"),
    ("rescan.ibans", "tili FI21-1234-5600-0007-85 ok"),
    ("rescan.ibans", "tili Fi21  1234 5600 0007 85 ok"),
    ("rescan.plates", "auto abc-123 pihalla"),
    ("rescan.plates", "auto Abc-12 pihalla"),
])
def test_lower_case_and_separated_identifiers_refuse(tmp_path, check, text):
    out = _valid(tmp_path)
    _plant_text(out, text)
    res = run_checks(out, CONTRACT, GATE, checks=_own())
    rec = {r.check: r for r in res.records}[check]
    assert (rec.status, rec.hits, res.refused) == ("fail", 1, True)


@pytest.mark.parametrize("text,hits", [
    ("tili be51731042965018 ok", 1),       # lower-case, own token
    ("BE51731042965018", 1),               # upper-case whole cell
    ("ref_BE51731042965018", 1),           # upper-case glued: still a hit (fail closed)
    ("pid_be51731042965018", 0),           # lower-case glued to an identifier prefix: pseudonym text
    ("pid-be51731042965018", 0),
])
def test_lower_case_iban_must_stand_alone(tmp_path, text, hits):
    out = _valid(tmp_path)
    _plant_text(out, text)
    rec = {r.check: r for r in run_checks(out, CONTRACT, GATE, checks=_own()).records}["rescan.ibans"]
    assert rec.hits == hits


def test_mixed_case_iban_with_bad_checksum_still_passes(tmp_path):
    out = _valid(tmp_path)
    _plant_text(out, "tili fi21-1234-5600-0007-86 ok")
    rec = {r.check: r for r in run_checks(out, CONTRACT, GATE, checks=_own()).records}["rescan.ibans"]
    assert rec.status == "pass"


VALUE_HEADER = "131052-308T"  # value-like header cell
VALUE_FILE = "4111111111111111.csv"


def test_structure_output_never_echoes_unlisted_header_or_file_names(tmp_path):
    out = _valid(tmp_path)
    p = out / "visits.csv"
    rows = list(csv.reader(p.open(encoding="utf-8", newline="")))
    rows[0].append(VALUE_HEADER)
    for r in rows[1:]:
        r.append("x")
    with p.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    (out / VALUE_FILE).write_text("a\n1\n", encoding="utf-8")
    res = run_checks(out, CONTRACT, GATE, checks=_own())
    blob = json.dumps(res.to_dict())
    assert VALUE_HEADER not in blob and "4111111111111111" not in blob
    recs = {r.check: r for r in res.records}
    cols = [(v.label, v.file, v.column) for v in recs["contract.columns"].violations]
    assert ("extraColumn", "visits.csv", "unlisted-column#5") in cols
    files = [(v.label, v.file) for v in recs["contract.files"].violations]
    assert files == [("unexpectedFile", "unlisted-file#0")]


def _cli(*args):
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-m", "pets_release.checks", *args],
                          check=False, capture_output=True, text=True, env=env)


def test_cli_marks_narrowed_runs_partial_and_full_runs_full(tmp_path):
    out = _valid(tmp_path)
    c = FIX / "contract.json"
    part = _cli("--contract", str(c), "--phase", "gate", "--check", "rescan.emails", str(out))
    assert json.loads(part.stdout)["selection"] == "partial"
    assert "selection: partial" in part.stderr
    scoped = _cli("--contract", str(c), "--phase", "gate", "--scope", "release", str(out))
    assert json.loads(scoped.stdout)["selection"] == "partial"
    full = _cli("--contract", str(c), "--phase", "gate", str(out))
    assert json.loads(full.stdout)["selection"] == "full"


def test_cli_help_exits_0():
    r = _cli("--help")
    assert r.returncode == 0 and "--check" in r.stdout


def _textish(release, contract, context):
    return Outcome.not_applicable()


TEXTISH = Check(name="text.demo", version="1.0.0", scope="release", unit="turns", run=_textish,
                applies_to=("text",))
NO_DECL = Check(name="text.nodecl", version="1.0.0", scope="release", unit="turns", run=_textish)


def _no_text_contract():
    c = copy.deepcopy(CONTRACT)
    c["files"]["notes.csv"]["columns"]["note_text"]["form"] = "^.*$"
    return c


def _files_check():
    return [c for c in all_checks() if c.name == "contract.files"]


def test_not_applicable_when_contract_has_no_column_of_its_unit_does_not_refuse(tmp_path):
    res = run_checks(_valid(tmp_path), _no_text_contract(), GATE, checks=[TEXTISH, *_files_check()])
    rec = {r.check: r for r in res.records}["text.demo"]
    assert (rec.status, rec.denominator["n"], rec.hits, res.refused) == ("not_applicable", 0, 0, False)


def test_not_applicable_while_contract_declares_its_unit_is_error(tmp_path):
    res = run_checks(_valid(tmp_path), CONTRACT, GATE, checks=[TEXTISH])
    assert (res.records[0].status, res.refused) == ("error", True)


def test_not_applicable_from_check_without_declared_forms_is_error(tmp_path):
    res = run_checks(_valid(tmp_path), _no_text_contract(), GATE, checks=[NO_DECL])
    assert (res.records[0].status, res.refused) == ("error", True)


def test_all_not_applicable_selection_still_refuses(tmp_path):
    # nothing was actually checked: never clean (same rule as an empty selection)
    res = run_checks(_valid(tmp_path), _no_text_contract(), GATE, checks=[TEXTISH])
    assert res.records[0].status == "not_applicable"
    assert res.refused is True
