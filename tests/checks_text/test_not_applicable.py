"""Text checks on a release with no text column (HEALTH-S1-like) are not_applicable, not error."""
import csv

from pets_release.checks import run_checks
from pets_release.checks.registry import all_checks

C = "customer"


def _no_text_release(tmp_path):
    folder = tmp_path / "release"
    folder.mkdir()
    with open(folder / "visits.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["age_band", "los_minutes"])
        w.writerows([["30-34", "120"], ["40-44", "95"]])
    contract = {
        "files": {"visits.csv": {"required": ["age_band"], "columns": {
            "age_band": {"form": "^\\d{2}-\\d{2}$", "params": {}},
            "los_minutes": {"form": "integer", "params": {}},
        }}},
        "qi": [], "tokens": [],
    }
    return folder, contract


def _text_checks():
    return [c for c in all_checks() if c.name.startswith("text.")]


def test_every_text_check_declares_it_applies_to_text():
    checks = _text_checks()
    assert len(checks) == 14
    assert all(c.applies_to == ("text",) for c in checks)


def test_no_text_column_makes_every_text_check_not_applicable(tmp_path):
    folder, contract = _no_text_release(tmp_path)
    other = [c for c in all_checks() if c.name == "contract.files"]
    res = run_checks(folder, contract, {"phase": "gate"}, checks=_text_checks() + other)
    by = {r.check: r for r in res.records}
    for c in _text_checks():
        assert by[c.name].status == "not_applicable", c.name
        assert by[c.name].denominator == {"unit": "turns", "n": 0}
    assert by["contract.files"].status == "pass"
    assert res.refused is False


def test_text_column_present_keeps_normal_behaviour(gate, release, contract):
    folder = release([[(C, "it is 131052-308T")], [(C, "my invoice is wrong")]])
    assert gate("text.national-ids", folder, contract())["status"] == "fail"
    rec = gate("text.phones", folder, contract())
    assert rec["status"] == "pass" and rec["denominator"] == {"unit": "turns", "n": 2}


def test_text_column_with_empty_file_is_not_not_applicable(tmp_path, contract):
    folder = tmp_path / "release"
    folder.mkdir()
    (folder / "turns.csv").write_text("turn_id,conversation_id,seq,speaker,text\n", encoding="utf-8")
    chk = [c for c in all_checks() if c.name == "text.phones"]
    rec = run_checks(folder, contract(), {"phase": "gate"}, checks=chk).records[0]
    assert rec.status == "error"
