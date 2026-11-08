"""D64 (#157): the producer-side lift estimator equals #139's red-team attribute inference on a synthetic release.

Rule: ``minimiser.attr_lift.measure`` (the release tool's own implementation; it never imports the attacker) gives the
same targets, inference rate and base rate as ``pets_attacker.redteam.attribute_inference`` when the red team's best
rows are exactly the target's QI class: every QI released, no blank cell, mid-band ages (the +-1 year age tolerance
crosses no band edge) and no field shared by 95% or more of the rows. Synthetic rows only. Rows:
  synthetic release, QIs age band + municipality + month/hour   -> equal rates for both bounded attributes, lift > 1
  attacker knows no QI                                          -> inference rate == base rate, lift 1.0
  no target with a value                                        -> lift None (the search counts it as over the bound)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pets_release.minimiser import attr_lift as AL

QCOLS = ["age_band", "municipality", "arrival_ts"]
SENS = ("icd10_primary", "los_minutes")


def _synthetic(n=400):
    rng = np.random.default_rng(7)
    orig, prot = [], []
    for i in range(n):
        decade = int(rng.integers(2, 6))  # ages 25.5 .. 55.5: mid-band
        month, hour = int(rng.integers(1, 4)), int(rng.integers(8, 11))
        when = pd.Timestamp(f"2025-{month:02d}-10 {hour:02d}:20:00")
        birth = when - pd.Timedelta(days=int((decade * 10 + 5.5) * 365.25))
        muni = ("Alpha", "Beta", "Gamma")[int(rng.integers(0, 3))]
        icd = f"{'ABCD'[decade - 2]}{int(rng.integers(0, 3)):02d}" if rng.random() < 0.6 else f"Z{int(rng.integers(0, 9)):02d}"
        los = f"[{int(rng.integers(1, 8)) * 30},{int(rng.integers(1, 8)) * 30 + 30})"
        vid = f"v{i:04d}"
        orig.append({"visit_id": vid, "date_of_birth": birth.strftime("%Y-%m-%d"), "arrival_ts": str(when),
                     "municipality": muni, "sex": "", "postcode": ""})
        prot.append({"visit_id": f"t{i:04d}", "age_band": f"{decade * 10}-{decade * 10 + 9}", "municipality": muni,
                     "arrival_ts": f"2025-{month:02d}-01T{hour:02d}:00", "icd10_primary": icd, "los_minutes": los})
    return pd.DataFrame(orig, dtype=str), pd.DataFrame(prot, dtype=str)


def _attacker(tmp_path, orig, prot):
    from pets_attacker.personas import _World
    from pets_attacker.redteam import attribute_inference

    (tmp_path / "metadata").mkdir()
    pd.DataFrame([{"dataset": "health", "table": "ed_visits", "column": c, "privacy_role": "sensitive_attribute"}
                  for c in SENS], dtype=str).to_csv(tmp_path / "metadata" / "field_catalog.csv", index=False)
    rowmap = pd.DataFrame({"protected_row": [str(i) for i in range(len(prot))],
                           "original_record_id": orig["visit_id"]}, dtype=str)
    identity = pd.DataFrame({"record": orig["visit_id"], "person": [f"p{i}" for i in range(len(orig))]}, dtype=str)
    world = _World(prot, rowmap, identity, orig, "visit_id", None)
    rungs = {"ed_visits": {"age_band": "age.band10", "municipality": "geo.topn", "arrival_ts": "ts.month_hour",
                           "visit_id": "id.pseudonym", "icd10_primary": "icd.3", "los_minutes": "num.bin"}}
    return attribute_inference(tmp_path, "health", "ed_visits", world, prot, orig, "visit_id", rungs)


def test_producer_estimator_equals_the_red_team(tmp_path):
    orig, prot = _synthetic()
    red = _attacker(tmp_path, orig, prot)
    assert red["evaluated"] is True
    for c in SENS:
        r, ours = red["columns"][c], AL.measure(prot, QCOLS, c)
        assert r["evaluated"] is True
        assert ours["n_targets"] == r["n_targets"]
        assert round(ours["inference_rate"], 4) == r["inference_rate"]
        assert round(ours["baseline_rate"], 4) == r["baseline_rate"]
    assert AL.measure(prot, QCOLS, "icd10_primary")["lift"] > 1.0


def test_population_measure_is_independent_of_row_order():
    """More rows than the red team's 3000-target sample: the bound check reads every row, so the released row
    order (it follows the keyed tokens, i.e. the release key) cannot move the measured lift."""
    _, prot = _synthetic(3500)
    shuffled = prot.sample(frac=1.0, random_state=3)
    for c in SENS:
        a, b = AL.measure(prot, QCOLS, c), AL.measure(shuffled, QCOLS, c)
        assert a == b and a["n_targets"] == 3500


def test_no_known_qi_is_the_base_rate():
    _, prot = _synthetic()
    m = AL.measure(prot, [], "icd10_primary")
    assert m["inference_rate"] == m["baseline_rate"] and m["lift"] == 1.0


@pytest.mark.parametrize("cell", ["", "***", "  "])
def test_no_target_is_unmeasured(cell):
    _, prot = _synthetic(20)
    prot["icd10_primary"] = cell
    assert AL.measure(prot, QCOLS, "icd10_primary") == {"n_targets": 0, "inference_rate": None,
                                                        "baseline_rate": None, "lift": None}
