"""Counts-only evidence for ticket 28: two real HEALTH-S1 releases for two recipients.

Usage: python scripts/recipient_evidence.py <kit root> <work dir>

Runs the real CLI (`pets-release run --recipient`) twice on the kit with a throwaway master key
(never stored, never printed), then compares the token columns named by each manifest's contract.
Prints aggregate counts only: no token, no key material, no row value. The two release folders stay
in <work dir> (outside git) for `pets-release verify`.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pandas as pd

RECIPIENTS = ("recipient-a", "recipient-b")


def main(kit: Path, work: Path) -> dict:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC",
               PETS_HMAC_KEY=secrets.token_hex(32))
    toks: dict[str, set[str]] = {}
    cov: dict[str, float] = {}
    exits: dict[str, dict[str, int]] = {}
    for rec in RECIPIENTS:
        out = work / rec
        run = subprocess.run([sys.executable, "-m", "pets_release", "run", "--scenario", "HEALTH-S1",
                              "--plan", "hand", "--kit", str(kit), "--out", str(out), "--recipient", rec,
                              "--created", "2026-11-07T00:00:00Z"], env=env, capture_output=True, text=True)
        exits[rec] = {"run": run.returncode}
        if run.returncode != 0:
            print(json.dumps({"recipient": rec, "runExit": run.returncode}))
            raise SystemExit(1)
        ver = subprocess.run([sys.executable, "-m", "pets_release", "verify", "--full", "--kit", str(kit),
                              str(out)], env=env, capture_output=True, text=True)
        exits[rec]["verifyFull"] = ver.returncode
        contract = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["contract"]
        cols = sorted({(t["table"], t["column"]) for t in contract["tokens"]})
        frames = {t: pd.read_csv(out / f"{t}.csv", dtype=str, keep_default_na=False) for t, _ in cols}
        toks[rec] = {v for t, c in cols for v in frames[t][c]}
        lab, ed = set(frames["lab_results"]["visit_id"]), set(frames["ed_visits"]["visit_id"])
        cov[rec] = round(len(lab & ed) / len(lab), 6) if lab else 0.0
        exits[rec]["tokenColumns"] = len(cols)
        exits[rec]["distinctTokens"] = len(toks[rec])
    result = {"perRecipient": exits, "joinCoverageLabInEd": cov,
              "tokenOverlapBetweenRecipients": len(toks[RECIPIENTS[0]] & toks[RECIPIENTS[1]])}
    print(json.dumps(result, sort_keys=True))
    if result["tokenOverlapBetweenRecipients"] != 0 or any(e["verifyFull"] != 0 for e in exits.values()):
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
