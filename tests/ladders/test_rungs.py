"""Rung transforms: every output matches its rung's contract form; pure; fail closed."""

from __future__ import annotations

import re

import pandas as pd
import pytest

from pets_release.ladders import (
    CONTRACT_FORMS,
    LADDERS,
    VALIDATOR_FORMS,
    LadderError,
    apply,
    contract_form,
    output_column,
)


class FakeKeys:
    """Deterministic stand-in for the pseudonymiser interface (token(value, label))."""

    def token(self, value: str, label: str = "RECORD_KEY") -> str:
        import hashlib

        return hashlib.sha256(f"{label}|{value}".encode()).hexdigest()


def _plan(rows):
    return [
        {"table": t, "column": c, "rung": r, "params": p or {}, "floor": "", "reason": "t", "source": "hand"}
        for t, c, r, p in rows
    ]


def _one(rung, values, params=None, tables=None, extra_plan=()):
    df = pd.DataFrame({"x": values}, dtype=str)
    plan = _plan([("t", "x", rung, params)] + list(extra_plan))
    out = apply(plan, {"t": df, **(tables or {})}, FakeKeys())
    return out["t"]


def _matches(rung, value):
    form = contract_form(rung)
    if form in VALIDATOR_FORMS:
        return True
    assert form.startswith("^") and form.endswith("$"), form
    return re.fullmatch(form, value) is not None


TS = ["2025-03-14 14:37:05", "2025-03-31 00:00:00", "2025-12-01 23:59:59", "2025-01-05T08:15:00", "4.3.2025 07:45"]


@pytest.mark.parametrize("rung", ["ts.hour", "ts.month_hour", "ts.day", "ts.week", "ts.month"])
def test_timestamp_rungs_match_form(rung):
    out = _one(rung, TS)
    assert all(_matches(rung, v) for v in out["x"]), list(out["x"])


def test_timestamp_exact_values():
    assert list(_one("ts.hour", TS[:1])["x"]) == ["2025-03-14T14:00"]
    assert list(_one("ts.month_hour", TS[:1])["x"]) == ["2025-03-01T14:00"]
    assert list(_one("ts.day", TS[:1])["x"]) == ["2025-03-14"]
    assert list(_one("ts.month", TS[:1])["x"]) == ["2025-03"]
    # 2025-03-14 is ISO week 11
    assert list(_one("ts.week", TS[:1])["x"]) == ["2025-W11"]
    # Finnish day-first dates parse
    assert list(_one("ts.day", ["4.3.2025 07:45"])["x"]) == ["2025-03-04"]


def test_month_hour_contract_form_is_the_spec_regex():
    assert contract_form("ts.month_hour") == r"^\d{4}-\d{2}-01T\d{2}:00$"


def test_month_hour_keeps_hour_of_day_distribution():
    vals = [f"2025-{m:02d}-{d:02d} {h:02d}:{(m * d) % 60:02d}:11" for m in (1, 5, 9) for d in (3, 17) for h in range(24)]
    out = _one("ts.month_hour", vals)
    orig_h = pd.Series([int(v[11:13]) for v in vals]).value_counts().sort_index()
    new_h = pd.Series([int(v[11:13]) for v in out["x"]]).value_counts().sort_index()
    assert orig_h.equals(new_h)


def test_month_hour_parses_in_pets_eval_with_same_hours():
    pe = pytest.importorskip("pets_eval.parse")
    vals = ["2025-03-14 14:37:05", "2025-07-02 03:01:00", "2025-07-30 23:59:59"]
    out = _one("ts.month_hour", vals)["x"]
    assert list(pe.to_hour(out)) == [14, 3, 23]
    assert out.str.contains(r"\d{1,2}:\d{2}").all()  # health.derive: has_time


def test_timestamp_unparseable_never_passes_through():
    out = _one("ts.hour", ["not a time", "2025-03-14 01:02:03"])
    assert list(out["x"]) == ["", "2025-03-14T01:00"]


def test_timestamp_exact_is_identity_and_form_accepts_kit_shape():
    out = _one("ts.exact", ["2025-03-14 14:37:05"])
    assert list(out["x"]) == ["2025-03-14 14:37:05"]
    assert _matches("ts.exact", "2025-03-14 14:37:05")


@pytest.mark.parametrize(
    "dob,ref,band5,band10",
    [
        ("1990-06-15", "2025-06-14", "30-34", "30-39"),  # birthday not yet reached: 34
        ("1990-06-15", "2025-06-15", "35-39", "30-39"),
        ("2025-01-01", "2025-12-31", "0-4", "0-9"),
        ("1930-01-01", "2025-12-31", "90+", "90+"),
        ("1900-01-01", "2025-12-31", "90+", "90+"),  # age 125: still top-coded
        ("1925-12-31", "2025-12-30", "90+", "90+"),  # 99
    ],
)
def test_age_bands(dob, ref, band5, band10):
    df = pd.DataFrame({"date_of_birth": [dob], "arrival_ts": [ref + " 10:00:00"]}, dtype=str)
    for rung, expect in (("age.band5", band5), ("age.band10", band10)):
        plan = _plan(
            [
                ("v", "date_of_birth", rung, {"ref_column": "arrival_ts"}),
                ("v", "arrival_ts", "ts.month_hour", None),
            ]
        )
        out = apply(plan, {"v": df}, FakeKeys())["v"]
        assert list(out["age_band"]) == [expect]
        assert "date_of_birth" not in out.columns
        assert _matches(rung, expect)


def test_age_ref_uses_original_not_generalised_column():
    # arrival_ts is coarsened in the same plan; age must still be computed from the original.
    df = pd.DataFrame({"date_of_birth": ["1990-06-15"], "arrival_ts": ["2025-06-30 10:00:00"]}, dtype=str)
    plan = _plan(
        [("v", "date_of_birth", "age.band10", {"ref_column": "arrival_ts"}), ("v", "arrival_ts", "ts.month", None)]
    )
    assert list(apply(plan, {"v": df}, FakeKeys())["v"]["age_band"]) == ["30-39"]


def test_age_numeric_source_and_fixed_ref_date_and_bad_values():
    df = pd.DataFrame({"a": ["37", "1980-01-01", "garbage", "", "200"]}, dtype=str)
    plan = _plan([("v", "a", "age.band5", {"ref_date": "2025-12-31"})])
    out = apply(plan, {"v": df}, FakeKeys())["v"]
    assert list(out["age_band"]) == ["35-39", "45-49", "", "", ""]


def test_age_without_reference_fails_closed():
    df = pd.DataFrame({"a": ["1990-01-01"]}, dtype=str)
    with pytest.raises(LadderError):
        apply(_plan([("v", "a", "age.band5", {})]), {"v": df}, FakeKeys())


def test_age_output_column_name_is_configurable_and_collision_refused():
    df = pd.DataFrame({"a": ["1990-01-01"], "age_band": ["x"]}, dtype=str)
    with pytest.raises(LadderError):
        apply(_plan([("v", "a", "age.band5", {"ref_date": "2025-01-01"}), ("v", "age_band", "keep", None)]), {"v": df}, FakeKeys())
    out = apply(_plan([("v", "a", "age.band5", {"ref_date": "2025-01-01", "output": "ageb"})]), {"v": df[["a"]]}, FakeKeys())["v"]
    assert list(out.columns) == ["ageb"]
    entry = _plan([("v", "a", "age.band5", {"output": "ageb"})])[0]
    assert output_column(entry) == "ageb"
    assert output_column(_plan([("v", "a", "age.band5", {})])[0]) == "age_band"
    assert output_column(_plan([("v", "a", "keep", {})])[0]) == "a"


def test_geo_topn_groups_rest_as_other_with_deterministic_ties():
    vals = ["A"] * 5 + ["B"] * 3 + ["C"] * 3 + ["D"] * 1 + ["E"] * 1 + [None]
    out = _one("geo.topn", vals, {"n": 2})["x"]
    # top2: A (5), then tie B/C at 3 -> alphabetical -> B
    assert list(out)[:13] == ["A"] * 5 + ["B"] * 3 + ["other"] * 5
    assert pd.isna(list(out)[-1])
    assert _matches("geo.topn", "other")


def test_geo_topn_requires_n():
    with pytest.raises(LadderError):
        _one("geo.topn", ["a"], {})
    with pytest.raises(LadderError):
        _one("geo.topn", ["a"], {"n": 0})


def test_geo_full_and_keep_identity():
    assert list(_one("geo.full", ["Turku", "Åbo"])["x"]) == ["Turku", "Åbo"]
    assert list(_one("keep", ["F", "M"])["x"]) == ["F", "M"]


@pytest.mark.parametrize(
    "rung,expect",
    [("icd.full", ["J18.9", "R51", "S72.0"]), ("icd.3", ["J18", "R51", "S72"]), ("icd.chapter", ["J", "R", "S"])],
)
def test_icd_rungs(rung, expect):
    out = _one(rung, ["J18.9", "r51", " S72.0 "])["x"]
    assert list(out) == (expect if rung != "icd.full" else ["J18.9", "R51", "S72.0"])
    assert all(_matches(rung, v) for v in out)


def test_icd_garbage_is_blank_for_coarse_rungs():
    assert list(_one("icd.3", ["hello", "", "J18.9"])["x"]) == ["", "", "J18"]
    assert list(_one("icd.chapter", ["12"])["x"]) == [""]


def test_numeric_round():
    out = _one("num.round", ["36.84", "37,05", "-0.4", "120", "bad"], {"unit": 0.5})["x"]
    assert list(out) == ["37.0", "37.0", "-0.5", "120.0", ""]
    out = _one("num.round", ["123", "126", "5"], {"unit": 5})["x"]
    assert list(out) == ["125", "125", "5"]
    out = _one("num.round", ["123", "127"], {"unit": 10})["x"]
    assert list(out) == ["120", "130"]
    assert all(_matches("num.round", v) for v in out)


def test_numeric_bin_matches_form_and_parses_in_pets_eval():
    out = _one("num.bin", ["12", "19.9", "-3", "20", "x"], {"width": 10})["x"]
    assert list(out) == ["[10,20)", "[10,20)", "[-10,0)", "[20,30)", ""]
    assert all(_matches("num.bin", v) for v in out if v)
    pe = pytest.importorskip("pets_eval.parse")
    parsed = pe.parse_numeric(out.iloc[:4])
    assert parsed.notna().all() and abs(parsed.iloc[0] - 15) < 1e-6


def test_numeric_exact_is_identity():
    assert list(_one("num.exact", ["36.8", "12"])["x"]) == ["36.8", "12"]


def test_numeric_params_validated():
    with pytest.raises(LadderError):
        _one("num.round", ["1"], {"unit": 0})
    with pytest.raises(LadderError):
        _one("num.bin", ["1"], {})


def test_identifier_pseudonym_is_64_hex_and_consistent_across_tables():
    a = pd.DataFrame({"visit_id": ["V1", "V2"], "k": ["1", "2"]}, dtype=str)
    b = pd.DataFrame({"visit_id": ["V2", "V1", "V2"], "z": ["a", "b", "c"]}, dtype=str)
    plan = _plan([("a", "visit_id", "id.pseudonym", {}), ("a", "k", "keep", None), ("b", "visit_id", "id.pseudonym", {}), ("b", "z", "keep", None)])
    out = apply(plan, {"a": a, "b": b}, FakeKeys())
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in out["a"]["visit_id"])
    assert out["a"]["visit_id"][1] == out["b"]["visit_id"][0]
    assert out["a"]["visit_id"][0] == out["b"]["visit_id"][1]
    assert "V1" not in out["a"]["visit_id"].tolist()
    assert contract_form("id.pseudonym") == "hex64"


def test_identifier_empty_stays_empty_and_label_param():
    out = _one("id.pseudonym", ["", None, "X"], {"label": "NATIONAL_ID"})["x"]
    assert out[0] == "" or pd.isna(out[0])
    assert pd.isna(out[1])
    assert out[2] == FakeKeys().token("X", "NATIONAL_ID")


def test_withheld_drops_column_and_table():
    a = pd.DataFrame({"p": ["1"], "q": ["2"]}, dtype=str)
    b = pd.DataFrame({"p": ["1"]}, dtype=str)
    plan = _plan([("a", "p", "withheld", None), ("a", "q", "keep", None), ("b", "p", "withheld", None)])
    out = apply(plan, {"a": a, "b": b}, FakeKeys())
    assert list(out) == ["a"] and list(out["a"].columns) == ["q"]


def test_text_redacted_needs_injected_redactor():
    df = pd.DataFrame({"x": ["hello"]}, dtype=str)
    plan = _plan([("t", "x", "text.redacted", {})])
    with pytest.raises(LadderError):
        apply(plan, {"t": df}, FakeKeys())
    out = apply(plan, {"t": df}, FakeKeys(), redactor=lambda table, column, frame, params: frame[column].str.upper())
    assert list(out["t"]["x"]) == ["HELLO"]


def test_every_non_withheld_rung_has_a_contract_form_and_ladders_are_consistent():
    for kind, ladder in LADDERS.items():
        assert ladder[-1] == "withheld", kind
        for r in ladder[:-1]:
            assert r in CONTRACT_FORMS
            form = CONTRACT_FORMS[r]
            assert form in VALIDATOR_FORMS or (form.startswith("^") and form.endswith("$")), (r, form)
            if form not in VALIDATOR_FORMS:
                re.compile(form)
    assert "withheld" not in CONTRACT_FORMS


def test_contract_form_unknown_rung_raises():
    with pytest.raises(LadderError):
        contract_form("ts.nope")
    with pytest.raises(LadderError):
        contract_form("withheld")
