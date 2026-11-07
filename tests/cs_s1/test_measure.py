"""CS-S1 measurements on the synthetic minikit, validated against 02's manifest schema.

Rows: redaction with gold -> exact, held-out, six text_recall residual risks; without gold -> not_measured.
(Purpose checks: test_purpose_lineage.py.)
"""
from __future__ import annotations

import pytest
from cs_kit import build_cs_kit

from pets_release.cs_s1 import measure as M
from pets_release.manifest import not_measured
from pets_release.measure import measured_errors


@pytest.fixture(scope="module")
def kit(tmp_path_factory):
    return build_cs_kit(tmp_path_factory.mktemp("cskit") / "kit")


def _block(**kw):
    base = {k: not_measured("not in this test") for k in ("utility", "privacy", "search", "baselines", "redaction")}
    return dict(base, **kw)


def test_redaction_measured_on_held_out_with_residual_risks(prepared, kit):
    red = M.redaction(kit, prepared.spans)
    assert measured_errors(_block(redaction=red["measured"])) == []
    assert red["measured"]["mode"] == "exact" and red["held"]
    risks = {r["label"]: r for r in red["risks"] if r["kind"] == "text_recall"}
    assert set(risks) == set(M.RESIDUAL_LABELS)
    # plus one per-label recall note per CS-S1 target label and SECRET precision (Sol r1 Spec)
    notes = {r["risk"] for r in red["risks"] if r["kind"] == "note"}
    assert notes == {"target-recall-iban", "target-recall-national-id", "target-recall-payment-card",
                     "target-recall-secret", "target-precision-secret"}
    person = risks["PERSON"]["rate"]
    assert person["status"] == "measured" and 0 <= person["value"] <= 1
    assert person["denominator"] == {"unit": "turns", "n": len(red["held"])}


def test_redaction_not_measured_without_gold(prepared, tmp_path):
    red = M.redaction(build_cs_kit(tmp_path / "kit", gold=False), prepared.spans)
    assert red["measured"]["status"] == "not_measured"
    assert all(r["rate"]["status"] == "not_measured" for r in red["risks"])
