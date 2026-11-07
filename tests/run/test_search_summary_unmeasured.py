"""`measured.search` never publishes a stand-in figure as measured (#133), through the production CLI.

Seam: `pets-release run` (no --plan), in-process; the real search runs on the synthetic minikit and one log entry
is altered at the boundary where `run` receives the search result (as in test_search_summary_shape). Synthetic only.

Rule: a non-final search-log entry whose risk or purpose scores are unknown is never written as a measured 0.0.
An empty risk map, an empty score map, or an accepted step with a missing score makes `run` refuse fail-closed
(exit 2, no release folder). A rejected candidate whose check was not scored (not answerable / error, as the
search logs it) is published with `utility: null` (unknown), never 0.0.

Failure rows (trigger -> wrong result before the fix):
  a step with an empty risk map           -> released, point risk 0.0 (perfect privacy), status measured
                                                                  -> test_empty_risk_map_refuses
  a step with an empty score map          -> released, point utility 0.0, status measured
                                                                  -> test_empty_score_map_refuses
  an accepted step with a missing score   -> released, the missing score counted as 0.0
                                                                  -> test_accepted_step_with_missing_score_refuses
  a rejected step with a missing score    -> released, point utility 0.0 (a stand-in), status measured
                                                                  -> test_rejected_unscored_candidate_is_null
"""
from __future__ import annotations

import json

import pytest


def _edit(pick, change):
    """Apply ``change`` to the first non-final entry matching ``pick``; fail the test if none matches."""
    def alter(log):
        out, done = [], False
        for e in log:
            if not done and e["step"] != "final" and pick(e):
                e, done = change(dict(e)), True
            out.append(e)
        assert done, "no search-log entry matched the alteration"
        return out
    return alter


def _refused(code, out, capsys):
    err = capsys.readouterr().err
    assert code == 2, err
    assert "measured.search" in err
    assert not out.exists()


def test_empty_risk_map_refuses(run_search_log, capsys):
    code, out = run_search_log(_edit(lambda e: e["step"] == 0, lambda e: dict(e, risk={})))
    _refused(code, out, capsys)


@pytest.mark.parametrize("risk", [None, False, True, "private-risk-marker", float("nan"), float("inf"), -float("inf")],
                         ids=["none", "false", "true", "string", "nan", "inf", "negative-inf"])
def test_unmeasured_risk_component_refuses(run_search_log, capsys, risk):
    """Seam: CLI run. Unknown/non-finite risk -> refusal, never a measured release or value-bearing reason."""
    code, out = run_search_log(_edit(lambda e: e["step"] == 0, lambda e: dict(e, risk={"component": risk})))
    captured = capsys.readouterr()
    assert code == 2, captured.err
    assert captured.err == "pets-release run: measured.search: a search step has no measured risk\n"
    assert not out.exists()


def test_empty_score_map_refuses(run_search_log, capsys):
    code, out = run_search_log(_edit(lambda e: not e["accepted"], lambda e: dict(e, scores={})))
    _refused(code, out, capsys)


@pytest.mark.parametrize("score,missing", [(False, False), (True, False), ("private-score-marker", False),
                                         ("0.5", False), (float("nan"), False), (float("inf"), False),
                                         (-float("inf"), False), (False, True)],
                         ids=["false", "true", "string", "numeric-string", "nan", "inf", "negative-inf", "mixed-missing"])
def test_rejected_non_numeric_score_refuses(run_search_log, capsys, score, missing):
    """Seam: CLI run. Rejected candidates must validate present scores, including alongside unknown scores."""
    scores = {"check": score}
    if missing:
        scores["unscored"] = None
    code, out = run_search_log(_edit(lambda e: not e["accepted"], lambda e: dict(e, scores=scores)))
    captured = capsys.readouterr()
    assert code == 2, captured.err
    assert captured.err == "pets-release run: measured.search: a search step has a non-numeric purpose score\n"
    assert not out.exists()


def _drop_one_score(e):
    first = sorted(e["scores"])[0]
    return dict(e, scores={**e["scores"], first: None})


def test_accepted_step_with_missing_score_refuses(run_search_log, capsys):
    code, out = run_search_log(_edit(lambda e: e["accepted"], _drop_one_score))
    _refused(code, out, capsys)


def _rejected_unscored(run_search_log):
    """Release whose first rejected step has one unscored check; returns (exit code, out, that step)."""
    picked = {}

    def change(e):
        e = _drop_one_score(e)
        picked["step"] = e["step"]
        return e

    code, out = run_search_log(_edit(lambda e: not e["accepted"], change))
    return code, out, picked["step"]


def test_rejected_unscored_candidate_is_null(run_search_log, capsys):
    code, out, step = _rejected_unscored(run_search_log)
    assert code == 0, capsys.readouterr().err
    s = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["measured"]["search"]
    assert s["status"] == "measured"
    assert next(p for p in s["points"] if p["step"] == step)["utility"] is None
    log_path = out.parent / (out.name + ".scoring") / "search_log.jsonl"
    log = [json.loads(x) for x in log_path.read_text(encoding="utf-8").splitlines() if x]
    unscored = {e["step"] for e in log if e["step"] != "final" and None in e["scores"].values()}
    assert step in unscored
    assert {p["step"] for p in s["points"] if p["utility"] is None} == unscored
    assert all(isinstance(p["utility"], float) for p in s["points"] if p["step"] not in unscored)


def test_dashboard_leaves_unscored_candidates_off_the_chart(tmp_path, run_search_log, capsys):
    """Seam: `pets-release dashboard` on the released folder. An unscored candidate is not plotted (it would
    otherwise sit at utility 0); every scored candidate is."""
    import re

    from pets_release.cli import main

    code, out, _ = _rejected_unscored(run_search_log)
    assert code == 0, capsys.readouterr().err
    pts = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["measured"]["search"]["points"]
    html_path = tmp_path / "dash" / "dashboard.html"
    assert main(["dashboard", str(out), "--out", str(html_path)]) == 0, capsys.readouterr().err
    html = html_path.read_text(encoding="utf-8")
    plotted = sorted(int(n) for n in re.findall(r"<title>step (\d+)</title>", html))
    assert plotted == sorted(p["step"] for p in pts if p["utility"] is not None)
    assert len(plotted) < len(pts)
    assert "None" not in html
