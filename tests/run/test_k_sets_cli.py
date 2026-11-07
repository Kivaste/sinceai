"""#146 (decision D58) at the CLI seam: per-person k on both QI sets, and every withheld catalogued QI justified.
Synthetic minikit rows only.

Rule: the manifest's ``measured.kSets`` records per-person k (persons, min, median, below-k count and share), before
local suppression and on the released tables, for (a) the scenario's suggested QIs in their released forms and (b)
every catalogued QI the release keeps; next to it, each catalogued QI the release withholds with its policy
justification. A set that cannot be computed is ``not_measured`` with a reason, never a pass. ``verify --full``
re-measures the section and fails when it differs or is not measured. A manifest without it is invalid.

Failure rows (trigger -> wrong result before #146):
  R1 plan keeps arrival_mode (catalogued, not a scenario QI), one person unique on it
       -> no kSets; want set (b) below k before suppression above set (a), both 0 on the release, verify both tiers 0
  R2 hand-plan release -> no withheld list; want sex, postcode and test_name withheld with their policy reasons
  R3 signed kSets figure changed, re-signed -> verify --full exits 0; want exit 1 naming measured.kSets
  R4 kSets removed, re-signed -> verify exits 0; want exit 1 (schema)
  R5 the scenario QI set cannot be computed -> silently omitted or a pass; want not_measured with a reason and
       verify --full exit 1
"""
from __future__ import annotations

import json

import pandas as pd
from run_helpers import TEST_KEY, build_kit, cli, coarse_qis, run_args
from test_verify_assertion_rerun import MANIFEST, copy_release, resign

KS = "kSets"


def _manifest(rel):
    return json.loads((rel / MANIFEST).read_text(encoding="utf-8"))


def _fj(m):
    return {(f["table"], f["column"]): f for f in m["fieldJustifications"]}


def _one_unique_mode(folder):
    """coarse_qis, then arrival_mode is one value for everyone except the first person's visits."""
    coarse_qis(folder)
    p = folder / "ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    first = df.at[0, "patient_hetu"]
    df["arrival_mode"] = ["police" if h == first else "walk-in" for h in df["patient_hetu"]]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def _plan_keeping_arrival_mode():
    from pets_release.policy import hand_plan

    plan = hand_plan("HEALTH-S1")
    for e in plan:
        if (e["table"], e["column"]) == ("ed_visits", "arrival_mode"):
            e["rung"], e["params"], e["reason"] = "keep", {}, "#146 test: kept catalogued QI"
    return plan


def _run_in_process(tmp_path, monkeypatch, edit, plan=None):
    from pets_release.run import cli as run_cli
    from pets_release.run import pipeline

    if plan is not None:
        monkeypatch.setattr(pipeline, "hand_plan", lambda sid: plan())
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit)
    rel = tmp_path / "out" / "rel"
    assert run_cli.main(run_args(kit, rel)[1:]) == 0
    return kit, rel


def _sets(m):
    ks = m["measured"][KS]
    assert ks["status"] == "measured", ks
    return {s["set"]: s for s in ks["sets"]}


def _qi_cols(s):
    return {(q["table"], q["column"]) for q in s["qi"]}


def test_kept_catalogued_qi_lowers_k_in_set_b_only(tmp_path, monkeypatch):
    kit, rel = _run_in_process(tmp_path, monkeypatch, _one_unique_mode, _plan_keeping_arrival_mode)
    m = _manifest(rel)
    assert ("ed_visits", "arrival_mode") in {(q["table"], q["column"]) for q in m["contract"]["qi"]}
    sets = _sets(m)
    assert set(sets) == {"scenario", "keptCatalogued"}
    a, b = sets["scenario"], sets["keptCatalogued"]
    assert a["status"] == b["status"] == "measured"
    assert ("ed_visits", "arrival_mode") in _qi_cols(b)
    assert ("ed_visits", "arrival_mode") not in _qi_cols(a)
    assert _qi_cols(a) == {("ed_visits", "age_band"), ("ed_visits", "municipality"), ("ed_visits", "arrival_ts")}
    assert m["measured"][KS]["k"] == 5
    # the kept catalogued QI pushes exactly one more person below k in set (b), none in set (a)
    assert b["beforeSuppression"]["belowK"] == a["beforeSuppression"]["belowK"] + 1
    assert b["beforeSuppression"]["belowKShare"] > a["beforeSuppression"]["belowKShare"]
    for s in (a, b):
        assert s["released"]["belowK"] == 0 and s["released"]["belowKShare"] == 0.0
        assert s["released"]["minK"] >= 5
        assert s["beforeSuppression"]["persons"] == 730
    assert ("ed_visits", "arrival_mode") not in {(w["table"], w["column"]) for w in m["measured"][KS]["withheld"]}
    assert cli("verify", str(rel)).returncode == 0
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 0, full.stdout + full.stderr


def test_withheld_catalogued_qis_carry_their_policy_justification(released, tmp_path):
    _, rel = copy_release(released, tmp_path)
    m = _manifest(rel)
    sets = _sets(m)
    assert _qi_cols(sets["scenario"]) == _qi_cols(sets["keptCatalogued"])  # the hand plan keeps only scenario QIs
    withheld = {(w["table"], w["column"]): w["reason"] for w in m["measured"][KS]["withheld"]}
    fj = _fj(m)
    for key in (("ed_visits", "sex"), ("ed_visits", "postcode"), ("ed_visits", "arrival_mode"),
                ("lab_results", "test_name"), ("lab_results", "sampled_ts"), ("published_weekly_stats", "sex")):
        assert key in withheld, key
        assert fj[key]["decision"] == "withheld"
        assert withheld[key] == fj[key]["reason"]
    kept = {(q["table"], q["derived_from"]) for q in m["contract"]["qi"]}
    assert not any(k in kept for k in withheld)


def test_full_verify_fails_on_a_changed_k_set_figure(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    m = _manifest(rel)
    for s in m["measured"][KS]["sets"]:
        if s["set"] == "keptCatalogued":
            s["beforeSuppression"]["belowK"] += 1
    (rel / MANIFEST).write_text(json.dumps(m), encoding="utf-8")
    resign(rel)
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "measured.kSets" in full.stdout, full.stdout


def test_manifest_without_k_sets_is_invalid(released, tmp_path):
    _, rel = copy_release(released, tmp_path)
    m = _manifest(rel)
    del m["measured"][KS]
    (rel / MANIFEST).write_text(json.dumps(m), encoding="utf-8")
    resign(rel)
    lim = cli("verify", str(rel))
    assert lim.returncode == 1, lim.stdout + lim.stderr


def test_a_set_that_cannot_be_computed_is_not_measured_and_fails_full_verify(tmp_path, monkeypatch):
    from pets_release.run import ksets

    monkeypatch.setattr(ksets, "SCENARIO_QI", {})
    kit, rel = _run_in_process(tmp_path, monkeypatch, coarse_qis)
    sets = _sets(_manifest(rel))
    assert sets["scenario"]["status"] == "not_measured"
    assert sets["scenario"]["reason"]
    assert sets["keptCatalogued"]["status"] == "measured"
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "measured.kSets" in full.stdout, full.stdout
