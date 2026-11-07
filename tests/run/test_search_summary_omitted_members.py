"""`measured.search` never publishes an omitted score or risk member as measured (#150, gap in #133).

Seam: `pets-release run` (no --plan), in-process; the real search runs on the synthetic minikit and one log entry
is altered at the boundary where `run` receives the search result (as in test_search_summary_unmeasured).
Synthetic only.

Rule: a non-final search-log entry carries exactly the expected members: one score per policy purpose check and one
risk component per policy risk-vector component. An omitted member is unknown, never measured. An omitted or
unknown risk component, an unknown score member, or an accepted step with an omitted score makes `run` refuse
fail-closed (exit 2, no release folder). A rejected candidate with an omitted score has `utility: null` (#133).

Failure rows (trigger -> wrong result before the fix):
  an accepted step omits a score member    -> released, utility = mean of the remaining scores, status measured
                                                          -> test_accepted_step_omitting_a_score_refuses
  an accepted step omits a risk component  -> released, risk = max of the remaining components, status measured
                                                          -> test_accepted_step_omitting_a_risk_component_refuses
  a rejected step omits a risk component   -> released, risk = max of the remaining components
                                                          -> test_rejected_step_omitting_a_risk_component_refuses
  a step carries an unknown risk component -> released, the stray figure counted as measured risk
                                                          -> test_unknown_risk_component_refuses
  a step carries an unknown score member   -> released, the stray figure averaged into utility
                                                          -> test_unknown_score_member_refuses
  a rejected step omits a score member     -> released, utility = mean of the remaining scores (a stand-in)
                                                          -> test_rejected_step_omitting_a_score_is_null
"""
from __future__ import annotations

import json

import pytest
from test_search_summary_unmeasured import _edit, _refused, _run


def _omit_first(field):
    def change(e):
        first = sorted(e[field])[0]
        return dict(e, **{field: {k: v for k, v in e[field].items() if k != first}})
    return change


def _add_unknown(field, value):
    return lambda e: dict(e, **{field: {**e[field], "zz_unknown_member": value}})


def test_accepted_step_omitting_a_score_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["accepted"], _omit_first("scores")))
    _refused(code, out, capsys)


def test_accepted_step_omitting_a_risk_component_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["accepted"], _omit_first("risk")))
    _refused(code, out, capsys)


def test_rejected_step_omitting_a_risk_component_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: not e["accepted"], _omit_first("risk")))
    _refused(code, out, capsys)


def test_unknown_risk_component_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["accepted"], _add_unknown("risk", 0.0)))
    _refused(code, out, capsys)


def test_unknown_score_member_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["accepted"], _add_unknown("scores", 1.0)))
    _refused(code, out, capsys)


def test_rejected_step_omitting_a_score_is_null(tmp_path, monkeypatch, capsys):
    picked = {}

    def change(e):
        e = _omit_first("scores")(e)
        picked["step"] = e["step"]
        return e

    scored = lambda e: not e["accepted"] and None not in e["scores"].values()  # noqa: E731 - a fully scored one
    code, out = _run(tmp_path, monkeypatch, _edit(scored, change))
    assert code == 0, capsys.readouterr().err
    s = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["measured"]["search"]
    assert s["status"] == "measured"
    assert next(p for p in s["points"] if p["step"] == picked["step"])["utility"] is None


# Rule 2 (#150 scope addition, final review pass 4 Gemini 8): a purpose score that is present is a finite,
# non-boolean number on every step, and the log has at least one candidate; otherwise `run` refuses.
#   an accepted step's score is a boolean    -> released, True averaged in as 1.0, status measured
#                                                    -> test_non_number_score_refuses[accepted-bool]
#   a rejected step's score is NaN           -> NaN utility published (or a non-search failure), not a refusal
#                                                    -> test_non_number_score_refuses[rejected-nan]
#   an accepted step's score is infinite     -> inf utility published (or a non-search failure), not a refusal
#                                                    -> test_non_number_score_refuses[accepted-inf]
#   a log with no candidate step             -> CLI: refused by justify's start-step check (already, kept by
#                                               test_log_without_candidates_refuses); search_summary itself
#                                               published candidates 0, status measured
#                                                    -> test_search_summary_without_candidates_raises (direct)
@pytest.mark.parametrize("which,value", [(True, True), (False, float("nan")), (True, float("inf"))],
                         ids=["accepted-bool", "rejected-nan", "accepted-inf"])
def test_non_number_score_refuses(tmp_path, monkeypatch, capsys, which, value):
    def change(e):
        first = sorted(k for k, v in e["scores"].items() if v is not None)[0]
        return dict(e, scores={**e["scores"], first: value})

    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["accepted"] is which, change))
    _refused(code, out, capsys)


def test_log_without_candidates_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, lambda log: [e for e in log if e["step"] == "final"])
    err = capsys.readouterr().err
    assert code == 2, err
    assert not out.exists()


def test_search_summary_without_candidates_raises():
    """Direct seam: justify refuses first in `run`, so the CLI cannot reach this guard (defence in depth)."""
    from pets_release.policy.health_s1 import POLICY
    from pets_release.run.justify import JustificationError, search_summary

    with pytest.raises(JustificationError, match="measured.search"):
        search_summary([{"step": "final", "scores": {}, "risk": {}, "accepted": True}], {}, POLICY)
