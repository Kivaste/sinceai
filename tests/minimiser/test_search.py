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

Round-1 review fix (final privacy re-check covers every declared privacy target, fail closed):
  F16 a declared target kind the minimiser cannot evaluate      -> test_unevaluable_privacy_target_refuses
  F17 k checks errored/refused/missing, or the k run raises     -> test_k_recheck_error_refuses
  F18 no QI released: k recorded as a vacuous pass below k      -> test_no_qi_released_k_judged_on_unit_count
  F19 policy declaring no target recorded as a pass; k risk
      components without a k target crash                       -> test_no_privacy_targets_not_applicable
  F20 suppression waiver with a via column not coarser than its
      floor on the ladder (alternative floor counted)           -> test_suppression_waiver_needs_via_coarser_on_ladder
  F21 sacrifice score_before is the start score, not the score
      just before the sacrifice took effect                     -> test_score_before_is_pre_suppression_score
  F22 no QI released and a blank person id: hand rule passes k  -> test_no_qi_unidentified_record_suppressed_or_refused
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


# ---------------------------------------------------------------- round-1 review fix: final privacy re-check


def _with_targets(pol, targets):
    return type(pol)(**{**pol.__dict__, "privacy_targets": tuple(targets)})


def _all_ok(task, orig, prot):
    return {"score": 1.0, "status": "ok"}


@pytest.mark.parametrize("target", [
    {"id": "text-recall", "kind": "text_recall", "min": 0.98, "labels": "x"},
    {"id": "no-health-in-text", "kind": "health_in_text", "max_hits": 0},
    {"id": "timestamps-hour", "kind": "timestamp_floor", "rung": "ts.hour"},
])
def test_unevaluable_privacy_target_refuses(syn, target):
    pol = syn.policy()
    pol = _with_targets(pol, (*pol.privacy_targets, target))
    with pytest.raises(MinimiserRefused) as ei:
        _run(syn, pol)
    last = ei.value.log[-1]
    assert last["step"] == "final" and last["accepted"] is False
    assert target["id"] in last["reason"] and target["id"] in ei.value.reason


def _gate(kind):
    def gate(*a, **kw):
        if kind == "raise":
            raise RuntimeError("runner broke")
        recs = [{"check": "producer.person-k", "status": "pass", "hits": 0},
                {"check": "producer.row-k", "status": "pass", "hits": 0}]
        if kind == "refused":
            return {"refused": True, "registryError": None, "records": recs, "vacuous": False}
        if kind == "error":
            recs[0] = dict(recs[0], status="error")
        if kind == "missing":
            recs = recs[:1]
        return {"refused": False, "registryError": None, "records": recs, "vacuous": False}
    return gate


@pytest.mark.parametrize("kind", ["raise", "refused", "error", "missing"])
def test_k_recheck_error_refuses(syn, monkeypatch, kind):
    from pets_release.minimiser import risk
    monkeypatch.setattr(risk, "gate_k", _gate(kind))
    with pytest.raises(MinimiserRefused) as ei:
        _run(syn)
    assert ei.value.log[-1]["step"] == "final" and ei.value.log[-1]["accepted"] is False
    assert "qi-k" in ei.value.reason


def test_no_qi_released_k_judged_on_unit_count(syn):
    # every QI withheld: all 25 persons share one class, so k holds iff 25 >= k (never a vacuous pass)
    res = _run(syn, syn.policy(), purpose=_all_ok)
    assert res.final["privacy_targets"] == [{"id": "qi-k", "kind": "k_anonymity", "status": "pass"}]
    assert res.final["privacy_status"] == "pass"
    with pytest.raises(MinimiserRefused) as ei:
        _run(syn, syn.policy(k=30), purpose=_all_ok)
    assert "qi-k" in ei.value.reason


def test_no_privacy_targets_not_applicable(syn):
    pol = syn.policy()
    pol = _with_targets(type(pol)(**{**pol.__dict__, "suppression": None}), ())
    with pytest.raises(MinimiserRefused, match="k risk components"):
        _run(syn, pol)  # k components cannot be measured without a k target
    pol = type(pol)(**{**pol.__dict__, "risk_vector": ("join_derived_qi", "direct_identifier_leak")})
    res = _run(syn, pol)
    assert res.final["privacy_targets"] == []
    assert res.final["privacy_status"] == "not_applicable"
    assert res.final["privacy"] is None
    assert "not_applicable" in res.log[-1]["reason"]


def test_privacy_targets_recorded_on_pass(syn):
    res = _run(syn)
    assert res.final["privacy_targets"] == [{"id": "qi-k", "kind": "k_anonymity", "status": "pass"}]
    assert res.final["privacy_status"] == "pass"


def test_suppression_waiver_needs_via_coarser_on_ladder(syn):
    # pid's floor is withheld; U-JOIN needs it, so the alternative floor (id.pseudonym) is released. A
    # suppression drop of U-FLAG enumerated via pid is not waived: pid is at its (alternative) floor, not coarser.
    n = len(syn.tables["visits"])

    def purpose(t, orig, prot):
        v = prot.get("visits")
        if t == "U-JOIN" and (v is None or "pid" not in v.columns):
            return {"score": None, "status": "not_answerable"}
        if t == "U-FLAG" and v is not None and len(v) < n:
            return {"score": 0.85, "status": "ok"}
        return syn.purpose(t, orig, prot)

    s = {"check": "U-FLAG", "floor_score": 0.6, "reason": "x", "via": [{"table": "visits", "column": "pid"}]}
    with pytest.raises(MinimiserRefused) as ei:
        _run(syn, syn.policy(sacrifices=(syn.sacrifice, s)), purpose=purpose)
    assert any(e["accepted"] and "alternative floors" in e["reason"] for e in ei.value.log)
    assert "U-FLAG" in ei.value.reason


def test_score_before_is_pre_suppression_score(syn):
    # U-FLAG scores 1.0 while spare is released (start) and 0.95 once spare is withheld (strict search), then
    # 0.85 after suppression: score_before is the score just before the sacrifice took effect (0.95)
    n = len(syn.tables["visits"])

    def purpose(t, orig, prot):
        v = prot.get("visits")
        if t == "U-FLAG" and v is not None and "flag" in v.columns:
            if len(v) < n:
                return {"score": 0.85, "status": "ok"}
            return {"score": 1.0 if "spare" in v.columns else 0.95, "status": "ok"}
        return syn.purpose(t, orig, prot)

    s = {"check": "U-FLAG", "floor_score": 0.6, "reason": "x", "via": [{"table": "visits", "column": "dob"}]}
    res = _run(syn, syn.policy(sacrifices=(syn.sacrifice, s)), purpose=purpose)
    got = {x["check"]: x for x in res.sacrifices}
    assert got["U-FLAG"]["score_before"] == 0.95 and got["U-FLAG"]["score_after"] == 0.85
    assert got["U-TOWN"]["score_before"] == 1.0


def _blank_person(syn):
    tables = {t: df.copy() for t, df in syn.tables.items()}
    tables["visits"].loc[0, "pid"] = ""  # one unidentified record
    return tables


def test_no_qi_unidentified_record_suppressed_or_refused(syn):
    # no QI released: the production person-k check still runs (one class); an unidentified record is always
    # a hit, so suppression drops it, and without suppression the plan is refused
    tables = _blank_person(syn)
    res = search(syn.policy(), tables, syn.keys, purpose=_all_ok, params=syn.params, kspec=syn.kspec)
    assert res.suppressed["visits"] and 0 in res.suppressed["visits"]
    assert res.final["privacy_status"] == "pass"
    recs = {r["check"]: r for r in res.final["privacy"]["records"]}
    assert recs["producer.person-k"]["status"] == "pass" and recs["producer.person-k"]["hits"] == 0
    assert "vacuous" not in res.final["privacy"]
    pol = syn.policy()
    pol = type(pol)(**{**pol.__dict__, "suppression": None})
    with pytest.raises(MinimiserRefused) as ei:
        search(pol, tables, syn.keys, purpose=_all_ok, params=syn.params, kspec=syn.kspec)
    assert "qi-k" in ei.value.reason