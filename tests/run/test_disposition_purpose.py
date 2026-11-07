"""#90 L2: retain disposition because purpose checks exclude cancelled duplicates.

Seams: real CLI release/manifest and the production purpose-check adapter.
Rows (trigger -> result):
  cancelled duplicate with a synthetic extreme LOS -> H-U2 ignores it when disposition is present
  withhold disposition from that same table        -> H-U2 changes (the exclusion is lost)
  CLI hand-plan release                           -> retains disposition with its true purpose reason

The kit catalog calls disposition a sensitive_attribute, not a quasi_identifier: no QI expansion.
"""
from __future__ import annotations

import json

import pandas as pd

from pets_release.kiteval import purpose_check


def test_disposition_is_needed_to_exclude_cancelled_duplicates():
    # Hand-made rows: three real visits and four cancelled duplicate records, one triage group.
    visits = pd.DataFrame({"triage": ["A"] * 7, "los_minutes": ["10"] * 3 + ["1000"] * 4,
                           "disposition": ["discharged"] * 3 + ["cancelled_duplicate"] * 4}, dtype=str)
    source = {"ed_visits": visits}
    kept = purpose_check("H-U2", source, source)
    withheld = purpose_check("H-U2", source, {"ed_visits": visits.drop(columns="disposition")})
    assert kept["status"] == withheld["status"] == "ok"
    assert kept["score"] == 1.0
    assert withheld["score"] == 0.0


def test_cli_retains_disposition_with_its_actual_purpose_justification(released):
    _, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    visits = pd.read_csv(out / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
    assert "disposition" in visits.columns
    manifest = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    field = next(f for f in manifest["fieldJustifications"]
                 if (f["table"], f["column"]) == ("ed_visits", "disposition"))
    assert field["decision"] == "released"
    assert "cancelled duplicate" in field["reason"]
    assert "purpose check" in field["reason"]
