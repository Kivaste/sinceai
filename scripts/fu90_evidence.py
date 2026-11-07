"""#90 counts-only evidence: real HEALTH-S1 release, gate, both verification tiers and purpose scores.

Usage: python scripts/fu90_evidence.py <kit root> <new release folder>
Uses a throwaway master key held only in memory; never prints values, tokens or key material.
The production release and private scoring artifacts stay in the supplied local folder, outside git.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from collections import Counter
from pathlib import Path


def main(kit: Path, out: Path) -> int:
    env = dict(os.environ, PYTHONUTF8="1", TZ="UTC", PETS_HMAC_KEY=secrets.token_hex(32))
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    commands = {
        "run": ["run", "--scenario", "HEALTH-S1", "--plan", "hand", "--kit", str(kit),
                "--out", str(out), "--recipient", "fu90-evidence", "--created", "2026-11-07T00:00:00Z"],
        "verifyLimited": ["verify", str(out)],
        "verifyFull": ["verify", "--full", "--kit", str(kit), str(out)],
    }
    exits = {}
    for name, args in commands.items():
        proc = subprocess.run([sys.executable, "-m", "pets_release", *args], env=env,
                              capture_output=True, text=True, encoding="utf-8", check=False)
        exits[name] = proc.returncode
        if proc.returncode != 0:
            print(json.dumps({"exits": exits}, sort_keys=True))
            return 1  # Do not print subprocess diagnostics, which are not an allowlisted metric.
    manifest = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    scoring = out.with_name(out.name + ".scoring")
    gate = json.loads((scoring / "gate_report.json").read_text(encoding="utf-8"))
    suppression = json.loads((scoring / "suppression_report.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "revision": manifest["bindings"]["toolRevision"], "exits": exits,
        "gate": {"refused": gate["refused"], "statuses": dict(Counter(r["status"] for r in gate["records"])),
                 "hits": sum(r["hits"] for r in gate["records"]),
                 "denominators": {r["check"]: r["denominator"] for r in gate["records"]}},
        "suppression": suppression,
        "purpose": manifest["measured"]["utility"]["tasks"],
        "releasedColumnCount": sum(len(t["columns"]) for t in manifest["contract"]["files"].values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
