"""Follow-ups 75/76: impossible dates, inverted bands and out-of-range month/hour cells are refused.

Rule: a non-blank cell that fits its rung's regex but is not a real date, a real band or a real
month/hour is a RungError (fail closed), never a NaN/never-matching interval.
Synthetic cells only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pets_attacker.cli import main
from pets_attacker.linkage import QI, Matcher, RungError, parse_interval


@pytest.mark.parametrize("rung,cell", [
    ("dob.date", "2001-02-30"), ("dob.date", "2001-13-01"), ("dob.date", "2001-00-10"),
    ("dob.month", "2001-13"), ("dob.month", "2001-00"),
])
def test_impossible_dob_cell_is_refused(rung, cell):
    prot = pd.DataFrame({"dob": [cell, "2001-01-01" if rung == "dob.date" else "2001-01"]})
    with pytest.raises(RungError):
        Matcher(prot, [QI("age", ("a",), ("dob",))], {"dob": rung})


@pytest.mark.parametrize("rung", ["age.band5", "age.band10"])
def test_inverted_age_band_is_refused(rung):
    with pytest.raises(RungError):
        Matcher(pd.DataFrame({"age": ["40-30"]}), [QI("age", ("a",), ("age",))], {"age": rung})


def test_valid_dob_and_band_cells_still_index():
    m = Matcher(pd.DataFrame({"dob": ["2000-02-29", ""]}), [QI("age", ("a",), ("dob",))], {"dob": "dob.date"})
    lo, hi = m.d[0]
    assert 25.0 < lo[0] < hi[0] < 26.0 and lo[1] == -1.0
    m = Matcher(pd.DataFrame({"age": ["30-39"]}), [QI("age", ("a",), ("age",))], {"age": "age.band10"})
    assert tuple(m.d[0][0]) == (30.0,) and tuple(m.d[0][1]) == (40.0,)


@pytest.mark.parametrize("cell", ["2025-13-01T10:00", "2025-00-01T10:00", "2025-03-01T24:00", "2025-99-01T99:00"])
def test_out_of_range_month_hour_cell_is_refused(cell):
    with pytest.raises(RungError):
        parse_interval(pd.Series([cell]), "ts.month_hour")
    with pytest.raises(RungError):
        Matcher(pd.DataFrame({"t": [cell]}), [QI("time", ("t",), ("t",))], {"t": "ts.month_hour"})


def test_valid_month_hour_cells_still_parse():
    parse_interval(pd.Series(["2025-12-01T23:00", "2025-01-01T00:00", ""]), "ts.month_hour")


def _kit(root: Path, dob_cell: str, mh_cell: str) -> tuple:
    kit, rel = root / "kit", root / "rel"
    for d in ("data/health", "adversary", "truth", "metadata"):
        (kit / d).mkdir(parents=True)
    rel.mkdir()
    orig = pd.DataFrame({"visit_id": ["v0", "v1"], "municipality": ["Aa", "Bb"],
                         "arrival_ts": ["2025-01-01T09:00:00", "2025-02-01T09:00:00"],
                         "date_of_birth": ["1990-01-01", "1980-01-01"], "icd10_primary": ["X01", "X02"]})
    orig.to_csv(kit / "data/health/ed_visits.csv", index=False)
    released = orig.copy()
    released["arrival_ts"] = [mh_cell, "2025-02-01T09:00"]
    released["date_of_birth"] = [dob_cell, "1980-01-01"]
    released.to_csv(rel / "ed_visits.csv", index=False)
    pd.DataFrame({"protected_row": [0, 1], "original_record_id": ["v0", "v1"]}).to_csv(rel / "rowmap_ed_visits.csv", index=False)
    pd.DataFrame({"record_id": ["v0", "v1"], "person_id": ["p0", "p1"]}).to_csv(kit / "truth/health__ed_visits.csv", index=False)
    pd.DataFrame({"adv_row_id": ["a0"], "event_date": ["2025-01-01"], "place": ["Aa"], "age_mentioned": ["35"]}).to_csv(
        kit / "adversary/news_clips_health.csv", index=False)
    pd.DataFrame({"adv_row_id": ["a0"], "person_id": ["p0"]}).to_csv(kit / "truth/adversary__news_clips_health.csv", index=False)
    spec = {"attacks": [{"adversary": "news_clips_health", "dataset": "health", "table": "ed_visits", "sensitive": "icd10_primary",
                         "qis": [{"kind": "time", "adversary": ["event_date"], "protected": ["arrival_ts"], "window": [96, 24]},
                                 {"kind": "exact", "adversary": ["place"], "protected": ["municipality"]},
                                 {"kind": "age", "adversary": ["age_mentioned"], "protected": ["date_of_birth"], "tol": 1}]}]}
    (kit / "metadata/attack_specs.json").write_text(json.dumps(spec), encoding="utf-8")
    rungs = root / "rungs.json"
    rungs.write_text(json.dumps({"ed_visits": {"arrival_ts": "ts.month_hour", "municipality": "keep",
                                               "date_of_birth": "dob.date"}}), encoding="utf-8")
    return kit, rel, rungs


@pytest.mark.parametrize("dob_cell,mh_cell,ok", [
    ("1990-01-01", "2025-01-01T09:00", True),
    ("1990-02-30", "2025-01-01T09:00", False),
    ("1990-01-01", "2025-13-01T09:00", False),
])
def test_cli_refuses_impossible_cells(tmp_path: Path, dob_cell, mh_cell, ok):
    kit, rel, rungs = _kit(tmp_path, dob_cell, mh_cell)
    out = tmp_path / "o.json"
    rc = main(["--kit", str(kit), "--release", str(rel), "--label", "t", "--out", str(out), "--rungs", str(rungs)])
    assert (rc == 0) is ok
    assert out.exists() is ok
