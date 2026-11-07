"""python -m pets_release.redaction_eval --kit <root> [--precision-floor F] [--out DIR]
Exit 0 only when the floor is set and met; 1 when below it (or precision unknown); 2 when no floor is set
(unknown is not a pass) unless --report-only, which exits 0 and claims no pass."""
from __future__ import annotations

import argparse
import json

from pets_release.offline import entry_point

from .harness import evaluate_frames, headline, load_frames
from .predictors import regex_predictor


@entry_point
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--precision-floor", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--report-only", action="store_true",
                    help="measure and print without a floor; exits 0 and claims no pass")
    a = ap.parse_args(argv)
    frame, notes = load_frames(a.kit)
    rep = evaluate_frames(frame, notes, lambda dev: regex_predictor,
                          precision_floor=a.precision_floor, out_dir=a.out)
    print(json.dumps({"split_mode": rep["split_mode"], "split": rep["split"],
                      "precision_floor": rep["precision_floor"], "headline": headline(rep)}, sort_keys=True))
    if rep["passed"] is None:  # floor unset: unknown, never a pass
        return 0 if a.report_only else 2
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
