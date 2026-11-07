"""Must-fix #138: the measured release records both independent attacker personas' rates in ``residualRisks``.

Seam: the measure CLI (``python -m pets_release.measure.wire`` -> ``wire.main``) with the real measurer, the real
pets-eval child and the real attacker, on the synthetic minikit plus hand-made adversary and identity files.
The manifest is read from the release the CLI wrote.

Rule: the measured path runs the broker persona (one entry per adversary source in the kit's attack specs) and
the municipal-insider persona against the release and records each linkage rate with its denominator. When the
attacker cannot run, the rate is ``not_measured`` with a truthful, current reason; never a minted 0.0 and never
the stale "wired in the story-kit ticket" reason.

Rows (trigger -> result):
  measured run, kit has attack specs + adversary + identity files -> linkage-broker-<adv> and linkage-insider
      measured, value in [0, 1], denominator n = attacker targets (3 adversary rows; insider: released visits)
  plain `pets-release run` (no measurer) -> linkage-attackers not_measured, reason names the measured run
  measured run, the kit's attack specs file is absent (attacker refuses) -> released; linkage-attackers is
      not_measured with a reason naming the failed attacker run; no linkage entry is measured
"""
from __future__ import annotations

import json

import pandas as pd
import pytest
from run_helpers import TEST_KEY, build_kit, cli, coarse_qis, run_args

from pets_release.manifest import MANIFEST_FILENAME, loads_strict
from pets_release.measure import wire

CATALOG = ("dataset,table,column,privacy_role,data_kind,subtype\n"
           "health,ed_visits,visit_id,record_key,identifier,id\n"
           "health,ed_visits,municipality,quasi_identifier,categorical,place\n"
           "health,lab_results,lab_id,record_key,identifier,id\n"
           "health,clinical_notes,note_id,record_key,identifier,id\n"
           "health,published_weekly_stats,stat_id,record_key,identifier,id\n")
ADV = "public_directory"
STALE = "story-kit ticket"


def _bench() -> dict:
    b = {"privacy": 0.5, "utility": 0.5, "composite": 0.5, "worst_reid": 0.5, "residual_identifiers": 0.0,
         "utility_tasks": {"H-U2": 0.5}, "utility_by_scenario": {"HEALTH-S1": 0.5}, "runtime_s": 1.0}
    return {"generated": "fixture", "baselines": {f"{p}_health": dict(b) for p in ("B0", "B2", "B2K")}}


def _attack_files(kit) -> None:
    """Identity map (visit -> person) for the synthetic visits, and one broker source of 3 adversary rows that
    know only the municipality. After ``coarse_qis`` every visit shares one municipality, so no adversary row
    can single out a visit: the broker's linkage rate is 0.0 over 3 targets by construction."""
    visits = pd.read_csv(kit / "data" / "health" / "ed_visits.csv", dtype=str, keep_default_na=False,
                         na_filter=False)
    ident = kit / "truth"
    ident.mkdir()
    pd.DataFrame({"record_id": visits["visit_id"], "person_id": visits["patient_hetu"]}).to_csv(
        ident / "health__ed_visits.csv", index=False)
    (kit / "adversary").mkdir()
    ids = ["a0", "a1", "a2"]
    pd.DataFrame({"adv_row_id": ids, "place": [visits.at[0, "municipality"]] * 3}).to_csv(
        kit / "adversary" / f"{ADV}.csv", index=False)
    pd.DataFrame({"adv_row_id": ids, "person_id": list(visits["patient_hetu"][:3])}).to_csv(
        ident / f"adversary__{ADV}.csv", index=False)
    spec = {"attacks": [{"adversary": ADV, "dataset": "health", "table": "ed_visits", "sensitive": "icd10_primary",
                         "qis": [{"kind": "exact", "adversary": ["place"], "protected": ["municipality"]}]}]}
    (kit / "metadata" / "attack_specs.json").write_text(json.dumps(spec), encoding="utf-8")


@pytest.fixture
def attack_kit(tmp_path, monkeypatch):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=coarse_qis)
    (kit / "metadata" / "field_catalog.csv").write_text(CATALOG, encoding="utf-8")
    (kit / "results").mkdir()
    (kit / "results" / "benchmark.json").write_text(json.dumps(_bench()), encoding="utf-8")
    _attack_files(kit)
    return kit, tmp_path / "rel"


def _risks(out) -> dict:
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    return {r["risk"]: r for r in m["residualRisks"]}


def test_measured_run_records_both_persona_linkage_rates_with_denominators(attack_kit):
    kit, out = attack_kit
    assert wire.main(run_args(kit, out)[1:]) == 0
    risks = _risks(out)
    released_visits = len(pd.read_csv(out / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False))
    broker, insider = risks[f"linkage-broker-{ADV}"]["rate"], risks["linkage-insider"]["rate"]
    assert broker["status"] == "measured" and broker["value"] == 0.0
    assert broker["denominator"] == {"unit": "rows", "n": 3}
    assert insider["status"] == "measured" and 0.0 <= insider["value"] <= 1.0
    assert insider["denominator"] == {"unit": "rows", "n": released_visits}
    assert not any(STALE in r["rate"].get("reason", "") for r in risks.values())


def test_plain_run_names_the_measured_run_instead_of_a_closed_ticket(attack_kit):
    """Seam: the real ``pets-release run`` CLI (subprocess). The plain run measures nothing; its reason says where
    the measured values come from, never the stale ticket reference."""
    kit, out = attack_kit
    p = cli(*run_args(kit, out))
    assert p.returncode == 0, p.stderr[-500:]
    risks = _risks(out)
    assert not any(STALE in r["rate"].get("reason", "") for r in risks.values())
    assert "measure.wire" in risks["linkage-attackers"]["rate"]["reason"]


def test_attacker_that_cannot_run_is_recorded_as_not_measured_with_a_current_reason(attack_kit):
    kit, out = attack_kit
    (kit / "metadata" / "attack_specs.json").unlink()
    assert wire.main(run_args(kit, out)[1:]) == 0
    risks = _risks(out)
    rate = risks["linkage-attackers"]["rate"]
    assert rate["status"] == "not_measured" and "attacker run failed" in rate["reason"]
    assert not any(r["kind"] == "linkage" and r["rate"]["status"] == "measured" for r in risks.values())
    assert not any(STALE in r["rate"].get("reason", "") for r in risks.values())
