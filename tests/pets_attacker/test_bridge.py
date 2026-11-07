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
    for r in risks:
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
    assert len(json.loads(out.read_text(encoding="utf-8"))["residualRisks"]) == 6
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
