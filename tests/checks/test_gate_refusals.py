"""Planted refusal fixtures through the real registry and runner (ticket 04)."""
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
GATE = {"phase": "gate"}
CASES = sorted(p.name for p in FIX.iterdir() if p.is_dir())


def _copy(case, tmp_path):
    dst = tmp_path / "out"
    shutil.copytree(FIX / case / "release", dst)
    return dst


def _by_name(result):
    return {r.check: r for r in result.records}


def test_valid_release_passes_every_registered_check(tmp_path):
    res = run_checks(_copy("valid", tmp_path), CONTRACT, GATE)
    bad = {r.check: r.status for r in res.records if r.status != "pass"}
    assert bad == {}
    assert not res.refused
    assert {r.check for r in res.records} == {c.name for c in all_checks()}


@pytest.mark.parametrize("case", [c for c in CASES if c != "valid"])
def test_planted_fixture_is_refused_with_counts_and_locations(case, tmp_path):
    expected = json.loads((FIX / case / "expected.json").read_text(encoding="utf-8"))
    res = run_checks(_copy(case, tmp_path), CONTRACT, GATE)
    assert res.refused
    recs = _by_name(res)
    for check, want in expected["failing"].items():
        rec = recs[check]
        assert rec.status == "fail", check
        got = sorted(
            ({"file": v.file, "column": v.column, "count": v.count, "locations": list(v.locations)}
             for v in rec.violations if v.severity == "high"),
            key=lambda d: (d["file"], d["column"] or ""),
        )
        assert got == want, check
        assert rec.hits == sum(v.count for v in rec.violations)
    blob = json.dumps(res.to_dict(), sort_keys=True)
    if "planted" in expected:
        assert expected["planted"] not in blob


def test_row_map_file_in_release_is_refused(tmp_path):
    out = _copy("valid", tmp_path)
    # planted at test time: rowmap_*.csv files are never committed
    (out / "rowmap_visits.csv").write_text("protected_row,original_record_id\n0,x\n", encoding="utf-8")
    recs = _by_name(run_checks(out, CONTRACT, GATE))
    assert recs["release.row-maps"].status == "fail"
    labels = sorted((v.label, v.column or "") for v in recs["release.row-maps"].violations)
    assert labels == [("rowMapColumn", "original_record_id"), ("rowMapColumn", "protected_row"), ("rowMapFile", "")]
    assert recs["contract.files"].status == "fail"


def test_valid_token_in_token_column_passes_but_same_hex_elsewhere_fails(tmp_path):
    out = _copy("valid", tmp_path)
    recs = _by_name(run_checks(out, CONTRACT, GATE))
    assert recs["release.token-hex64"].status == "pass"
    assert recs["release.token-hex64"].denominator["n"] > 0


def test_forged_pass_file_does_not_skip_any_check(tmp_path):
    out = _copy("card_in_cell", tmp_path)
    forged = {"refused": False, "records": [{"check": c.name, "status": "pass"} for c in all_checks()]}
    for p in (out / "gate_pass.json", out.parent / "out.scoring" / "gate.json", out.parent / "gate_pass.json"):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(forged), encoding="utf-8")
    res = run_checks(out, CONTRACT, GATE)
    recs = _by_name(res)
    assert res.refused
    assert set(recs) == {c.name for c in all_checks()}
    assert recs["rescan.payment-cards"].status == "fail"
    assert recs["contract.files"].status == "fail"  # the planted file inside <out>/ itself


def test_missing_release_folder_is_never_clean(tmp_path):
    res = run_checks(tmp_path / "nope", CONTRACT, GATE)
    assert res.refused
    assert all(r.status == "error" for r in res.records)
