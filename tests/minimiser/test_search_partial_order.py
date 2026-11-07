"""Follow-up #89 round 1: the search treats the timestamp ladder as a partial order.

Rule the change adds: ``ts.hour_of_day`` (date-free) is not comparable with ``ts.day``/``ts.week``/``ts.month``.
The search never moves a column between incomparable rungs as a "coarsening", explores the date branch and the
hour-of-day branch independently from ``ts.month_hour``, and never ranks one incomparable rung above the other
on a risk tie (the earlier candidate is kept).

Failure rows (trigger -> result):
  P1 equal risks, joint move hour_of_day -> day ranked strictly better (index coarseness) and adopted
                                                          -> test_tie_never_prefers_incomparable_rung
  P2 hour_of_day rejected stops the walk before the date rungs   -> test_rejected_hour_of_day_still_walks_dates
  P3 floor hour_of_day: search walks to day/week/month (search.py ladder() index slice)
                                                          -> test_hour_of_day_floor_never_walks_to_dates
  P4 a date rung counted coarser than an hour_of_day floor (search.py _coarser_than_floor index compare)
                                                          -> test_coarser_than_floor_is_partial_order
Synthetic hand-made rows only.
"""

from __future__ import annotations

import hashlib
import re

import pandas as pd
import pytest

from pets_release.minimiser import search
from pets_release.minimiser.search import _Search
from pets_release.policy.model import FieldFloor, ScenarioPolicy

DATE_RUNGS = ("ts.day", "ts.week", "ts.month")


class _Keys:
    def token(self, value, label="RECORD_KEY"):
        return hashlib.sha256(f"po\0{label}\0{value}".encode()).hexdigest()


def _tables():
    rows = {"pid": [], "ts": [], "x": []}
    for i in range(12):
        rows["pid"].append(f"P{i:02d}")
        rows["ts"].append(f"2025-0{1 + i % 3}-1{i % 9} {8 + i % 4:02d}:{i % 6}5:00")
        rows["x"].append("a" if i % 2 else "b")
    return {"v": pd.DataFrame(rows, dtype=str)}


def _policy(ts_floor, checks, joint=()):
    return ScenarioPolicy(
        scenario="PO-S1", dataset="po", purpose_checks=tuple(checks), privacy_targets=(),
        floors={("v", "pid"): FieldFloor("identifier", "withheld", "direct identifier"),
                ("v", "ts"): FieldFloor("timestamp", ts_floor, "QI"),
                ("v", "x"): FieldFloor("categorical", "keep", "QI")},
        direct_identifiers=(("v", "pid"),),
        qi=({"table": "v", "column": "ts", "derived": "ts"}, {"table": "v", "column": "x", "derived": "x"}),
        risk_vector=("direct_identifier_leak",),  # 0 for every candidate: every comparison is a risk tie
        sacrifices=(), joint_qi_moves=tuple(joint), linked=(), param_minimums={},
    )


def _ts(prot):
    v = prot.get("v")
    return None if v is None or "ts" not in v.columns else v["ts"]


def _hour_only(s):
    return s is not None and s.map(lambda c: bool(re.fullmatch(r"\d{2}:00", c))).all()


def _date_only(s):
    return s is not None and not s.str.contains(":").any()


def _ok(cond):
    return {"score": 1.0 if cond else 0.0, "status": "ok"}


def purpose(task, orig, prot):
    s, v = _ts(prot), prot.get("v")
    has_x = v is not None and "x" in v.columns
    if task == "C":  # needs the timestamp released
        return _ok(s is not None)
    if task == "A":  # a date-form timestamp together with x fails
        return _ok(not (_date_only(s) and has_x))
    if task == "B":  # needs x, or a date-form timestamp
        return _ok(has_x or _date_only(s))
    if task == "H":  # fails on the date-free hour-of-day rung
        return _ok(not _hour_only(s))
    raise AssertionError(task)


def _run(policy):
    return search(policy, _tables(), _Keys(), purpose=purpose)


def _rung(res, col):
    return {e["column"]: e["rung"] for e in res.plan}[col]


def _ts_moves(res, accepted=None):
    return [m["rung"] for e in res.log if e["step"] != "final" and (accepted is None or e["accepted"] == accepted)
            for m in e["moves"] if m["column"] == "ts"]


def test_tie_never_prefers_incomparable_rung():
    # coarsening adopts hour_of_day (day fails A while x is released); the joint move {ts: day, x: withheld}
    # passes every check at the same risk, but day is not coarser than hour_of_day: the earlier plan stays
    pol = _policy("ts.month_hour", ("A", "B", "C"),
                  joint=(({"table": "v", "column": "ts", "rung": "ts.day"},
                          {"table": "v", "column": "x", "rung": "withheld"}),))
    res = _run(pol)
    assert _rung(res, "ts") == "ts.hour_of_day"
    assert _rung(res, "x") == "keep"
    assert "ts.day" in _ts_moves(res, accepted=False)  # the joint move was measured, and rejected
    assert not any(r in DATE_RUNGS for r in _ts_moves(res, accepted=True))


def test_rejected_hour_of_day_still_walks_dates():
    res = _run(_policy("ts.month_hour", ("C", "H")))
    assert _rung(res, "ts") == "ts.month"
    assert "ts.hour_of_day" in _ts_moves(res, accepted=False)
    assert [r for r in _ts_moves(res, accepted=True) if r in DATE_RUNGS] == list(DATE_RUNGS)


def test_hour_of_day_floor_never_walks_to_dates():
    res = _run(_policy("ts.hour_of_day", ("C",)))
    assert _rung(res, "ts") == "ts.hour_of_day"
    assert not any(r in DATE_RUNGS for r in _ts_moves(res))


@pytest.mark.parametrize("floor,rung,want", [
    ("ts.hour_of_day", "ts.day", False), ("ts.hour_of_day", "ts.month", False),
    ("ts.day", "ts.hour_of_day", False), ("ts.month_hour", "ts.hour_of_day", True),
    ("ts.month_hour", "ts.day", True), ("ts.hour_of_day", "withheld", True),
    ("ts.hour_of_day", "ts.hour_of_day", False), ("ts.exact", "ts.hour", True),
])
def test_coarser_than_floor_is_partial_order(floor, rung, want):
    s = _Search(_policy(floor, ("C",)), _tables(), _Keys(), purpose=purpose, purpose_all=None, kspec=None,
                budget=10, read_sets={}, params=None, redactor=None, risk_extra=None)
    assert s._coarser_than_floor(("v", "ts"), rung) is want
    assert all(r == floor or r == "withheld" or s._coarser_than_floor(("v", "ts"), r)
               for r in s.ladder(("v", "ts"), floor))
