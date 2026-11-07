"""Acceptance rule of ``run.purpose.evaluate`` (issue #60), with the adapter's task results substituted.

Rows (after-score per task -> result), HEALTH-S1 policy (sacrifices H-U4/H-U6/H-U8, floor 0.6):
  every task ok >= 0.9                          -> accepted
  non-sacrifice task (H-U2) ok 0.89             -> purpose:H-U2:below-threshold
  sacrifice task (H-U4) ok 0.6 / 0.75           -> accepted (at/above its floor)
  sacrifice task (H-U4) ok 0.59                 -> purpose:H-U4:below-sacrifice-floor
  sacrifice task (H-U4) not_answerable / error  -> never waived
  policy task missing from the kit              -> purpose:H-U7:missing
  kit-required task outside the policy failing  -> refused too
  adapter raises                                -> purpose:unavailable
"""
from __future__ import annotations

import pytest

import pets_release.kiteval as kiteval
from pets_release.policy import get_policy
from pets_release.run.purpose import evaluate

POLICY = get_policy("HEALTH-S1")


def _patch(monkeypatch, after: dict, extra=()):
    def fake(scenario, original, protected, *, root):
        if protected is original:
            return [{"id": t, "score": 1.0, "status": "ok", "required": True} for t in after]
        out = []
        for tid, v in after.items():
            if v == "missing":
                continue
            st, sc = ("ok", v) if isinstance(v, float) else (v, None)
            out.append({"id": tid, "score": sc, "status": st, "required": True})
        return out + list(extra)

    monkeypatch.setattr(kiteval, "purpose_checks", fake)


def _base(**over):
    d = {t: 0.95 for t in POLICY.purpose_checks}
    d.update(over)
    return d


def _run():
    src = {}
    return evaluate(POLICY, src, {"x": None}, root=None)


def test_all_pass(monkeypatch):
    _patch(monkeypatch, _base())
    res = _run()
    assert res.ok and [t["task"] for t in res.tasks] == sorted(POLICY.purpose_checks)
    assert all(t["before"] == 1.0 and t["after"] == 0.95 for t in res.tasks)


@pytest.mark.parametrize("over,reason", [
    ({"H-U2": 0.89}, "purpose:H-U2:below-threshold"),
    ({"H-U4": 0.59}, "purpose:H-U4:below-sacrifice-floor"),
    ({"H-U4": "not_answerable"}, "purpose:H-U4:not_answerable"),
    ({"H-U6": "error"}, "purpose:H-U6:error"),
    ({"H-U7": "missing"}, "purpose:H-U7:missing"),
])
def test_refusal_rows(monkeypatch, over, reason):
    _patch(monkeypatch, _base(**over))
    res = _run()
    assert not res.ok and reason in res.reasons, res.reasons


@pytest.mark.parametrize("score", [0.6, 0.75])
def test_sacrifice_at_or_above_floor_accepted(monkeypatch, score):
    _patch(monkeypatch, _base(**{"H-U4": score}))
    assert _run().ok


def test_kit_required_task_outside_policy_is_enforced(monkeypatch):
    _patch(monkeypatch, _base(), extra=[{"id": "H-U1", "score": None, "status": "error", "required": True}])
    assert "purpose:H-U1:error" in _run().reasons


def test_adapter_failure_is_unavailable(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("value-bearing text")

    monkeypatch.setattr(kiteval, "purpose_checks", boom)
    res = _run()
    assert res.reasons == ("purpose:unavailable",)
