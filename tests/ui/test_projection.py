"""Projection seam: aggregate proof built from a verified manifest, for states no verified
synthetic release can reach (a failed text.health is refused by the gate; the HEALTH mini-kit
contract always declares text-form columns, so no record there is not_applicable).

Inputs are hand-made synthetic manifest fragments: no rows, no values.
"""
from __future__ import annotations

from pets_release.ui.jobs import gate_summary
from pets_release.ui.targets import target_rows
from pets_release.ui.views import demonstration_page, result_page


def record(check, status, hits=0):
    return {"check": check, "status": status, "hits": hits, "scope": "release", "version": "1.0.0",
            "denominator": {"n": 0 if status == "not_applicable" else 10, "unit": "turns"}}


CHECKS = [record("a", "pass"), record("b", "pass"), record("text.health", "not_applicable")]


def test_gate_summary_counts_only_pass():
    """Rule: not_applicable is its own number; error, not_run and fail never count as pass."""
    assert gate_summary(CHECKS) == {"passed": 2, "notApplicable": 1, "total": 3}
    assert gate_summary([record("a", "pass"), record("b", "error"), record("c", "not_run"),
                         record("d", "fail", 2)]) == {"passed": 1, "notApplicable": 0, "total": 4}


def test_views_never_label_not_applicable_as_passed():
    """Rule: the result card and the jury page print pass/total and not applicable separately."""
    state = {"status": "RELEASED", "scenario": "HEALTH-S1", "steps": [{"name": "run", "exit": 0},
             {"name": "verify (limited)", "exit": 0}, {"name": "verify --full", "exit": 0}],
             "gate": gate_summary(CHECKS), "exportAssertions": {}, "assertionEvidence": {},
             "verification": {"at": "2026-11-07 (run 1 of this server session)", "revision": "abcdef123456"},
             "measured": {"utility": {"status": "not_measured", "reason": "synthetic"}}, "sacrifices": [],
             "residualRisks": [], "personK": None, "targets": []}
    page = result_page(state)
    assert "2/3" in page and "1 not applicable" in page and "3/3" not in page
    limitations = demonstration_page(state, "limitations")
    assert "Gate 2/3 passed" in limitations and "1 not applicable" in limitations
    assert "3/3" not in limitations


def test_proof_cards_render_only_for_a_released_status():
    """Rule: any non-RELEASED state shows no gate, assertion or target proof, even if fields linger."""
    for status in ("RUNNING", "FAILED", "REFUSED"):
        state = {"status": status, "scenario": "HEALTH-S1", "steps": [], "gate": gate_summary(CHECKS),
                 "exportAssertions": {"emails": False}, "assertionEvidence": {}, "measured": {},
                 "sacrifices": [], "residualRisks": [], "personK": None,
                 "targets": [{"name": "x", "threshold": ">= 1", "measured": 1, "status": "met"}]}
        page = result_page(state)
        assert "Export assertions" not in page and "2/3" not in page and ">met<" not in page, status
        for item in ("measurements", "limitations"):
            demo = demonstration_page(state, item)
            assert "Gate 2/3" not in demo and ">met<" not in demo, (status, item)


def test_failed_text_health_shows_its_hits_and_not_met():
    """Rule: a failed text.health is measured (its hit count) and not met; not_applicable is not met."""
    def health(manifest):
        return next(r for r in target_rows("CS-S1", manifest) if r["name"] == "no-health-in-text")

    failed = health({"gate": {"checks": [record("text.health", "fail", 3)]}})
    assert failed["measured"] == 3 and failed["status"] == "not met"
    clean = health({"gate": {"checks": [record("text.health", "pass", 0)]}})
    assert clean["measured"] == 0 and clean["status"] == "met"
    inapplicable = health({"gate": {"checks": [record("text.health", "not_applicable")]}})
    assert inapplicable["measured"] is None and inapplicable["status"] == "not applicable"
    assert health({"gate": {"checks": [record("text.health", "error")]}})["status"] == "not measured"


def test_sacrifice_floor_without_an_adopted_sacrifice_is_not_met_or_accepted():
    """Rule: a floor is an accepted sacrifice only if the manifest records that sacrifice."""
    manifest = {"measured": {"utility": {"tasks": [{"task": "H-U4", "status": "ok", "after": 0.7}]}},
                "sacrifices": []}
    row = next(r for r in target_rows("HEALTH-S1", manifest) if r["name"] == "H-U4 sacrifice floor")
    assert row["status"] == "not adopted"
    manifest["sacrifices"] = [{"check": "H-U4", "floor": 0.6, "after": 0.7, "before": 1.0, "reason": "r"}]
    row = next(r for r in target_rows("HEALTH-S1", manifest) if r["name"] == "H-U4 sacrifice floor")
    assert row["status"] == "accepted sacrifice" and row["measured"] == 0.7
    manifest["sacrifices"][0]["after"] = 0.5
    manifest["measured"]["utility"]["tasks"][0]["after"] = 0.5
    row = next(r for r in target_rows("HEALTH-S1", manifest) if r["name"] == "H-U4 sacrifice floor")
    assert row["status"] == "not met"


def test_scorecard_utility_and_composite_never_read_from_privacy_components():
    """Rule: aggregate utility/composite are not in the manifest's privacy block; never shown from there."""
    measured = {"privacy": {"status": "measured", "components": [
        {"component": "privacy", "before": 0.25, "after": 0.75},
        {"component": "utility", "before": 0.123456, "after": 0.654321},
        {"component": "composite", "before": 0.111111, "after": 0.222222}]}}
    state = {"status": "RELEASED", "scenario": "HEALTH-S1", "steps": [], "measured": measured}
    page = demonstration_page(state, "measurements")
    assert "0.75" in page
    scorecard = page.split("pets-eval scorecard", 1)[1].split("</table>", 1)[0]
    assert "0.654321" not in scorecard and "0.222222" not in scorecard
    assert "not in the signed manifest" in scorecard
