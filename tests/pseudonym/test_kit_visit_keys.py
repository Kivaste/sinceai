"""Real-kit check on visit keys. Aggregate counts only; no values are printed.

Skipped when the kit is absent (PETS_KIT, else the conventions path).
"""

import hashlib
import os
import secrets
from pathlib import Path

import pandas as pd
import pytest

from pets_release.pseudonym import (
    RECORD_KEY,
    MasterKey,
    Scope,
    pseudonymiser_for,
    release_scope_id,
)

_DEFAULT_KIT = Path(
    r"C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)"
    r"\TRUSTED_PETS_PROVING_GROUND_2026"
)
KIT = Path(os.environ.get("PETS_KIT") or _DEFAULT_KIT)
TABLES = ("ed_visits", "lab_results")


@pytest.mark.kit
def test_visit_keys_tokenise_one_to_one_and_keep_the_join(record_property):
    files = {t: KIT / "data" / "health" / f"{t}.csv" for t in TABLES}
    assert all(p.is_file() for p in files.values()), "kit required but not found"
    digests = {t: hashlib.sha256(p.read_bytes()).hexdigest() for t, p in files.items()}
    rsid = release_scope_id(
        scenario="HEALTH-S1",
        recipient=None,
        input_digests=digests,
        tool_revision="test",
    )
    p = pseudonymiser_for(MasterKey.from_text(secrets.token_hex(32)))
    scope = Scope.release(rsid)
    raw, tok = {}, {}
    for t, path in files.items():
        col = pd.read_csv(path, dtype=str, usecols=["visit_id"], keep_default_na=False, na_filter=False)
        raw[t] = set(col["visit_id"])
        assert "" not in raw[t]
        tok[t] = {p.token(v, label=RECORD_KEY, scope=scope) for v in raw[t]}
        assert len(tok[t]) == len(raw[t])
        record_property(f"{t}.distinctInputs", len(raw[t]))
    lab, ed = raw["lab_results"], raw["ed_visits"]
    raw_cov = len(lab & ed) / len(lab)
    tok_cov = len(tok["lab_results"] & tok["ed_visits"]) / len(tok["lab_results"])
    record_property("joinCoverageShare", round(tok_cov, 6))
    assert 0.0 <= tok_cov <= 1.0
    assert tok_cov == raw_cov
