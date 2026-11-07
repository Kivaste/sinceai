"""Aggregate-only evidence for ticket 28 on the real kit's visit keys.

Usage: python scripts/recipient_evidence.py <kit root> <out dir>

Pseudonymises ed_visits.visit_id and lab_results.visit_id for two recipients
with a throwaway key. Writes counts only (no values, no tokens) to
<out dir>/recipient_evidence.json and prints the same.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from pathlib import Path

import pandas as pd

from pets_release.pseudonym import RECORD_KEY, MasterKey
from pets_release.recipient import release_scope

TABLES = ("ed_visits", "lab_results")


def main(kit: Path, out: Path) -> dict:
    files = {t: kit / "data" / "health" / f"{t}.csv" for t in TABLES}
    digests = {t: hashlib.sha256(p.read_bytes()).hexdigest() for t, p in files.items()}
    raw = {
        t: set(pd.read_csv(p, dtype=str, usecols=["visit_id"], keep_default_na=False)["visit_id"])
        for t, p in files.items()
    }
    master = MasterKey.from_text(secrets.token_hex(32))  # throwaway, never stored
    toks: dict[str, dict[str, set[str]]] = {}
    for rec in ("recipient-a", "recipient-b"):
        rs = release_scope(
            master,
            scenario="HEALTH-S1",
            recipient=rec,
            input_digests=digests,
            tool_revision="evidence",
        )
        toks[rec] = {
            t: {rs.pseudonymiser.token(v, label=RECORD_KEY, scope=rs.scope) for v in raw[t]}
            for t in TABLES
        }

    def cov(tk: dict[str, set[str]]) -> float:
        lab = tk["lab_results"]
        return len(lab & tk["ed_visits"]) / len(lab)

    raw_cov = len(raw["lab_results"] & raw["ed_visits"]) / len(raw["lab_results"])
    all_a = toks["recipient-a"]["ed_visits"] | toks["recipient-a"]["lab_results"]
    all_b = toks["recipient-b"]["ed_visits"] | toks["recipient-b"]["lab_results"]
    result = {
        "distinctInputs": {t: len(raw[t]) for t in TABLES},
        "tokenOverlapBetweenRecipients": len(all_a & all_b),
        "joinCoverage": {
            "raw": round(raw_cov, 6),
            "recipient-a": round(cov(toks["recipient-a"]), 6),
            "recipient-b": round(cov(toks["recipient-b"]), 6),
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "recipient_evidence.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
