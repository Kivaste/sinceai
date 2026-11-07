"""Justification writer (ticket 25), seam = ``pets_release.run.justify``. Hand-made log rows, schema names only.

Rule: each field's reason cites the log step it comes from; plan/log disagreement fails closed. Rows:
  field moved by an accepted step                 -> cites that step; a later rejected try is cited too
  field at floor, a rejected try                  -> cites the rejected step ("kept at floor")
  field withheld at its floor, never tried         -> cites step 0
  field withheld at its floor, rejected tries      -> cites the last rejected step that touched it
  plan rung differs from its adopting step         -> JustificationError
  field off its floor with no adopting step        -> JustificationError
  log without a start step                         -> JustificationError
  measured.search                                  -> one point per non-final entry; final entry excluded;
                                                      an unscored rejected entry has utility null (#133;
                                                      refusals: test_search_summary_unmeasured and, for
                                                      omitted members (#150), test_search_summary_omitted_members,
                                                      CLI seam)
"""
from __future__ import annotations

import types

import pytest

from pets_release.run.justify import JustificationError, justify, search_summary

FLOORS = {("t", "a"): types.SimpleNamespace(reason="QI"), ("t", "b"): types.SimpleNamespace(reason="H-U1"),
          ("t", "c"): types.SimpleNamespace(reason="direct identifier")}
POLICY = types.SimpleNamespace(floors=FLOORS, purpose_checks=("H-U1",), risk_vector=("qi_k_shortfall",))


def _e(step, moves, accepted, reason, risk=0.5, score=1.0):
    return {"step": step, "candidate_digest": "0" * 64, "moves": [{"table": "t", "column": c, "rung": r}
                                                                   for c, r in moves],
            "scores": {"H-U1": score}, "risk": {"qi_k_shortfall": risk}, "accepted": accepted, "reason": reason,
            "cached": False}


LOG = [
    _e(0, [("a", "geo.full"), ("b", "keep")], True, "start: every permitted field at its floor: adopted"),
    _e(1, [("b", "withheld")], False, "withhold t.b: rejected (H-U1 below 0.9 or not ok)", score=None),
    _e(2, [("a", "geo.topn")], True, "coarsen t.a to geo.topn: adopted", risk=0.2),
    _e(3, [("a", "withheld")], False, "coarsen t.a to withheld: rejected (H-U1 below 0.9 or not ok)", score=0.1),
    _e("final", [], True, "final: passed"),
]


def _plan(a="geo.topn", b="keep", afloor="geo.full"):
    return [{"table": "t", "column": "a", "rung": a, "params": {}, "floor": afloor, "reason": "x", "source": "search"},
            {"table": "t", "column": "b", "rung": b, "params": {}, "floor": "keep", "reason": "x", "source": "search"},
            {"table": "t", "column": "c", "rung": "withheld", "params": {}, "floor": "withheld", "reason": "x",
             "source": "search"}]


def test_reasons_cite_their_steps():
    fj = {f["column"]: f for f in justify(_plan(), LOG, POLICY)}
    assert fj["a"]["reason"].startswith("search step 2: geo.topn adopted")
    assert "search step 3: tried withheld, rejected (H-U1" in fj["a"]["reason"]
    assert fj["b"]["reason"].startswith("search step 1: kept at floor keep; tried withheld, rejected (H-U1")
    assert fj["c"]["reason"].startswith("search step 0: withheld at the policy floor (direct identifier)")
    assert fj["c"]["decision"] == "withheld" and fj["c"]["outputColumn"] is None
    assert {f["source"] for f in fj.values()} == {"search"}


def test_withheld_at_floor_cites_the_last_rejected_try():
    """A floor-withheld field that a step tried to move cites that step (the last such), not step 0."""
    log = LOG[:4] + [
        _e(4, [("c", "keep")], False, "release t.c as keep: rejected (qi_k_shortfall above bound)"),
        _e(5, [("c", "hash")], False, "release t.c as hash: rejected (qi_k_shortfall above bound)"),
        LOG[4]]
    fj = {f["column"]: f for f in justify(_plan(), log, POLICY)}
    r = fj["c"]["reason"]
    assert r.startswith("search step 5: withheld at the policy floor; tried hash, rejected (qi_k_shortfall"), r
    assert r.endswith("(direct identifier)") and "search step 0" not in r
    assert fj["c"]["decision"] == "withheld"


def test_plan_rung_differs_from_adopting_step_fails():
    with pytest.raises(JustificationError):
        justify(_plan(a="geo.full"), LOG[:3] + [LOG[4]], POLICY)  # step 2 adopted geo.topn, plan says geo.full


def test_off_floor_without_adopting_step_fails():
    with pytest.raises(JustificationError):
        justify(_plan(b="withheld"), LOG, POLICY)


def test_log_without_start_fails():
    with pytest.raises(JustificationError):
        justify(_plan(), LOG[1:], POLICY)


def test_search_summary_points():
    s = search_summary(LOG, {"bound_reached": False}, POLICY)
    assert s["status"] == "measured" and s["candidates"] == 4 and s["accepted"] == 2
    assert [p["step"] for p in s["points"]] == [0, 1, 2, 3]
    assert s["points"][1] == {"step": 1, "risk": 0.5, "utility": None, "accepted": False}  # unscored: null (#133)
    assert s["points"][3]["utility"] == 0.1
    assert s["boundReached"] is False
