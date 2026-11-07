"""Kit glue: k specs and rung params stay consistent with the scenario policies (schema names only)."""

from __future__ import annotations

from pets_release.minimiser.kit import KSPECS, params_from_plan
from pets_release.policy import get_policy, hand_plan


def test_kspec_names_policy_columns():
    for scen, ks in KSPECS.items():
        cols = set(get_policy(scen).floors)
        assert (ks["person"]["table"], ks["person"]["column"]) in cols
        assert all((t, c) in cols for t, c in ks["record_keys"].items())
        for j in ks["joins"]:
            assert (j["table"], j["column"]) in cols and (j["ref_table"], j["ref_column"]) in cols


def test_params_from_hand_plan_cover_both_age_rungs():
    p = params_from_plan(hand_plan("HEALTH-S1"))
    dob = p[("ed_visits", "date_of_birth")]
    assert dob["age.band5"] == dob["age.band10"] == {"ref_column": "arrival_ts", "output": "age_band"}
    assert p[("ed_visits", "municipality")]["geo.topn"]["n"] >= 8
