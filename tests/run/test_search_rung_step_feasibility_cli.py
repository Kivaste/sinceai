"""The #128 record-key infeasibility check also guards the enumerated rung-sacrifice adopt path (#127 scope,
final review pass 4), through `pets-release run` (in-process CLI, synthetic rows only).

Rule: a candidate that drops a released table's record key is infeasible: the search never evaluates or adopts
it, on every adopt path, including the enumerated rung sacrifice (#89). Fail closed.

Rows (trigger -> result):
  start already drops lab_results.lab_id (policy floor patched to withheld) and arrival_ts starts at the
  sacrifice's `from` (floor patched to ts.month_hour), on a kit where k fails at month+hour beyond budget:
    before the fix -> the rung step is evaluated and logged "adopted" (finish() still refuses the run)
    after the fix  -> no rung-step candidate is evaluated or adopted; the run refuses (exit 1), nothing published
"""
from __future__ import annotations

import dataclasses
import json

from run_helpers import CREATED, TEST_KEY, build_kit, grouped_spread_arrivals


def _patched_policy(policy):
    floors = dict(policy.floors)
    floors[("lab_results", "lab_id")] = dataclasses.replace(floors[("lab_results", "lab_id")], rung="withheld")
    floors[("ed_visits", "arrival_ts")] = dataclasses.replace(floors[("ed_visits", "arrival_ts")],
                                                             rung="ts.month_hour")
    return dataclasses.replace(policy, floors=floors)


def test_rung_sacrifice_never_adopts_a_candidate_that_drops_a_record_key(tmp_path, monkeypatch, capsys):
    from pets_release.policy import get_policy
    from pets_release.run import cli as run_cli
    from pets_release.run import pipeline

    kit = build_kit(tmp_path / "kit", grouped_spread_arrivals)
    out = tmp_path / "out" / "rel"
    patched = _patched_policy(get_policy("HEALTH-S1"))
    monkeypatch.setattr(pipeline, "get_policy", lambda sid: patched)
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    rc = run_cli.main(["--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED])
    stdout = capsys.readouterr().out
    assert rc == 1, stdout
    assert not out.exists()
    log = [json.loads(x) for x in (out.parent / "rel.scoring" / "search_log.jsonl").read_text(
        encoding="utf-8").splitlines() if x]
    assert log and log[0]["accepted"] is True  # the start was taken, so the sacrifice phase was reachable
    steps = [e for e in log if str(e["reason"]).startswith("sacrifice: rung step")]
    assert steps == [], "rung-sacrifice candidate dropping a record key was evaluated: " + ",".join(
        f"{e['step']}:{e['accepted']}" for e in steps)
