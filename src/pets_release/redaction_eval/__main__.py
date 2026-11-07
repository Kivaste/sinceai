"""python -m pets_release.redaction_eval --kit <root> [--precision-floor F] [--out DIR]
Exit 1 when the precision floor is set and the held-out precision is below it (or unknown)."""
from __future__ import annotations

import argparse
import json

from .harness import evaluate_frames, headline, load_frames
from .predictors import regex_predictor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--precision-floor", type=float, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    frame, notes = load_frames(a.kit)
    rep = evaluate_frames(frame, notes, lambda dev: regex_predictor,
                          precision_floor=a.precision_floor, out_dir=a.out)
    print(json.dumps({"split_mode": rep["split_mode"], "split": rep["split"],
                      "precision_floor": rep["precision_floor"], "headline": headline(rep)}, sort_keys=True))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
