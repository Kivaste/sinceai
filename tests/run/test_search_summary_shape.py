"""`measured.search` aggregates vs the manifest identifier-shape scan (#61), through the production CLI.

Seam: `pets-release run` (no --plan), in-process; the real search runs once on the synthetic minikit and its
log's per-candidate risk figures are replaced at the boundary where `run` receives the result. Synthetic only.

Rule: `measured.search` points carry `risk` and `utility` rounded to 6 decimals (the precision of the other
manifest shares), so a measured search figure never reaches the manifest as a long digit run the
identifier-shape scan reads as an identifier. The scan itself is unchanged.

Failure rows (trigger -> wrong result before the fix):
  a candidate risk whose float repr carries a 16-digit Luhn-valid run (as on the real kit)
     -> writer refuses `identifier-shape:PAYMENT_CARD` on measured.search.points[*].risk, exit 1
                                                            -> test_long_float_risk_is_released_rounded
"""
from __future__ import annotations

import json

PLANTED = 0.4111111111111111  # its repr's digits form a Luhn-valid 16-digit card-shaped run


def test_long_float_risk_is_released_rounded(run_search_log):
    def alter(log):
        return [dict(e, risk={c: PLANTED for c in e["risk"]}) if e["step"] != "final" and e["risk"] else e
                for e in log]

    code, out = run_search_log(alter)
    assert code == 0
    pts = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["measured"]["search"]["points"]
    assert any(p["risk"] == round(PLANTED, 6) for p in pts)
    for p in pts:
        assert p["risk"] == round(p["risk"], 6)
        assert p["utility"] is None or p["utility"] == round(p["utility"], 6)  # null: unscored (#133)
