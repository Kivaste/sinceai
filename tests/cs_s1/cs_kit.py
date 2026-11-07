"""A CS-S1 kit folder from ticket 03's synthetic minikit (synthetic rows only), with synthetic gold spans
derived from the generator's own known values (customer names and e-mails), so the redaction measurement
path runs end to end."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MINIKIT = ROOT / "tests" / "fixtures" / "minikit" / "customer_service"
SCENARIOS = [
    {"id": "HEALTH-S1", "dataset": "health", "title": "synthetic", "utility_requirements": ["H-U2"]},
    {"id": "CS-S1", "dataset": "customer_service", "title": "synthetic",
     "utility_requirements": ["CS-U1", "CS-U3", "CS-U4", "CS-U5"]},
]
GOLD = "customer_service__turns__text.jsonl"


def build_cs_kit(root: Path, gold: bool = True) -> Path:
    (root / "metadata" / "pii_spans").mkdir(parents=True)
    (root / "data" / "customer_service").mkdir(parents=True)
    (root / "metadata" / "scenarios.json").write_text(json.dumps(SCENARIOS), encoding="utf-8")
    for p in sorted(MINIKIT.glob("*.csv")):
        shutil.copyfile(p, root / "data" / "customer_service" / p.name)
    if gold:
        cust = pd.read_csv(MINIKIT / "customers.csv", dtype=str, keep_default_na=False)
        turns = pd.read_csv(MINIKIT / "turns.csv", dtype=str, keep_default_na=False)
        known = [(v, "PERSON") for v in cust.full_name] + [(v, "EMAIL") for v in cust.email]
        with open(root / "metadata" / "pii_spans" / GOLD, "w", encoding="utf-8", newline="\n") as f:
            for tid, text in zip(turns.turn_id, turns.text):
                spans = []
                for v, lab in known:
                    i = text.find(v)
                    if v and i >= 0:
                        spans.append({"start": i, "end": i + len(v), "label": lab})
                if spans:
                    f.write(json.dumps({"record_id": tid, "spans": sorted(spans, key=lambda s: s["start"])}) + "\n")
    return root


def cs_run_args(kit: Path, out: Path) -> list[str]:
    return ["run", "--scenario", "CS-S1", "--plan", "hand", "--kit", str(kit), "--out", str(out),
            "--created", "2026-11-07T00:00:00Z"]
