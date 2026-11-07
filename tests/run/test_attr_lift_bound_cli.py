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

import pytest

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


REJECT = ("coarsen ed_visits.icd10_primary to icd.3: rejected (attribute lift over the bound, raised or "
          "unmeasured: ed_visits.icd10_primary)")
ADOPT = "coarsen ed_visits.icd10_primary to icd.3: adopted"


@pytest.mark.parametrize("full, chars3, expect, released", [
    (1.0, MAX_LIFT * 2, REJECT, True),     # under -> over: rejected
    (MAX_LIFT * 2, MAX_LIFT * 3, REJECT, False),  # already over -> higher: rejected
    (MAX_LIFT * 2, None, REJECT, False),   # already over -> unmeasured: rejected
    (MAX_LIFT * 3, MAX_LIFT * 2, ADOPT, False),   # already over -> lower: allowed (the final check still refuses)
])
def test_adoption_respects_the_lift_bound(tmp_path, monkeypatch, full, chars3, expect, released):
    """In-search feasibility (production run_release, search; every adoption path calls ``lift_regress``): the
    measurement is stubbed only for the diagnosis, by rung (the flat kit's one diagnosis has a 4th character, so
    3-character cells mean icd.3). ``full=1.0`` keeps the real measure at the floor. Deleting a clause of the rule
    flips its row."""
    from run_helpers import TEST_KEY, run_args

    from pets_release.cli import resolve_run_context
    from pets_release.minimiser import attr_lift
    from pets_release.run.pipeline import RunRefused, run_release
    from pets_release.verify import current_tool_revision

    real = attr_lift.measure

    def stub(df, qcols, column):
        m = real(df, qcols, column)
        if column != "icd10_primary":
            return m
        is3 = not df[column].astype(str).str.contains(".", regex=False).any()
        if is3:
            return {**m, "lift": chars3}
        return m if full == 1.0 else {**m, "lift": full}

    monkeypatch.setattr(attr_lift, "measure", stub)
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=flat_sensitive)
    out = tmp_path / "rel"
    ctx = resolve_run_context(run_args(kit, out)[1:])
    kw = dict(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key, out=out, plan_name=None,
              tool_revision=current_tool_revision())
    if released:
        assert run_release(**kw).status == "released"
    else:
        with pytest.raises(RunRefused):
            run_release(**kw)
    reasons = [e["reason"] for e in _log(out)]
    assert expect in reasons, " | ".join(r[:140] for r in reasons if "icd10_primary" in r)


def test_lift_regress_rule_rows():
    """The shared helper itself, on the production method (current -> candidate lift, bound MAX_LIFT)."""
    from types import SimpleNamespace

    from pets_release.minimiser.search import _Search

    s = SimpleNamespace(p=SimpleNamespace(attribute_lift={"max_lift": MAX_LIFT}))

    def rule(cur, cand):
        ev = {"lift": {"t.c": {"lift": cand}}}
        cev = {"lift": {} if cur == "absent" else {"t.c": {"lift": cur}}}
        return _Search.lift_regress(s, ev, cev)

    assert rule(1.0, MAX_LIFT) == [] and rule(1.0, MAX_LIFT + 0.01) == ["t.c"]
    assert rule(3.0, 4.0) == ["t.c"] and rule(3.0, None) == ["t.c"]
    assert rule(3.0, 3.0) == [] and rule(3.0, 2.5) == []
    assert rule("absent", 3.0) == ["t.c"] and rule("absent", 1.0) == []
    assert rule(None, 3.0) == [] and rule(None, None) == ["t.c"]


def test_lift_under_the_bound_releases_and_states_the_bound(tmp_path):
    kit = build_kit(tmp_path / "kit", edit=flat_sensitive)
    out = tmp_path / "rel"
    p = _run(kit, out)
    assert p.returncode == 0, p.stdout + p.stderr
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    note = next(r for r in m["residualRisks"] if r["risk"] == "attribute-lift-bound")
    d = note["description"]
    assert f"at most {MAX_LIFT} for icd10_primary, los_minutes" in d and "refused" in d
    assert "population estimator" in d and "not #139's sampled attacker" in d
    assert "icd10 lift disclosed, not reduced: chapter coding fails H-U4" in d
    assert f"2.0 refused the real kit; {MAX_LIFT}, just above the irreducible icd10 lift, awaits a human" in d
    assert d.endswith(" Enforced lift: icd10_primary 1.0000, los_minutes 1.0000.")
    # the stay-bin coarsening is recorded in the note, not as a sacrifice entry: a sacrifice entry would waive H-U2
    # below 0.9 (tests/run/test_purpose_rule.py), relaxing a purpose floor
    assert "los: 30-min bins, H-U2 0.967 -> 0.920 (kit)" in d
    assert "H-U2" not in {s["check"] for s in m["sacrifices"]}
    final = [e for e in _log(out) if e["step"] == "final"][0]
    assert final["accepted"] is True
    assert (f"attribute lift (bound {MAX_LIFT}): ed_visits.icd10_primary 1.000, ed_visits.los_minutes 1.000"
            in final["reason"])
