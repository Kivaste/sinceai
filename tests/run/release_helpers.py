"""Shared synthetic release setup/tampering helpers; assertions stay in the tests."""
from __future__ import annotations

import hashlib
import json

from run_helpers import TEST_KEY, coarse_qis

from pets_release.manifest import canonical_bytes, compute_signature
from pets_release.pseudonym import MasterKey, manifest_signing_key

MANIFEST = "privacy_manifest.json"
PLANTED_HEALTH = "diabetes follow-up panel"  # synthetic; matches bundled health lexicon


def plant_health(folder):
    """Plant a low-severity term in the synthetic kit's released lab text."""
    import pandas as pd

    coarse_qis(folder)
    path = folder / "lab_results.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    df.loc[0, "test_name"] = PLANTED_HEALTH
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def resign(release) -> None:
    """Rebind file digests and re-sign with the published test key to isolate tampering tests."""
    manifest = json.loads((release / MANIFEST).read_text(encoding="utf-8"))
    manifest["bindings"]["files"] = {
        name: hashlib.sha256((release / name).read_bytes()).hexdigest()
        for name in sorted(manifest["bindings"]["files"])
    }
    key = manifest_signing_key(MasterKey.from_text(TEST_KEY))
    manifest["signature"]["value"] = "0" * 64
    manifest["signature"]["value"] = compute_signature(manifest, key)
    (release / MANIFEST).write_bytes(canonical_bytes(manifest))
