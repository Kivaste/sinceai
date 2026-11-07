"""Run both personas on a HEALTH-S1 release folder and print aggregate rates.

python -m pets_attacker --kit <kit root> --release <folder with ed_visits.csv + rowmap_ed_visits.csv> --label b2k --out out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .linkage import qis_from_spec
from .personas import broker_attack, insider_attack
from .truth import load_adversary_truth, load_identity, load_rowmap

DOMAIN, TABLE, RECORD_KEY = "health", "ed_visits", "visit_id"


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def run(kit: Path, release: Path, label: str) -> dict:
    rowmap_path = release / f"rowmap_{TABLE}.csv"
    prot_path = release / f"{TABLE}.csv"
    if not rowmap_path.is_file() or not prot_path.is_file():
        raise FileNotFoundError("release folder needs ed_visits.csv and rowmap_ed_visits.csv")
    protected, rowmap = _csv(prot_path), load_rowmap(rowmap_path)
    original = _csv(kit / "data" / DOMAIN / f"{TABLE}.csv")
    identity = load_identity(kit, DOMAIN, TABLE)
    specs = json.loads((kit / "metadata" / "attack_specs.json").read_text(encoding="utf-8"))["attacks"]
    broker = {}
    for spec in specs:
        if spec["dataset"] != DOMAIN or spec["table"] != TABLE:
            continue
        adv = _csv(kit / "adversary" / f"{spec['adversary']}.csv")
        qis = qis_from_spec(spec["qis"], protected.columns)
        broker[spec["adversary"]] = broker_attack(
            adv, load_adversary_truth(kit, spec["adversary"]), protected, rowmap, identity, qis,
            original=original, record_key=RECORD_KEY, sensitive=spec.get("sensitive"))
    insider = insider_attack(original, protected, rowmap, identity, date_col="arrival_ts", place_col="municipality",
                             record_key=RECORD_KEY, sensitive="icd10_primary")
    return {"label": label, "broker": broker, "insider": insider}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pets_attacker")
    ap.add_argument("--kit", required=True, type=Path)
    ap.add_argument("--release", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        res = run(a.kit, a.release, a.label)
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"attacker: refused: {type(e).__name__}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0
