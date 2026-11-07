"""`pets-release run` without `--plan`: the search chooses the plan (ticket 25), through the real CLI.

Rule: with no `--plan`, `run` releases the search's plan; every field justification comes from a search-log
step, `measured.search` summarises the log, and the log goes to `<out>.scoring/search_log.jsonl`.

Rows (trigger -> result):
  run without --plan (k reachable)              -> exit 0; gate all pass; verify limited and --full pass
  same release                                  -> every fieldJustification has source "search" and cites a
                                                   step that exists in search_log.jsonl and moved or kept it
  same release                                  -> measured.search measured; candidates == non-final log
                                                   entries; one point per non-final entry; accepted counts match
  same release                                  -> the plan is the search's (the logged moves), not the hand plan
  run --plan bogus                              -> exit 2, no output folders
  run --scenario CS-S1 (with or without --plan)  -> exit 2, message names ticket 23 and follow-up #96, no folders
  search finds no acceptable plan                -> exit 1, no release folder; refusal report + search log
  two runs without --plan                        -> byte-identical release folders and search logs
"""
from __future__ import annotations

import hashlib
import json
import re

import pandas as pd
import pytest
from run_helpers import CREATED, build_kit, cli, grouped_qis

STEP = re.compile(r"search step (\d+|final)\b")
def search_args(kit, out, *extra):
    return ["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED, *extra]


@pytest.fixture(scope="module")
def searched(tmp_path_factory):
    base = tmp_path_factory.mktemp("search")
    kit = build_kit(base / "kit", grouped_qis)
    out = base / "out" / "rel"
    proc = cli(*search_args(kit, out))
    return kit, out, proc


def _manifest(out):
    return json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))


def _log(out):
    p = out.parent / (out.name + ".scoring") / "search_log.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


def test_search_release_passes_gate_and_both_verify_tiers(searched):
    kit, out, proc = searched
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RELEASED" in proc.stdout
    gate = json.loads((out.parent / "rel.scoring" / "gate_report.json").read_text(encoding="utf-8"))
    assert gate["refused"] is False
    assert {r["status"] for r in gate["records"]} <= {"pass", "not_applicable"}
    lim = cli("verify", str(out))
    assert lim.returncode == 0, lim.stdout + lim.stderr
    assert lim.stdout.strip().startswith("VERIFIED (limited):")
    full = cli("verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 0, full.stdout + full.stderr
    assert "VERIFIED (full)" in full.stdout


def test_every_justification_traces_to_a_log_step(searched):
    _, out, proc = searched
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m, log = _manifest(out), _log(out)
    by_step = {str(e["step"]): e for e in log}
    fj = m["fieldJustifications"]
    assert len(fj) == len({(f["table"], f["column"]) for f in fj}) >= 30  # every source column, once
    for f in fj:
        assert f["source"] == "search"
        steps = STEP.findall(f["reason"])
        assert steps, f"{f['table']}.{f['column']}: no log step cited"
        for s in steps:
            assert s in by_step, f"{f['table']}.{f['column']}: cites missing step {s}"
        cited = by_step[steps[0]]
        moved = {(mv["table"], mv["column"]): mv["rung"] for mv in cited["moves"]}
        key = (f["table"], f["column"])
        if cited["accepted"] and key in moved:
            assert moved[key] == f["rung"]  # the adopting step set exactly the released rung
        elif steps[0] != "0":
            assert not cited["accepted"] and key in moved  # a rejected try of this field keeps it where it is
        # step 0 (start, at the floor) is valid only when the field sits at its floor
        if steps[0] == "0" and not (cited["accepted"] and key in moved):
            assert f["rung"] == f["floor"]


def test_measured_search_summarises_the_log(searched):
    _, out, proc = searched
    assert proc.returncode == 0
    s = _manifest(out)["measured"]["search"]
    log = [e for e in _log(out) if e["step"] != "final"]
    assert s["status"] == "measured"
    assert s["candidates"] == len(log) and len(s["points"]) == len(log)
    assert s["accepted"] == sum(1 for e in log if e["accepted"]) >= 1
    assert [p["step"] for p in s["points"]] == [e["step"] for e in log]
    for p, e in zip(s["points"], log):
        assert p["accepted"] == e["accepted"]
        assert p["risk"] == round(max(e["risk"].values()), 6)  # 6 dp: test_search_summary_shape
    assert isinstance(s["boundReached"], bool)
    final = [e for e in _log(out) if e["step"] == "final"]
    assert len(final) == 1 and final[0]["accepted"] and "(privacy pass)" in final[0]["reason"]


def test_released_plan_is_the_logged_search_plan(searched):
    _, out, proc = searched
    assert proc.returncode == 0
    fj = {(f["table"], f["column"]): f for f in _manifest(out)["fieldJustifications"]}
    state = {}
    for e in _log(out):
        if e["accepted"] and e["step"] != "final":
            for mv in e["moves"]:
                state[(mv["table"], mv["column"])] = mv["rung"]
    for key, rung in state.items():
        assert fj[key]["rung"] == rung
    released = {f["outputColumn"] for f in fj.values() if f["table"] == "ed_visits" and f["decision"] == "released"}
    cols = set(pd.read_csv(out / "ed_visits.csv", dtype=str, nrows=0).columns)
    assert cols == released


def test_unknown_plan_is_a_usage_error(tmp_path):
    kit = build_kit(tmp_path / "kit", grouped_qis)
    out = tmp_path / "out" / "rel"
    proc = cli(*search_args(kit, out, "--plan", "bogus"))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert not out.exists() and not (tmp_path / "out" / "rel.scoring").exists()


@pytest.mark.parametrize("extra", [(), ("--plan", "hand")])
def test_cs_s1_refuses_cleanly_naming_the_follow_up(tmp_path, extra):
    """CS-S1 (release: ticket 23; search: follow-up #96) is not wired in this build: fail closed, say why."""
    kit = build_kit(tmp_path / "kit", grouped_qis)
    out = tmp_path / "out" / "rel"
    args = ["run", "--scenario", "CS-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED, *extra]
    proc = cli(*args)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "CS-S1" in proc.stderr and "#96" in proc.stderr and "ticket 23" in proc.stderr
    assert "RELEASED" not in proc.stdout
    assert not out.exists() and not (tmp_path / "out" / "rel.scoring").exists()


def test_search_refusal_writes_report_and_log_no_release(tmp_path):
    def drop_crp(folder):  # no lab test the H-U7 check reads: no candidate can pass, the start is rejected
        grouped_qis(folder)
        p = folder / "lab_results.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df["test_code"] = "ZZZ"
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    kit = build_kit(tmp_path / "kit", drop_crp)
    out = tmp_path / "out" / "rel"
    proc = cli(*search_args(kit, out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    sc = tmp_path / "out" / "rel.scoring"
    rep = json.loads((sc / "refusal_report.json").read_text(encoding="utf-8"))
    assert rep["reasons"] == ["search:no-acceptable-plan"]
    assert len(_log(out)) >= 1


def test_two_search_runs_byte_identical(tmp_path, searched):
    kit, out, proc = searched
    assert proc.returncode == 0
    out2 = tmp_path / "rel2"
    proc2 = cli(*search_args(kit, out2))
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr

    def dig(folder):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}

    assert dig(out) == dig(out2)
    assert (out.parent / "rel.scoring" / "search_log.jsonl").read_bytes() == \
        (tmp_path / "rel2.scoring" / "search_log.jsonl").read_bytes()
