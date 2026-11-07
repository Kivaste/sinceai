"""CS-S1 measurements on the synthetic minikit, validated against 02's manifest schema.

Rows: fallback turn_id -> CS-U5 unmodified 0.0, lineage-adapted > 0, both before-scored; CS-U1/U3/U4
scored; redaction with gold -> exact, held-out, six text_recall residual risks; without gold -> not_measured.
"""
from __future__ import annotations

import pandas as pd
import pytest
from cs_kit import build_cs_kit

from pets_release.cs_s1 import measure as M
from pets_release.manifest import not_measured
from pets_release.measure import measured_errors


@pytest.fixture(scope="module")
def kit(tmp_path_factory):
    return build_cs_kit(tmp_path_factory.mktemp("cskit") / "kit")


def _prot(prepared):
    return {k: v.reset_index(drop=True) for k, v in prepared.tables.items()}


def _block(**kw):
    base = {k: not_measured("not in this test") for k in ("utility", "privacy", "search", "baselines", "redaction")}
    return dict(base, **kw)


def test_utility_reports_cs_u5_twice(prepared, minikit, kit):
    prot = _prot(prepared)
    rowmap = pd.DataFrame({"protected_row": [str(i) for i in range(len(prot["turns"]))],
                           "original_record_id": minikit["turns"].turn_id.tolist()})
    block, util = M.utility("CS-S1", minikit, prot, rowmap, root=kit)
    assert measured_errors(_block(utility=block)) == []
    assert {"CS-U1", "CS-U3", "CS-U4", "CS-U5", M.ADAPTED} <= set(util)
    assert util["CS-U5"]["after"] == 0.0  # unmodified kit score: turn_id no longer matches
    assert util[M.ADAPTED]["after"] > 0.5 and util[M.ADAPTED]["before"] == util["CS-U5"]["before"]
    for t in ("CS-U1", "CS-U3", "CS-U4"):
        assert util[t]["status"] == "ok" and util[t]["before"] is not None and util[t]["after"] is not None


def test_utility_without_rowmap_has_no_adapted_entry(kept, kit):
    _, util = M.utility("CS-S1", kept.gate_context["source"], _prot(kept), None, root=kit)
    assert M.ADAPTED not in util and util["CS-U5"]["after"] > 0.5


def test_redaction_measured_on_held_out_with_residual_risks(prepared, kit):
    red = M.redaction(kit, prepared.spans)
    assert measured_errors(_block(redaction=red["measured"])) == []
    assert red["measured"]["mode"] == "exact" and red["held"]
    risks = {r["label"]: r for r in red["risks"]}
    assert set(risks) == set(M.RESIDUAL_LABELS)
    person = risks["PERSON"]["rate"]
    assert person["status"] == "measured" and 0 <= person["value"] <= 1
    assert person["denominator"] == {"unit": "turns", "n": len(red["held"])}


def test_redaction_not_measured_without_gold(prepared, tmp_path):
    red = M.redaction(build_cs_kit(tmp_path / "kit", gold=False), prepared.spans)
    assert red["measured"]["status"] == "not_measured"
    assert all(r["rate"]["status"] == "not_measured" for r in red["risks"])
