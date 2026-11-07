"""#69: real verify CLI re-runs quantization, even when file/contract digests are rebound.

Start with the production run CLI's HEALTH-S1 hand-plan release (synthetic kit).
Planted rounded/off-origin/wrong-width cells -> verify exit 1 via contract.forms,
not just a digest mismatch. No gate record or assertion is fabricated.
"""
from __future__ import annotations

import hashlib
import json
import shutil

import pandas as pd
import pytest
from run_helpers import cli

from pets_release.contract import generate
from pets_release.manifest import canonical_bytes, canonical_digest
from pets_release.policy import get_policy, hand_plan


@pytest.mark.parametrize("rung, params, planted", [
    ("num.round", {"unit": "0.5"}, "1.3"),
    ("num.bin", {"width": "2.5", "origin": "0.5"}, "[1.3,3.8)"),
    ("num.bin", {"width": "2.5", "origin": "0.5"}, "[0.5,4.0)"),
])
def test_verify_cli_reapplies_declared_numeric_parameters(released, tmp_path, rung, params, planted):
    _, original, produced = released
    assert produced.returncode == 0, produced.stdout + produced.stderr
    folder = tmp_path / "tampered"
    shutil.copytree(original, folder)
    assert cli("verify", str(folder)).returncode == 0
    manifest_path = folder / "privacy_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    plan = hand_plan("HEALTH-S1")
    entry = next(e for e in plan if (e["table"], e["column"]) == ("ed_visits", "temp_c"))
    entry.update(rung=rung, params=params)
    manifest["contract"] = generate(get_policy("HEALTH-S1"), plan)
    manifest["bindings"]["contractDigest"] = canonical_digest(manifest["contract"])
    # Recipient mode intentionally cannot authenticate a rebound declaration, but it must
    # independently reject cells that contradict that declaration (see the tamper limitation).
    pet = next(p for p in manifest["pets"] if (p["table"], p["column"]) == ("ed_visits", "temp_c"))
    pet.update(pet="rounding" if rung == "num.round" else "binning", params={"rung": rung, **params})
    justification = next(j for j in manifest["fieldJustifications"]
                         if (j["table"], j["column"]) == ("ed_visits", "temp_c"))
    justification["rung"] = rung
    csv_path = folder / "ed_visits.csv"
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_filter=False)
    frame["temp_c"] = planted
    frame.to_csv(csv_path, index=False, lineterminator="\n")
    manifest["bindings"]["files"]["ed_visits.csv"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_bytes(manifest))
    checked = cli("verify", str(folder))
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert "check contract.forms [release]" in checked.stdout and "formMismatch" in checked.stdout
    assert "digest mismatch" not in checked.stdout
