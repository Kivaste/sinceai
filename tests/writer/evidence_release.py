"""Evidence run: write a release from 02's fixture candidate with the REAL check registry (no stubs).

    python tests/writer/evidence_release.py <out_dir>

Producer-scope checks (ticket 11) get a hand-made synthetic source context built from the fixture's lineage:
one person per visit, labs joined to visits. Prints aggregates only (status, reason codes, file names).
Exit 0 released, 1 refused.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from writer_helpers import MASTER, fx, make_candidate

from pets_release.writer import write_release


def producer_context(cand) -> dict:
    visits = {t.name: t for t in cand.tables}["ed_visits.csv"]
    labs = {t.name: t for t in cand.tables}["lab_results.csv"]
    vkeys = list(visits.final) + sorted(visits.suppressed)
    # Synthetic source: lab i belongs to the visit with the same index in the fixture's original order.
    src_visits = pd.DataFrame({"visit_key": vkeys,
                               "patient_id": [f"synthetic-person-{i:03d}" for i in range(len(vkeys))],
                               "patient_name": [f"Synthetic Person {i:03d}" for i in range(len(vkeys))]},
                              dtype=str)
    lkeys = list(labs.final) + sorted(labs.suppressed)
    src_labs = pd.DataFrame({"lab_key": lkeys, "visit_key": [vkeys[i % len(vkeys)] for i in range(len(lkeys))]},
                            dtype=str)

    def rowmap(t):
        # writer sorts rows; the rowmap the checks need is the writer's, so build it the writer's way
        pairs = sorted(zip(t.frame.itertuples(index=False, name=None), t.final, strict=True))
        return pd.DataFrame({"protected_row": [str(i) for i in range(len(pairs))],
                             "original_record_id": [k for _, k in pairs]}, dtype=str)

    return {
        "k": 5,
        "source": {"ed_visits": src_visits, "lab_results": src_labs},
        "rowmaps": {"ed_visits": rowmap(visits), "lab_results": rowmap(labs)},
        "record_keys": {"ed_visits": "visit_key", "lab_results": "lab_key"},
        "person": {"table": "ed_visits", "column": "patient_id"},
        "joins": [{"table": "lab_results", "column": "visit_key", "ref_table": "ed_visits",
                   "ref_column": "visit_key"}],
        "identifiers": [{"table": "ed_visits", "column": "patient_id"},
                        {"table": "ed_visits", "column": "patient_name"}],
        "keys": [fx.FIXTURE_MASTER_KEY],
    }


def main(out: str) -> int:
    cand = make_candidate()
    res = write_release(cand, Path(out), MASTER, context=producer_context(cand))
    print(f"status={res.status} reasons={len(res.reasons)}")
    for r in res.reasons:
        print(f"  {r}")
    for folder in (res.out, res.scoring):
        if folder.exists():
            print(f"{folder.name}/: " + ", ".join(sorted(p.name for p in folder.iterdir())))
    return 0 if res.status == "released" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
