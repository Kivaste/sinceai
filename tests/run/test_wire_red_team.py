"""#139: the measured release records the red-team attacker's rates in ``residualRisks`` (measure-only, D54).

Seam: the measure CLI (``wire.main``) with the real measurer, the real attacker child and the real bridge child, on
the synthetic minikit plus hand-made adversary, identity and auxiliary files (#138's fixture). The manifest is read
from the release the CLI wrote.

Rule: the bridge turns each red-team attack into closed residualRisks entries: rate, denominator (attacker
targets) and a content-free description; an attack that could not run is ``not_measured`` with its reason, never a
minted 0.0.

Rows (trigger -> result):
  measured run with an auxiliary person table and a catalog marking icd10_primary sensitive
      -> linkage-redteam-{cross-dataset,range-aware}[-guess] measured over the 3 adversary rows;
         attribute-inference-redteam-icd10_primary and its -baseline measured over the released visits
  no auxiliary table in the kit -> linkage-redteam-cross-dataset(-guess) not_measured, reason names it
  no released sensitive attribute in the catalog -> attribute-inference-redteam not_measured, reason names it
"""
from __future__ import annotations

import pandas as pd
import pytest
from run_helpers import run_args
from test_wire_attacker_rates import _risks, attack_kit  # noqa: F401  (fixture)

from pets_release.measure import wire

SENSITIVE_ROW = ("health,ed_visits,icd10_primary,sensitive_attribute,code,dx\n"
                 "health,lab_results,value,sensitive_attribute,numerical,m\n")
LINK = ("linkage-redteam-cross-dataset", "linkage-redteam-cross-dataset-guess",
        "linkage-redteam-range-aware", "linkage-redteam-range-aware-guess")
JOIN = ("linkage-redteam-release-join", "linkage-redteam-release-join-guess", "linkage-redteam-release-join-lab_results")


def _aux(kit) -> None:
    """A finance customer list: one synthetic stranger, plus (r2, release join) the first minikit visit's person
    by national ID, with its birth date and municipality."""
    p = kit / "data" / "finance"
    p.mkdir(parents=True)
    v = pd.read_csv(kit / "data" / "health" / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    pd.DataFrame({"customer_id": ["c1", "c2"], "full_name": ["Synthetic Person", "Synthetic Patient"],
                  "birth_date": ["1980-01-01", v.at[0, "date_of_birth"][:10]],
                  "city": ["Nowhere", v.at[0, "municipality"]], "hetu": ["none-0", v.at[0, "patient_hetu"]]}).to_csv(
        p / "customers.csv", index=False)


def _sensitive(kit) -> None:
    with (kit / "metadata" / "field_catalog.csv").open("a", encoding="utf-8") as f:
        f.write(SENSITIVE_ROW)


def test_measured_run_records_every_red_team_rate_with_its_denominator(attack_kit):
    kit, out = attack_kit
    _aux(kit)
    _sensitive(kit)
    assert wire.main(run_args(kit, out)[1:]) == 0
    risks = _risks(out)
    for rid in LINK:
        r = risks[rid]
        assert r["kind"] == "linkage" and r["rate"]["status"] == "measured", rid
        assert r["rate"]["denominator"] == {"unit": "rows", "n": 3} and 0.0 <= r["rate"]["value"] <= 1.0
        assert "seed 0" in r["description"] and "3000" in r["description"]
    visits = pd.read_csv(out / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    n_icd = int((visits["icd10_primary"].str.strip() != "").sum())
    for rid in ("attribute-inference-redteam-icd10_primary", "attribute-inference-redteam-icd10_primary-baseline"):
        r = risks[rid]
        assert r["kind"] == "attribute_inference" and r["rate"]["status"] == "measured", rid
        assert r["rate"]["denominator"] == {"unit": "rows", "n": n_icd}
    assert "base rate" in risks["attribute-inference-redteam-icd10_primary-baseline"]["description"]
    # r2 (Spec r1): every released table's sensitive attribute, and the register joined to the released rows
    for rid in ("attribute-inference-redteam-lab_results.value", "attribute-inference-redteam-lab_results.value-baseline"):
        assert risks[rid]["rate"]["status"] == "measured", rid
    for rid in JOIN:
        r = risks[rid]
        assert r["kind"] == "linkage" and r["rate"]["status"] == "measured", rid
        assert 0.0 <= r["rate"]["value"] <= 1.0 and r["rate"]["denominator"]["n"] >= 1
    assert risks["linkage-redteam-release-join"]["rate"]["denominator"] == {"unit": "rows", "n": 1}


@pytest.mark.parametrize("missing", ["aux", "sensitive"])
def test_red_team_attack_that_cannot_run_is_not_measured_with_its_reason(attack_kit, missing):
    kit, out = attack_kit
    if missing != "aux":
        _aux(kit)
    if missing != "sensitive":
        _sensitive(kit)
    assert wire.main(run_args(kit, out)[1:]) == 0
    risks = _risks(out)
    if missing == "aux":
        for rid in LINK[:2]:
            rate = risks[rid]["rate"]
            assert rate["status"] == "not_measured" and "no auxiliary" in rate["reason"], rid
        assert risks["linkage-redteam-range-aware"]["rate"]["status"] == "measured"
        assert risks["attribute-inference-redteam-icd10_primary"]["rate"]["status"] == "measured"
    else:
        rate = risks["attribute-inference-redteam"]["rate"]
        assert rate["status"] == "not_measured" and "no released sensitive attribute" in rate["reason"]
        assert risks["linkage-redteam-cross-dataset"]["rate"]["status"] == "measured"
