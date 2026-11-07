"""Follow-up #85 item 1.5: fixture-based counterpart of the kit-gated visit-key join check. Content-free."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

import pandas as pd

from pets_release.pseudonym import (
    RECORD_KEY,
    MasterKey,
    Scope,
    pseudonymiser_for,
    release_scope_id,
)

MINIKIT = Path(__file__).resolve().parents[1] / "fixtures" / "minikit" / "health"


def test_visit_keys_tokenise_one_to_one_and_keep_the_join_on_fixture():
    tables = ("ed_visits", "lab_results")
    files = {t: MINIKIT / f"{t}.csv" for t in tables}
    digests = {t: hashlib.sha256(p.read_bytes()).hexdigest() for t, p in files.items()}
    rsid = release_scope_id(scenario="HEALTH-S1", recipient=None, input_digests=digests, tool_revision="test")
    p = pseudonymiser_for(MasterKey.from_text(secrets.token_hex(32)))
    scope = Scope.release(rsid)
    raw, tok = {}, {}
    for t, path in files.items():
        col = pd.read_csv(path, dtype=str, usecols=["visit_id"], keep_default_na=False)
        raw[t] = set(col["visit_id"])
        assert raw[t] and "" not in raw[t]
        tok[t] = {p.token(v, label=RECORD_KEY, scope=scope) for v in raw[t]}
        assert len(tok[t]) == len(raw[t])
    lab, ed = raw["lab_results"], raw["ed_visits"]
    assert lab & ed, "fixture must exercise a non-empty join"
    assert len(tok["lab_results"] & tok["ed_visits"]) / len(lab) == len(lab & ed) / len(lab)
