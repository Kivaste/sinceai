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

import copy
import dataclasses
import json

import pytest


def _run(tmp_path, monkeypatch, alter):
    """Run the CLI with the search log's entries passed through ``alter(entries) -> entries``."""
    from run_helpers import TEST_KEY, build_kit, grouped_qis

    from pets_release.cli import main
    from pets_release.run import pipeline

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", grouped_qis)
    real = pipeline.search

    def altered(*a, **k):
        res = copy.deepcopy(real(*a, **k))
        return dataclasses.replace(res, log=alter(res.log))

    monkeypatch.setattr(pipeline, "search", altered)
    out = tmp_path / "out" / "rel"
    code = main(["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out),
                 "--created", "2026-11-07T00:00:00Z"])
    return code, out


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


def test_empty_risk_map_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["step"] == 0, lambda e: dict(e, risk={})))
    _refused(code, out, capsys)


def test_empty_score_map_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: not e["accepted"], lambda e: dict(e, scores={})))
    _refused(code, out, capsys)


def _drop_one_score(e):
    first = sorted(e["scores"])[0]
    return dict(e, scores={**e["scores"], first: None})


def test_accepted_step_with_missing_score_refuses(tmp_path, monkeypatch, capsys):
    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: e["accepted"], _drop_one_score))
    _refused(code, out, capsys)


def _rejected_unscored(tmp_path, monkeypatch):
    """Release whose first rejected step has one unscored check; returns (exit code, out, that step)."""
    picked = {}

    def change(e):
        e = _drop_one_score(e)
        picked["step"] = e["step"]
        return e

    code, out = _run(tmp_path, monkeypatch, _edit(lambda e: not e["accepted"], change))
    return code, out, picked["step"]


def test_rejected_unscored_candidate_is_null(tmp_path, monkeypatch, capsys):
    code, out, step = _rejected_unscored(tmp_path, monkeypatch)
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


def test_dashboard_leaves_unscored_candidates_off_the_chart(tmp_path, monkeypatch, capsys):
    """Seam: `pets-release dashboard` on the released folder. An unscored candidate is not plotted (it would
    otherwise sit at utility 0); every scored candidate is."""
    import re

    from pets_release.cli import main

    code, out, _ = _rejected_unscored(tmp_path, monkeypatch)
    assert code == 0, capsys.readouterr().err
    pts = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["measured"]["search"]["points"]
    html_path = tmp_path / "dash" / "dashboard.html"
    assert main(["dashboard", str(out), "--out", str(html_path)]) == 0, capsys.readouterr().err
    html = html_path.read_text(encoding="utf-8")
    plotted = sorted(int(n) for n in re.findall(r"<title>step (\d+)</title>", html))
    assert plotted == sorted(p["step"] for p in pts if p["utility"] is not None)
    assert len(plotted) < len(pts)
    assert "None" not in html
