"""Bridge: attacker aggregate JSON -> manifest residualRisks entries (closed shape, values-free)."""

from __future__ import annotations

import json

import pytest

from pets_attacker import bridge
from pets_release.manifest.validate import validate_manifest_file  # noqa: F401  (production validator import)

ATTACK = {
    "label": "t",
    "broker": {
        "news_clips_health": {"reidentification_rate": 0.08, "attribute_inference_rate": 0.05, "n_targets": 200, "evaluated": True},
        "public_directory": {"reidentification_rate": 0.0, "attribute_inference_rate": 0.0, "n_targets": 739, "evaluated": True},
    },
    "insider": {"reidentification_rate": 0.0357, "attribute_inference_rate": 0.0393, "n_targets": 3000, "evaluated": True},
}


def test_entries_cover_both_personas_with_method_names():
    risks = bridge.residual_risks(ATTACK)
    ids = [r["risk"] for r in risks]
    assert ids == sorted(ids)  # the manifest requires risk-sorted order
    assert {"linkage-broker-news_clips_health", "attribute-inference-broker-news_clips_health",
            "linkage-insider", "attribute-inference-insider"} <= set(ids)
    for r in (r for r in risks if "redteam" not in r["risk"]):  # #139: no red_team block here (see below)
        assert set(r) == {"risk", "kind", "label", "rate", "description"}
        assert r["kind"] in ("linkage", "attribute_inference") and r["label"] is None
        assert r["rate"]["status"] == "measured"
        assert 0 <= r["rate"]["value"] <= 1 and r["rate"]["denominator"]["n"] >= 1
        assert "pets_attacker" in r["rate"]["source"]  # method name


def test_unevaluated_or_missing_rate_is_not_measured_never_zero():
    bad = json.loads(json.dumps(ATTACK))
    bad["insider"]["evaluated"] = False
    bad["broker"]["public_directory"]["reidentification_rate"] = None
    by = {r["risk"]: r["rate"] for r in bridge.residual_risks(bad)}
    assert by["linkage-insider"]["status"] == "not_measured"
    assert by["linkage-broker-public_directory"]["status"] == "not_measured"


def test_malformed_input_refuses():
    with pytest.raises(bridge.BridgeError):
        bridge.residual_risks({"label": "x", "broker": {}})
    with pytest.raises(bridge.BridgeError):
        bridge.residual_risks({"broker": {"a": {"reidentification_rate": 1.5, "attribute_inference_rate": 0, "n_targets": 3, "evaluated": True}},
                               "insider": ATTACK["insider"]})


def test_output_has_no_values_only_schema_names_and_numbers():
    text = json.dumps(bridge.residual_risks(ATTACK))
    assert "Anna" not in text
    assert set(bridge.residual_risks(ATTACK)[0]["rate"]) == {"status", "value", "denominator", "source"}


def test_cli_writes_json_and_fails_closed(tmp_path):
    src = tmp_path / "attack.json"
    src.write_text(json.dumps(ATTACK), encoding="utf-8")
    out = tmp_path / "residual.json"
    assert bridge.main(["--attack", str(src), "--out", str(out)]) == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))["residualRisks"]) == 6 + 7  # #139: + 7 red-team entries (not measured: no block)
    src.write_text("{}", encoding="utf-8")
    assert bridge.main(["--attack", str(src), "--out", str(tmp_path / "no.json")]) == 2
    assert not (tmp_path / "no.json").exists()


def test_entries_validate_inside_the_real_manifest_schema():
    """Production validator on the fixture manifest with its residualRisks swapped for the bridge output."""
    import copy
    from pathlib import Path
    from pets_release.manifest.validate import validate_manifest
    fx = Path(__file__).parents[1] / "fixtures" / "manifest" / "release" / "privacy_manifest.json"
    m = json.loads(fx.read_text(encoding="utf-8"))
    m["residualRisks"] = bridge.residual_risks(ATTACK) + [r for r in m["residualRisks"] if r["kind"] in ("note", "tamper_limitation")]
    m["residualRisks"].sort(key=lambda r: r["risk"])
    new = [e for e in validate_manifest(m) if "residualRisks" in e]
    assert new == [], new


RED = {"cross_dataset": {"evaluated": True, "reason": None, "n_targets": 1662, "reidentification_rate": 0.01,
                         "guess_rate": 0.02},
       "range_aware": {"evaluated": False, "reason": "error:RungError"},
       "release_join": {"evaluated": True, "reason": None, "n_targets": 2900, "reidentification_rate": 0.0,
                        "guess_rate": 0.001, "linked_table": "lab_results", "linked_n_targets": 5000,
                        "linked_reidentification_rate": 0.0},
       "attribute_inference": {"evaluated": True, "reason": None, "columns": {
           "icd10_primary": {"evaluated": True, "reason": None, "n_targets": 3000, "inference_rate": 0.3,
                             "baseline_rate": 0.1}}}}


def test_red_team_block_becomes_closed_entries_and_validates_in_the_manifest_schema():
    """#139. Rows: measured attack -> rate + denominator; failed attack -> not_measured with its rendered reason;
    per sensitive column an attacker entry and a -baseline entry."""
    import copy
    from pathlib import Path
    from pets_release.manifest.validate import validate_manifest
    by = {r["risk"]: r for r in bridge.residual_risks(dict(ATTACK, red_team=RED))}
    assert by["linkage-redteam-cross-dataset"]["rate"]["value"] == 0.01
    assert by["linkage-redteam-cross-dataset-guess"]["rate"]["denominator"] == {"unit": "rows", "n": 1662}
    assert by["linkage-redteam-range-aware"]["rate"]["status"] == "not_measured"
    assert by["linkage-redteam-release-join"]["rate"]["denominator"]["n"] == 2900
    assert by["linkage-redteam-release-join-lab_results"]["rate"]["denominator"] == {"unit": "rows", "n": 5000}
    assert "attack failed (RungError)" in by["linkage-redteam-range-aware-guess"]["rate"]["reason"]
    assert by["attribute-inference-redteam-icd10_primary"]["rate"]["value"] == 0.3
    assert by["attribute-inference-redteam-icd10_primary-baseline"]["rate"]["value"] == 0.1
    fx = Path(__file__).parents[1] / "fixtures" / "manifest" / "release" / "privacy_manifest.json"
    m = json.loads(fx.read_text(encoding="utf-8"))
    m["residualRisks"] = sorted(list(by.values()) + [r for r in copy.deepcopy(m["residualRisks"])
                                                     if r["kind"] in ("note", "tamper_limitation")],
                                key=lambda r: r["risk"])
    assert [e for e in validate_manifest(m) if "residualRisks" in e] == []


def test_missing_red_team_block_is_not_measured_and_an_unknown_reason_refuses():
    by = {r["risk"]: r["rate"] for r in bridge.residual_risks(ATTACK)}
    red_ids = [k for k in by if "redteam" in k]
    assert len(red_ids) == 7 and all(by[k]["status"] == "not_measured" for k in red_ids)
    bad = json.loads(json.dumps(RED))
    bad["range_aware"]["reason"] = "Some Free Text"  # only the attacker's own codes reach the manifest
    with pytest.raises(bridge.BridgeError):
        bridge.residual_risks(dict(ATTACK, red_team=bad))


def test_every_red_team_reason_code_is_known_to_the_bridge():
    """r2: a code the bridge cannot render refuses the whole attacker output (fail closed); keep them in step."""
    from pets_attacker import redteam
    assert set(redteam.REASONS) <= set(bridge._REASONS)
