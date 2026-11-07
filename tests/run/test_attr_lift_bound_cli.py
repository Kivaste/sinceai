"""D64 (#157): the attribute-inference lift bound, through the real CLI (`pets-release run`, search) on the minikit.

Rule: a released plan holds every bounded attribute (HEALTH-S1: icd10_primary, los_minutes) at or under the
policy's max_lift (#139's estimator, ``minimiser.attr_lift``); a plan over it is refused, never relaxed, and the
purpose floors stay enforced. Rows, trigger -> result:
  minikit (grouped QIs, its own diagnoses and stays): small classes, lift over the bound at the coarsest rungs the purpose
      floors allow (icd10 chapter fails H-U4, wider stay bins fail H-U2)  -> exit 1, refused, the search log's
      final step names the attributes over the bound; nothing published
  minikit, diagnosis and stay carry no information beyond the base rate  -> exit 0, released; the manifest
      states the bound (residual note) and the final step logs the measured lift
  same, a move that would push a plan under the bound over it (measurement stubbed)  -> the move is rejected
      with reason "attribute lift above bound", the run still releases
Deleting the final bound check makes the first row release (exit 0); deleting the candidate check adopts the move
of the third row: each test fails.
"""
from __future__ import annotations

import json

from run_helpers import CREATED, MINIKIT, build_kit, cli, grouped_qis

from pets_release.policy.health_s1 import MAX_LIFT

ARGS = ("--scenario", "HEALTH-S1", "--created", CREATED)


def _run(kit, out):
    return cli("run", "--kit", str(kit), "--out", str(out), *ARGS)


def _log(out):
    sc = out.parent / (out.name + ".scoring") / "search_log.jsonl"
    return [json.loads(x) for x in sc.read_text(encoding="utf-8").splitlines() if x]


def flat_sensitive(folder):
    """grouped_qis, then one diagnosis and one stay for every visit: knowing the QIs gives no lift."""
    import pandas as pd

    grouped_qis(folder)
    p = folder / "ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    df["icd10_primary"] = df.at[0, "icd10_primary"]
    df["los_minutes"] = "120"
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def own_sensitive(folder):
    """grouped_qis, then every visit gets back the minikit's own diagnosis and stay: on its small QI classes the
    most common value of a class is often the visit's own, a lift above the bound."""
    import pandas as pd

    grouped_qis(folder)
    p = folder / "ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    own = pd.read_csv(MINIKIT / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    for c in ("icd10_primary", "los_minutes"):
        df[c] = own[c]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def test_lift_over_the_bound_refuses(tmp_path):
    kit = build_kit(tmp_path / "kit", edit=own_sensitive)
    out = tmp_path / "rel"
    p = _run(kit, out)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "REFUSED" in p.stdout
    assert not out.exists()
    log = _log(out)
    final = [e for e in log if e["step"] == "final"]
    assert len(final) == 1 and final[0]["accepted"] is False
    reason = final[0]["reason"]
    assert "attribute lift above bound: ed_visits.icd10_primary" in reason
    assert "attribute lift above bound: ed_visits.los_minutes" in reason
    # the purpose floors held: the coarser rungs that would lower the lift were rejected on purpose, not relaxed
    rejected = {e["reason"] for e in log if e["step"] != "final" and not e["accepted"]}
    assert any(r.startswith("coarsen ed_visits.icd10_primary to icd.chapter: rejected (H-U4") for r in rejected)
    assert any(r.startswith("coarsen ed_visits.los_minutes to num.bin: rejected (H-U2") for r in rejected)
    report = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    assert report["reasons"] == ["search:no-acceptable-plan"]


def test_a_move_over_the_bound_is_never_adopted(tmp_path, monkeypatch):
    """In-search feasibility (production run_release, search): a coarsening move whose lift goes over the bound
    from a plan under it is rejected even though every purpose check passes. The measurement is stubbed only to
    put 3-character diagnoses over the bound (the flat kit's one diagnosis has a 4th character, so the floor plan
    is under it); deleting the candidate check adopts the move and the final check refuses."""
    from run_helpers import TEST_KEY, run_args

    from pets_release.cli import resolve_run_context
    from pets_release.minimiser import attr_lift
    from pets_release.run.pipeline import run_release
    from pets_release.verify import current_tool_revision

    real = attr_lift.measure

    def chars3_over(df, qcols, column):
        m = real(df, qcols, column)
        if column == "icd10_primary" and not df[column].astype(str).str.contains(".", regex=False).any():
            return {**m, "lift": MAX_LIFT * 2}
        return m

    monkeypatch.setattr(attr_lift, "measure", chars3_over)
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=flat_sensitive)
    out = tmp_path / "rel"
    ctx = resolve_run_context(run_args(kit, out)[1:])
    res = run_release(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key, out=out,
                      plan_name=None, tool_revision=current_tool_revision())
    assert res.status == "released"
    reasons = [e["reason"] for e in _log(out)]
    assert ("coarsen ed_visits.icd10_primary to icd.3: rejected (attribute lift above bound: "
            "ed_visits.icd10_primary)" in reasons), " | ".join(r[:120] for r in reasons if "icd10_primary" in r)


def test_lift_under_the_bound_releases_and_states_the_bound(tmp_path):
    kit = build_kit(tmp_path / "kit", edit=flat_sensitive)
    out = tmp_path / "rel"
    p = _run(kit, out)
    assert p.returncode == 0, p.stdout + p.stderr
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    note = next(r for r in m["residualRisks"] if r["risk"] == "attribute-lift-bound")
    assert f"at most {MAX_LIFT} for icd10_primary and los_minutes" in note["description"]
    assert "refused" in note["description"]
    final = [e for e in _log(out) if e["step"] == "final"][0]
    assert final["accepted"] is True
    assert (f"attribute lift (bound {MAX_LIFT}): ed_visits.icd10_primary 1.000, ed_visits.los_minutes 1.000"
            in final["reason"])
