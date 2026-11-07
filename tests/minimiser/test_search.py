"""Minimiser (ticket 24): deterministic bounded search, seam = ``pets_release.minimiser.search``.

Rule the change adds: the minimiser picks, per field, the coarsest rung at or above its policy floor at which
every purpose check passes (score >= 0.9, status ok), or passes only through a policy-enumerated sacrifice at or
above its floor score; errors and unknowns are never waived; local suppression comes last and is followed by a
full, uncached re-check of every purpose check and the k target (production person-k check, 04's runner).

Failure rows (trigger -> result):
  F1 same input twice -> different log/plan bytes              -> test_same_input_identical_log_and_plan
  F2 non-enumerated check below 0.9 adopted                    -> test_non_enumerated_failure_never_adopted
  F3 enumerated sacrifice below its floor score adopted        -> test_sacrifice_below_floor_never_adopted
  F4 sacrifice adopted via a column not in its ``via``         -> test_sacrifice_only_via_its_columns
  F5 error/not_answerable waived (even with a high score)      -> test_errors_never_waived
  F6 suppression without full re-check / re-check on cache     -> test_full_recheck_after_suppression
  F7 re-check fails after suppression but plan still returned  -> test_recheck_failure_refuses
  F8 more candidates than the bound                            -> test_bound_respected_and_logged
  F9 nothing accepted but a plan returned                      -> test_no_accepted_candidate_refuses
  F10 plan finer than floor / wrong shape / source not search  -> test_plan_valid_against_policy
  F11 log entry with unknown/missing keys                      -> test_log_entries_closed_shape
  F12 row values in the log                                    -> test_log_is_content_free
  F13 cache serves a result whose read columns changed         -> test_cache_hits_only_on_unchanged_read_columns
  F14 suppression beyond the policy's max share returned       -> test_suppression_over_budget_refuses
  F15 risk component the minimiser cannot measure silently 0   -> test_unknown_risk_component_refuses
"""

from __future__ import annotations

import json

import pytest

from pets_release.minimiser import LOG_KEYS, MinimiserRefused, search, write_search_log
from pets_release.policy import validate_plan


def _run(syn, policy=None, purpose=None, **kw):
    kw.setdefault("params", syn.params)
    kw.setdefault("kspec", syn.kspec)
    return search(policy or syn.policy(), syn.tables, syn.keys, purpose=purpose or syn.purpose, **kw)


def _rungs(res):
    return {(e["table"], e["column"]): e["rung"] for e in res.plan}


def _candidates(res):
    return [e for e in res.log if e["step"] != "final"]


def _adopted(res):
    return [e for e in _candidates(res) if e["accepted"]]


def test_same_input_identical_log_and_plan(syn, tmp_path):
    a, b = _run(syn), _run(syn)
    pa, pb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_search_log(pa, a.log)
    write_search_log(pb, b.log)
    assert pa.read_bytes() == pb.read_bytes()
    assert json.dumps(a.plan, sort_keys=True) == json.dumps(b.plan, sort_keys=True)
    assert a.suppressed == b.suppressed


def test_plan_valid_against_policy(syn):
    pol = syn.policy()
    res = _run(syn, pol)
    validate_plan(res.plan, pol)  # raises on finer-than-floor, unknown keys, missing columns
    assert {e["source"] for e in res.plan} == {"search"}
    r = _rungs(res)
    # unused fields withheld; needed ones at the coarsest rung that still passes
    assert r[("visits", "spare")] == "withheld"
    assert r[("labs", "val")] == "withheld"
    assert r[("visits", "flag")] == "keep"
    assert r[("visits", "dx")] == "icd.3"  # chapter scores 0 on U-DX
    assert r[("visits", "ts")] == "ts.hour_of_day"  # day has no hour (U-HOUR)
    assert r[("visits", "dob")] == "age.band10"
    assert r[("visits", "visit_id")] == r[("labs", "visit_id")] == "id.pseudonym"  # linked, U-JOIN


def _log_or_refusal(fn):
    try:
        return fn().log, None
    except MinimiserRefused as e:
        assert e.log  # a refusal carries the search log
        return e.log, e


def test_non_enumerated_failure_never_adopted(syn):
    log, _ = _log_or_refusal(lambda: _run(syn, syn.policy(sacrifices=())))
    adopted = [e for e in log if e["accepted"] and e["step"] != "final"]
    assert adopted
    for e in adopted:
        assert all(s is not None and s >= 0.9 for s in e["scores"].values())
    assert not any(m["column"] == "town" and m["rung"] == "geo.topn" for e in adopted for m in e["moves"])


def test_enumerated_sacrifice_adopted_when_needed(syn):
    res = _run(syn)
    assert _rungs(res)[("visits", "town")] == "geo.topn"
    assert [s["check"] for s in res.sacrifices] == ["U-TOWN"]
    s = res.sacrifices[0]
    assert s["floor_score"] == 0.4 and s["score_after"] >= 0.4 and s["score_before"] >= 0.9


def test_sacrifice_below_floor_never_adopted(syn):
    high = dict(syn.sacrifice, floor_score=0.8)  # topn scores 3/6 = 0.5 < 0.8
    log, _ = _log_or_refusal(lambda: _run(syn, syn.policy(sacrifices=(high,))))
    for e in log:
        if e["accepted"] and e["step"] != "final":
            assert e["scores"]["U-TOWN"] >= 0.9


def test_sacrifice_only_via_its_columns(syn):
    # U-DX enumerated as a sacrifice, but via town: coarsening dx to chapter (U-DX = 0) must stay rejected,
    # and so must any dx move scoring below 0.9 even above the floor.
    pol = syn.policy(sacrifices=(syn.sacrifice, {"check": "U-DX", "floor_score": 0.0, "reason": "x",
                                                 "via": [{"table": "visits", "column": "town"}]}))
    res = _run(syn, pol)
    assert _rungs(res)[("visits", "dx")] == "icd.3"


def test_sacrifice_needs_its_own_via_column(syn):
    # U-TOWN is enumerated but attributed to dx; grouping towns (a via column of another sacrifice) must not
    # waive it.
    pol = syn.policy(sacrifices=(dict(syn.sacrifice, via=[{"table": "visits", "column": "dx"}]),
                                 {"check": "U-DX", "floor_score": 0.0, "reason": "x",
                                  "via": [{"table": "visits", "column": "town"}]}))
    log, _ = _log_or_refusal(lambda: _run(syn, pol))
    for e in log:
        if e["accepted"] and e["step"] != "final":
            assert e["scores"]["U-TOWN"] >= 0.9


def test_errors_never_waived(syn):
    def purpose(task, orig, prot):
        r = syn.purpose(task, orig, prot)
        if task == "U-TOWN" and "town" in prot["visits"].columns and prot["visits"]["town"].nunique() < 6:
            return {"score": 0.95, "status": "error"}  # high score, but an error
        return r

    pol = syn.policy(sacrifices=(dict(syn.sacrifice, floor_score=0.0),))
    log, _ = _log_or_refusal(lambda: _run(syn, pol, purpose=purpose))
    for e in log:
        if e["accepted"]:
            assert e["scores"]["U-TOWN"] is not None and e["scores"]["U-TOWN"] >= 0.9


def test_raising_check_is_an_error_never_waived(syn):
    def purpose(task, orig, prot):
        if task == "U-TOWN" and "town" in prot["visits"].columns and prot["visits"]["town"].nunique() < 6:
            raise ValueError("boom")
        return syn.purpose(task, orig, prot)

    pol = syn.policy(sacrifices=(dict(syn.sacrifice, floor_score=0.0),))
    log, _ = _log_or_refusal(lambda: _run(syn, pol, purpose=purpose))
    assert any(e["scores"]["U-TOWN"] is None for e in log)  # the raising candidate was logged, not fatal
    for e in log:
        if e["accepted"]:
            assert e["scores"]["U-TOWN"] is not None and e["scores"]["U-TOWN"] >= 0.9


def test_full_recheck_after_suppression(syn):
    calls = []

    def purpose(task, orig, prot):
        calls.append((task, len(prot["visits"])))
        return syn.purpose(task, orig, prot)

    res = _run(syn, purpose=purpose)
    n = len(syn.tables["visits"])
    kept = n - len(res.suppressed["visits"])
    assert res.suppressed["visits"], "fixture should need suppression"
    final = [c for c in calls if c[1] == kept]
    assert sorted(t for t, _ in final) == sorted(syn.checks)  # every purpose check, uncached, on suppressed data
    assert res.final["purpose"] and {r["id"] for r in res.final["purpose"]} == set(syn.checks)
    k = {r["check"]: r for r in res.final["privacy"]["records"]}
    assert k["producer.person-k"]["status"] == "pass"  # production check via 04's runner
    assert k["producer.person-k"]["hits"] == 0
    assert res.log[-1]["step"] == "final" and res.log[-1]["accepted"] is True
    assert res.log[-1]["cached"] is False


def test_recheck_failure_refuses(syn):
    n = len(syn.tables["visits"])

    def purpose(task, orig, prot):
        if task == "U-FLAG" and len(prot["visits"]) < n:
            return {"score": 0.5, "status": "ok"}  # suppression breaks this check
        return syn.purpose(task, orig, prot)

    with pytest.raises(MinimiserRefused) as ei:
        _run(syn, purpose=purpose)
    assert ei.value.log[-1]["step"] == "final" and ei.value.log[-1]["accepted"] is False


def _drop_on_suppression(syn, task, score):
    n = len(syn.tables["visits"])

    def purpose(t, orig, prot):
        if t == task and len(prot["visits"]) < n:
            return {"score": score, "status": "ok"}
        return syn.purpose(t, orig, prot)

    return purpose


def test_suppression_drop_waived_for_enumerated_sacrifice_in_effect(syn):
    # U-FLAG enumerated via dob (coarsened past its floor): a suppression-caused drop above the floor is waived
    s = {"check": "U-FLAG", "floor_score": 0.6, "reason": "suppression to reach k",
         "via": [{"table": "visits", "column": "dob"}]}
    res = _run(syn, syn.policy(sacrifices=(syn.sacrifice, s)), purpose=_drop_on_suppression(syn, "U-FLAG", 0.85))
    got = {x["check"]: x for x in res.sacrifices}
    assert got["U-FLAG"]["score_after"] == 0.85 and got["U-FLAG"]["score_before"] == 1.0


def test_suppression_drop_below_floor_refuses(syn):
    s = {"check": "U-FLAG", "floor_score": 0.6, "reason": "x", "via": [{"table": "visits", "column": "dob"}]}
    with pytest.raises(MinimiserRefused):
        _run(syn, syn.policy(sacrifices=(syn.sacrifice, s)), purpose=_drop_on_suppression(syn, "U-FLAG", 0.5))


def test_suppression_drop_refuses_when_via_at_floor(syn):
    s = {"check": "U-FLAG", "floor_score": 0.6, "reason": "x", "via": [{"table": "visits", "column": "flag"}]}
    with pytest.raises(MinimiserRefused):
        _run(syn, syn.policy(sacrifices=(syn.sacrifice, s)), purpose=_drop_on_suppression(syn, "U-FLAG", 0.85))


def test_suppression_drop_error_never_waived(syn):
    s = {"check": "U-FLAG", "floor_score": 0.0, "reason": "x", "via": [{"table": "visits", "column": "dob"}]}
    n = len(syn.tables["visits"])

    def purpose(t, orig, prot):
        if t == "U-FLAG" and len(prot["visits"]) < n:
            return {"score": 0.99, "status": "error"}
        return syn.purpose(t, orig, prot)

    with pytest.raises(MinimiserRefused):
        _run(syn, syn.policy(sacrifices=(syn.sacrifice, s)), purpose=purpose)


def test_suppression_k_must_match_k_target(syn):
    pol = syn.policy()
    pol = type(pol)(**{**pol.__dict__, "suppression": dict(pol.suppression, k=2)})
    with pytest.raises(MinimiserRefused):
        _run(syn, pol)


def test_suppression_over_budget_refuses(syn):
    with pytest.raises(MinimiserRefused):
        _run(syn, syn.policy(max_share=0.01))


def test_bound_respected_and_logged(syn):
    try:
        res = _run(syn, budget=6)
        log, stats = res.log, res.stats
    except MinimiserRefused as e:  # bound hit before k was reachable: refusal, still logged
        log, stats = e.log, e.stats
    cands = [e for e in log if e["step"] != "final"]
    assert len(cands) <= 6
    assert log[-1]["step"] == "final" and "bound" in log[-1]["reason"]
    assert stats["candidates"] == len(cands) and stats["bound_reached"] is True


def test_no_accepted_candidate_refuses(syn):
    def purpose(task, orig, prot):
        return {"score": None, "status": "error"} if task == "U-FLAG" else syn.purpose(task, orig, prot)

    with pytest.raises(MinimiserRefused):
        _run(syn, purpose=purpose)


def test_log_entries_closed_shape(syn):
    res = _run(syn)
    assert LOG_KEYS == {"step", "candidate_digest", "moves", "scores", "risk", "accepted", "reason", "cached"}
    for e in res.log:
        assert set(e) == LOG_KEYS
        assert all(set(m) == {"table", "column", "rung"} for m in e["moves"])
        assert set(e["scores"]) == set(syn.checks)
        assert len(e["candidate_digest"]) == 64


def test_log_is_content_free(syn, tmp_path):
    res = _run(syn)
    p = tmp_path / "log.jsonl"
    write_search_log(p, res.log)
    text = p.read_text(encoding="utf-8")
    values = set()
    for df in syn.tables.values():
        for c in df.columns:
            values |= set(df[c])
    leaked = sorted(v for v in values if len(v) >= 3 and f'"{v}"' in text)
    assert not leaked


def test_cache_hits_only_on_unchanged_read_columns(syn):
    read_sets = {t: {"visits": ["flag"]} for t in ("U-FLAG",)}
    calls = []

    def purpose(task, orig, prot):
        calls.append(task)
        return syn.purpose(task, orig, prot)

    res = _run(syn, purpose=purpose, read_sets=read_sets)
    assert res.stats["cache_hits"] > 0
    flag_calls = calls.count("U-FLAG")
    # U-FLAG recomputed only when the flag column changed (start, withhold-flag try, final re-check)
    assert flag_calls <= 4
    # unknown read sets are never cached across different candidates
    calls.clear()
    _run(syn, purpose=purpose)
    assert calls.count("U-JOIN") >= len({e["candidate_digest"] for e in _candidates(res)}) - 1


def test_unknown_risk_component_refuses(syn):
    pol = syn.policy()
    pol = type(pol)(**{**pol.__dict__, "risk_vector": pol.risk_vector + ("text_recall_shortfall",)})
    with pytest.raises(MinimiserRefused):
        _run(syn, pol)
