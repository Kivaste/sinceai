"""Review round 1: mandatory floors; rung output and contract form agree by construction."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from pets_release.ladders import (
    CONTRACT_FORMS,
    CONTRACT_PARAMS,
    LADDERS,
    LadderError,
    apply,
    contract_entry,
)


class FakeKeys:
    def token(self, value, label="RECORD_KEY"):
        import hashlib

        return hashlib.sha256(f"{label}|{value}".encode()).hexdigest()


def entry(rung, params=None, **over):
    e = {"table": "t", "column": "x", "rung": rung, "params": params or {}, "floor": "keep", "reason": "r", "source": "hand"}
    e.update(over)
    return e


def run(entries, values):
    return apply(entries, {"t": pd.DataFrame({"x": values}, dtype=object)}, FakeKeys())


# ---- 1. floors are mandatory -------------------------------------------------
@pytest.mark.parametrize("bad", ["", None, False, 0, "garbage", "ts.nope"])
def test_missing_or_invalid_floor_refused(bad):
    with pytest.raises(LadderError):
        run([entry("keep", floor=bad)], ["a"])


def test_absent_floor_key_refused():
    e = entry("keep")
    del e["floor"]
    with pytest.raises(LadderError):
        run([e], ["a"])


def test_withheld_with_withheld_floor_ok_and_keep_below_floor_refused():
    assert run([entry("withheld", floor="withheld")], ["a"]) == {}
    with pytest.raises(LadderError):
        run([entry("keep", floor="withheld")], ["a"])


# ---- 2. output agrees with the form ------------------------------------------
SAMPLES = [
    "2025-03-14 14:37:05", "2025-03-14T14:37", "2025-03-14", "4.3.2025 07:45", "04.03.2025 klo 7.45", "4.3.2025",
    "2025-03-14 14:37:05+02:00", "2025-03-14 14:37:05.123Z", "",
    None, "garbage", "2025-02-30", "2025-03-14 25:00:00", "2025-03-14 12:61:00", "2025-03-14 12:00:61",
    "1990-06-15", "37", "250", "J18.9", "j18", "r51", "S72.0", "R", "12,5", "36.84", "-3", "1e3", "nan", "1,000.5",
    "abc", "Turku", "x" * 3,
]
PARAMS = {
    "geo.topn": {"n": 2}, "num.round": {"unit": 0.5}, "num.bin": {"width": 10},
    "age.band5": {"ref_date": "2025-12-31"}, "age.band10": {"ref_date": "2025-12-31"}, "id.pseudonym": {},
}
FORM_CHECK = {
    "hex64": lambda v: re.fullmatch(r"[0-9a-f]{64}", v),
    "decimal": lambda v: re.fullmatch(r"-?\d+(\.\d+)?", v),
    "integer": lambda v: re.fullmatch(r"-?\d+", v),
    "text": lambda v: True,
    "enum": lambda v: True,
}
RUNGS = [r for lad in LADDERS.values() for r in lad if r not in ("withheld", "text.redacted")]


@pytest.mark.parametrize("rung", RUNGS)
def test_every_output_satisfies_form_or_is_nullable_empty(rung):
    form = CONTRACT_FORMS[rung]
    assert CONTRACT_PARAMS[rung] == {"nullable": True}
    out = run([entry(rung, PARAMS.get(rung), floor=LADDERS_FINEST(rung))], SAMPLES)
    col = next(iter(out["t"].columns))
    for src, v in zip(SAMPLES, out["t"][col]):
        if pd.isna(v) or v == "":
            continue  # nullable empty
        ok = FORM_CHECK[form](v) if form in FORM_CHECK else re.fullmatch(form, v)
        assert ok, (rung, form, src)


def LADDERS_FINEST(rung):
    return next(lad[0] for lad in LADDERS.values() if rung in lad)


def test_null_and_malformed_become_empty_never_raw():
    for rung in ("ts.exact", "ts.day", "num.exact", "icd.full"):
        out = run([entry(rung, floor=LADDERS_FINEST(rung))], ["garbage", None, ""])["t"]["x"]
        assert out[0] == ""
        assert pd.isna(out[1]) or out[1] == ""
        assert out[2] == ""


def test_exact_timestamp_normalised_from_finnish_formats():
    out = run([entry("ts.exact", floor="ts.exact")], ["4.3.2025 07:45", "2025-03-14T14:37", "2025-03-14 14:37:05"])["t"]["x"]
    assert list(out) == ["2025-03-04 07:45:00", "2025-03-14 14:37:00", "2025-03-14 14:37:05"]


def test_exact_numeric_normalised_decimal_comma():
    out = run([entry("num.exact", floor="num.exact")], ["12,5", "36.8", "abc", "<5", ">100", "<"])["t"]["x"]
    assert list(out) == ["12.5", "36.8", "", "<5", ">100", ""]


def test_contract_entry_carries_form_and_nullable():
    assert contract_entry("ts.month_hour") == {"form": CONTRACT_FORMS["ts.month_hour"], "params": {"nullable": True}}
    with pytest.raises(LadderError):
        contract_entry("withheld")


# ---- 3. full timestamp validation --------------------------------------------
@pytest.mark.parametrize("bad", ["2025-03-14 12:61:00", "2025-03-14 12:00:61", "2025-03-14 24:00:00", "2025-13-01", "31.2.2025"])
@pytest.mark.parametrize("rung", ["ts.hour", "ts.month_hour", "ts.day", "ts.week", "ts.month", "ts.exact"])
def test_invalid_timestamp_is_malformed(rung, bad):
    assert run([entry(rung, floor="ts.exact")], [bad])["t"]["x"][0] == ""
