"""Follow-up #43: redactor alignment, age output name, numeric/edge hardening."""

from __future__ import annotations

import pandas as pd
import pytest

from pets_release.ladders import LADDERS, LadderError, apply
from pets_release.ladders import transforms as T


class FakeKeys:
    def token(self, value, label="RECORD_KEY"):
        import hashlib

        return hashlib.sha256(f"{label}|{value}".encode()).hexdigest()


def _finest(rung):
    return next((lad[0] for lad in LADDERS.values() if rung in lad), "keep")


def e(table, column, rung, params=None, floor=None):
    floor = floor or _finest(rung)
    return {"table": table, "column": column, "rung": rung, "params": params or {}, "floor": floor, "reason": "t", "source": "hand"}


def _df(**cols):
    return pd.DataFrame(cols, dtype=str)


def test_redactor_reordered_series_is_realigned_by_index():
    df = pd.DataFrame({"t": ["a", "b", "c"]}, index=[10, 11, 12], dtype=str)
    red = lambda tb, c, fr, p: pd.Series(["A", "B", "C"], index=[12, 10, 11]).rename("x")
    out = apply([e("x", "t", "text.redacted", floor="text.redacted")], {"x": df}, FakeKeys(), redactor=red)["x"]
    assert out["t"].tolist() == ["B", "C", "A"]


def test_redactor_with_foreign_index_refused():
    df = pd.DataFrame({"t": ["a", "b"]}, index=[10, 11], dtype=str)
    red = lambda tb, c, fr, p: pd.Series(["A", "B"])
    with pytest.raises(LadderError):
        apply([e("x", "t", "text.redacted", floor="text.redacted")], {"x": df}, FakeKeys(), redactor=red)


@pytest.mark.parametrize("output", ["dob", "other", None])
def test_age_output_equal_to_source_column_refused(output):
    df = _df(dob=["1990-01-01"], other=["x"], age_band=["z"]) if output is None else _df(dob=["1990-01-01"], other=["x"])
    params = {"ref_date": "2025-01-01"}
    if output:
        params["output"] = output
    plan = [e("t", "dob", "age.band5", params), e("t", "other", "keep")]
    if output is None:
        plan.append(e("t", "age_band", "keep"))
    with pytest.raises(LadderError):
        apply(plan, {"t": df}, FakeKeys())


def test_num_bin_bad_origin_is_ladder_error():
    for bad in (None, "Infinity", "x", True):
        with pytest.raises(LadderError):
            T.num_bin(pd.Series(["1"]), {"width": 5, "origin": bad})


def test_huge_values_blank_not_raise():
    s = pd.Series(["1e30", "1e999999999", "5"])
    assert T.num_round(s, {"unit": 1}).tolist()[0] in ("", "1" + "0" * 30)
    assert T.num_bin(s, {"width": 5}).tolist()[2] == "[5,10)"
    T.num_exact(s, {})


def test_non_str_cells_refused():
    df = pd.DataFrame({"a": ["x", 5]})
    with pytest.raises(LadderError):
        apply([e("t", "a", "keep")], {"t": df}, FakeKeys())


def test_topn_ignores_empty_strings():
    s = pd.Series(["", "", "", "a", "b"])
    assert T.geo_topn(s, {"n": 1}).tolist() == ["", "", "", "a", "other"]


def test_num_exact_negative_zero_normalised():
    assert T.num_exact(pd.Series(["-0", "-0.0", "-1"]), {}).tolist() == ["0", "0.0", "-1"]


def test_zero_column_table_refused():
    with pytest.raises(LadderError):
        apply([], {"t": pd.DataFrame({})}, FakeKeys())


def test_bad_token_shape_refused():
    class Bad:
        def token(self, value, label="RECORD_KEY"):
            return value

    df = _df(id=["a"])
    with pytest.raises(LadderError):
        apply([e("t", "id", "id.pseudonym")], {"t": df}, Bad())
