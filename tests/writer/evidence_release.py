"""Evidence run: write a release from 02's fixture candidate with the REAL check registry (no stand-ins).

    python tests/writer/evidence_release.py <out_dir>

A synthetic mini kit is written to ``<out_dir>.kit`` (source tables matching the fixture lineage; one withheld
table). Producer-scope checks (ticket 11) get the matching synthetic context. Prints aggregates only (status,
reason codes, file names). Exit 0 released, 1 refused.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from writer_helpers import MASTER, make_candidate, make_kit, producer_context

from pets_release.writer import write_release


def main(out: str) -> int:
    cand = make_candidate()
    out_p = Path(out)
    kit = make_kit(out_p.with_name(out_p.name + ".kit"), cand)
    res = write_release(cand, out_p, MASTER, kit, context=producer_context(cand))
    print(f"status={res.status} reasons={len(res.reasons)}")
    for r in res.reasons:
        print(f"  {r}")
    for folder in (res.out, res.scoring):
        if folder.exists():
            print(f"{folder.name}/: " + ", ".join(sorted(p.name for p in folder.iterdir())))
    return 0 if res.status == "released" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
