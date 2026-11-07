"""apply(): plan validation, purity, determinism, floor, real pseudonymiser seam."""

from __future__ import annotations

import copy
import re

import pandas as pd
import pytest

from pets_release.ladders import LadderError, PseudonymKeys, apply


class FakeKeys:
    def token(self, value, label="RECORD_KEY"):
        import hashlib

        return hashlib.sha256(f"{label}|{value}".encode()).hexdigest()


def e(table, column, rung, params=None, floor=""):
    return {"table": table, "column": column, "rung": rung, "params": params or {}, "floor": floor, "reason": "t", "source": "hand"}


def tables():
    return {
        "t": pd.DataFrame(
            {"id": ["a", "b", "c"], "ts": ["2025-03-14 14:37:05", "2025-04-01 01:00:00", "2025-05-05 05:05:05"], "v": ["1.26", "2.5", "9"]},
            dtype=str,
        )
    }


PLAN = [e("t", "id", "id.pseudonym"), e("t", "ts", "ts.month_hour"), e("t", "v", "num.round", {"unit": 1})]


def test_pure_no_mutation_and_deterministic():
    tb = tables()
    snapshot = copy.deepcopy({k: v.copy() for k, v in tb.items()})
    plan_snapshot = copy.deepcopy(PLAN)
    o1 = apply(PLAN, tb, FakeKeys())
    o2 = apply(list(reversed(PLAN)), tb, FakeKeys())  # plan order does not matter
    pd.testing.assert_frame_equal(tb["t"], snapshot["t"])
    assert PLAN == plan_snapshot
    pd.testing.assert_frame_equal(o1["t"], o2["t"])
    assert list(o1["t"].columns) == ["id", "ts", "v"]  # source column order


def test_missing_plan_entry_for_column_refused():
    with pytest.raises(LadderError):
        apply(PLAN[:2], tables(), FakeKeys())


def test_plan_entry_for_unknown_column_or_table_refused():
    with pytest.raises(LadderError):
        apply(PLAN + [e("t", "nope", "keep")], tables(), FakeKeys())
    with pytest.raises(LadderError):
        apply(PLAN + [e("zzz", "id", "keep")], tables(), FakeKeys())


def test_missing_table_in_plan_refused():
    with pytest.raises(LadderError):
        apply(PLAN, {**tables(), "other": pd.DataFrame({"a": ["1"]}, dtype=str)}, FakeKeys())


def test_duplicate_entries_and_unknown_rung_refused():
    with pytest.raises(LadderError):
        apply(PLAN + [e("t", "id", "keep")], tables(), FakeKeys())
    with pytest.raises(LadderError):
        apply([e("t", "id", "bogus"), *PLAN[1:]], tables(), FakeKeys())


def test_rung_from_wrong_column_kind_is_still_a_valid_rung():
    # kinds are advisory: the plan owner decides; geo.topn on any text column is fine
    out = apply([e("t", "id", "geo.topn", {"n": 1}), *PLAN[1:]], tables(), FakeKeys())
    assert set(out["t"]["id"]) <= {"a", "other"}


def test_floor_enforced_finer_than_floor_refused():
    plan = [e("t", "id", "keep", floor="id.pseudonym"), *PLAN[1:]]
    with pytest.raises(LadderError):
        apply(plan, tables(), FakeKeys())
    plan = [e("t", "id", "id.pseudonym", floor="withheld"), *PLAN[1:]]
    with pytest.raises(LadderError):
        apply(plan, tables(), FakeKeys())
    plan = [e("t", "id", "withheld", floor="id.pseudonym"), *PLAN[1:]]
    assert "id" not in apply(plan, tables(), FakeKeys())["t"].columns
    plan = [e("t", "ts", "ts.month", floor="ts.hour"), *[x for x in PLAN if x["column"] != "ts"]]
    assert "ts" in apply(plan, tables(), FakeKeys())["t"].columns
    plan = [e("t", "ts", "ts.exact", floor="ts.hour"), *[x for x in PLAN if x["column"] != "ts"]]
    with pytest.raises(LadderError):
        apply(plan, tables(), FakeKeys())


def test_unknown_floor_refused():
    with pytest.raises(LadderError):
        apply([e("t", "id", "id.pseudonym", floor="garbage"), *PLAN[1:]], tables(), FakeKeys())


def test_row_order_and_index_preserved():
    out = apply(PLAN, tables(), FakeKeys())["t"]
    assert list(out.index) == [0, 1, 2]
    assert out["ts"].tolist() == ["2025-03-01T14:00", "2025-04-01T01:00", "2025-05-01T05:00"]


def test_no_cell_equals_original_where_generalised():
    out = apply(PLAN, tables(), FakeKeys())["t"]
    assert not set(out["id"]) & {"a", "b", "c"}


def test_real_pseudonymiser_via_adapter_is_hex64_deterministic_and_keyed():
    ps = pytest.importorskip("pets_release.pseudonym")
    master = ps.MasterKey.from_env({"PETS_HMAC_KEY": "k" * 40}) if hasattr(ps.MasterKey, "from_env") else None
    assert master is not None
    scope = ps.Scope.release("0123456789abcdef")

    def run(recipient):
        keys = PseudonymKeys(ps.pseudonymiser_for(master, recipient=recipient), scope)
        return apply(PLAN, tables(), keys)["t"]["id"].tolist()

    a, b, c = run(None), run(None), run("rec-2")
    assert a == b
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in a)
    assert a != c  # recipient-derived keys share no tokens
