"""Follow-up #89: ``ts.hour_of_day`` is coarser than ``ts.month`` and only ever adopted as an enumerated sacrifice.

Seam: ``pets_release.minimiser.search`` (ticket 24's seam; the CLI's ``run`` only takes ``--plan hand``, so the
search is not reachable from the CLI). Synthetic rows only (conftest).

Rule: on the privacy order hour_of_day (date-free ``HH:00``) is coarser than month; a step from month+hour toward
it is never an ordinary coarsening step. The search adopts it only through a policy-enumerated rung sacrifice,
only when k measurably fails at month+hour (shortfall above the suppression budget) and the sacrifice's check
still passes strictly at hour_of_day, and records the measured scores; missing scores refuse.

Failure rows (trigger -> wrong result before the fix):
  R1 no rung sacrifice enumerated, date rungs fail U-HOUR -> strict coarsening adopts hour_of_day
                                                            -> test_strict_coarsening_never_adopts_hour_of_day
  R2 every date rung passes, no rung sacrifice -> walk passes through hour_of_day as a small step
                                                            -> test_hour_of_day_never_a_small_step_after_month
  R3 rung sacrifice enumerated, k fails at month+hour -> adopted without a recorded k/check score
                                                            -> test_rung_sacrifice_adopted_and_recorded_when_k_fails
  R4 rung sacrifice enumerated, k passes at month+hour -> hour_of_day adopted anyway
                                                            -> test_rung_sacrifice_not_adopted_when_k_passes
"""

from __future__ import annotations

import dataclasses

from pets_release.minimiser import search


def _run(syn, policy=None, tables=None, purpose=None):
    return search(policy or syn.policy(), tables or syn.tables, syn.keys, purpose=purpose or syn.purpose,
                  params=syn.params, kspec=syn.kspec)


def _rung(res, col="ts"):
    return {(e["table"], e["column"]): e["rung"] for e in res.plan}[("visits", col)]


def _ts_moves(res):
    return [m["rung"] for e in res.log if e["step"] != "final" and e["accepted"] for m in e["moves"]
            if m["column"] == "ts"]


def test_strict_coarsening_never_adopts_hour_of_day(syn):
    res = _run(syn)
    assert _rung(res) == "ts.month_hour"  # day/week/month fail U-HOUR; hour_of_day is not enumerated
    assert "ts.hour_of_day" not in _ts_moves(res)


def test_hour_of_day_never_a_small_step_after_month(syn):
    def purpose(task, orig, prot):
        if task == "U-HOUR":
            v = prot.get("visits")
            return {"score": 1.0, "status": "ok"} if v is not None and "ts" in v.columns else {
                "score": None, "status": "not_answerable"}
        return syn.purpose(task, orig, prot)

    res = _run(syn, purpose=purpose)
    # every rung passes U-HOUR; the walk stops on risk, and hour_of_day (beyond month, sacrifice-only) is
    # never even a candidate of an ordinary step
    assert _rung(res) in ("ts.month_hour", "ts.day", "ts.week", "ts.month")
    tried = [m["rung"] for e in res.log for m in e["moves"] if m["column"] == "ts"]
    assert "ts.hour_of_day" not in tried


HOUR_SACRIFICE = {"check": "U-HOUR", "floor_score": 0.5, "reason": "coarser visit time to reach k",
                  "via": [{"table": "visits", "column": "ts"}]}
HOUR_STEP = {"check": "U-HOUR", "table": "visits", "column": "ts", "from": "ts.month_hour", "to": "ts.hour_of_day",
             "reason": "hour of day only, if k fails at month+hour"}


def _with_step(syn, **kw):
    pol = syn.policy(**kw)
    return dataclasses.replace(pol, sacrifices=(*pol.sacrifices, HOUR_SACRIFICE), rung_sacrifices=(HOUR_STEP,))


def _flat(syn):
    """One town, one visit instant: k holds at month+hour (only the lone third-decade person is below k)."""
    t = {k: v.copy() for k, v in syn.tables.items()}
    t["visits"]["town"] = "Ta"
    t["visits"]["ts"] = "2025-01-10 08:15:00"
    return t


def test_rung_sacrifice_adopted_and_recorded_when_k_fails(syn):
    res = _run(syn, policy=_with_step(syn))  # synthetic rows: k shortfall at month+hour is above the 0.25 budget
    assert _rung(res) == "ts.hour_of_day"
    (rec,) = [s for s in res.sacrifices if "rung_step" in s]
    assert rec["check"] == "U-HOUR" and rec["score_after"] == 1.0
    step = rec["rung_step"]
    assert (step["table"], step["column"], step["from"], step["to"]) == ("visits", "ts", "ts.month_hour",
                                                                        "ts.hour_of_day")
    assert step["max_share"] == 0.25 and step["k_shortfall_at_from"] > step["max_share"]
    assert step["check_score_at_to"] == 1.0
    adopted = [e for e in res.log if e["accepted"] and any(m["rung"] == "ts.hour_of_day" for m in e["moves"])]
    assert len(adopted) == 1 and adopted[0]["reason"].startswith("sacrifice: rung step visits.ts")


def test_rung_sacrifice_not_adopted_when_k_passes(syn):
    res = _run(syn, policy=_with_step(syn), tables=_flat(syn))
    assert _rung(res) == "ts.month_hour"
    assert not [s for s in res.sacrifices if "rung_step" in s]