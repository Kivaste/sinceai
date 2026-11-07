"""Run both personas on a HEALTH-S1 release folder and print aggregate rates.

python -m pets_attacker --kit <kit root> --release <folder with ed_visits.csv + rowmap_ed_visits.csv> --label b2k --out out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from pets_release.manifest.canonical import loads_strict
from pets_release.offline import entry_point

from .linkage import RungError, qis_from_spec
from .personas import broker_attack, insider_attack
from .truth import load_adversary_truth, load_identity, load_rowmap

DOMAIN, TABLE, RECORD_KEY = "health", "ed_visits", "visit_id"


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _rowmap_path(release: Path, scoring_dir: Path | None, rowmaps: dict) -> Path:
    """Explicit --rowmap wins, then --scoring-dir, else the release folder (kit-baseline layout). No fallback."""
    if TABLE in rowmaps:
        return rowmaps[TABLE]
    return (scoring_dir if scoring_dir is not None else release) / f"rowmap_{TABLE}.csv"


def run(kit: Path, release: Path, label: str, scoring_dir: Path | None = None, rowmaps: dict | None = None,
        rungs_path: Path | None = None) -> dict:
    if rungs_path is None:
        raise RungError("--rungs is required: rungs are never inferred from cell shape")
    # #114: strict (duplicate keys, NaN/Infinity refuse); the rung record is never partially parsed
    rungs = loads_strict(Path(rungs_path).read_text(encoding="utf-8-sig")).get(TABLE)
    if not isinstance(rungs, dict):
        raise RungError("rung metadata has no entry for the table")
    rowmap_path = _rowmap_path(release, scoring_dir, rowmaps or {})
    prot_path = release / f"{TABLE}.csv"
    if not rowmap_path.is_file() or not prot_path.is_file():
        raise FileNotFoundError("release needs ed_visits.csv and a row map (release dir, --scoring-dir or --rowmap)")
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
            original=original, record_key=RECORD_KEY, sensitive=spec.get("sensitive"), rungs=rungs)
    insider = insider_attack(original, protected, rowmap, identity, date_col="arrival_ts", place_col="municipality",
                             record_key=RECORD_KEY, sensitive="icd10_primary", rungs=rungs)
    return {"label": label, "broker": broker, "insider": insider}


@entry_point
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pets_attacker")
    ap.add_argument("--kit", required=True, type=Path)
    ap.add_argument("--release", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--rungs", type=Path, help="JSON {table: {column: rung}} from the release contract (required)")
    ap.add_argument("--scoring-dir", type=Path, help="folder holding rowmap_<table>.csv (e.g. <out>.scoring)")
    ap.add_argument("--rowmap", action="append", default=[], metavar="TABLE=PATH", help="explicit row map for a table")
    a = ap.parse_args(argv)
    rowmaps = {}
    for item in a.rowmap:
        table, sep, path = item.partition("=")
        if not sep or not table or not path:
            print("attacker: refused: bad --rowmap", file=sys.stderr)
            return 2
        rowmaps[table] = Path(path)
    try:
        res = run(a.kit, a.release, a.label, a.scoring_dir, rowmaps, a.rungs)
    except (FileNotFoundError, KeyError, IndexError, ValueError) as e:
        print(f"attacker: refused: {type(e).__name__}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0





