"""python -m pets_release.redaction_eval --kit <root> [--predictor production|regex-baseline]
                                     [--precision-floor F] [--out DIR] [--report-only]
The default predictor is the shipped redactor (``redact_conversation`` with the shipped passes, lexicon
gazetteer fitted on development names only); ``regex-baseline`` is a trivial non-product baseline.
Exit 0 only when the floor is set and met; 1 when below it (or precision unknown); 2 when no floor is set
(unknown is not a pass) unless --report-only, which exits 0 and claims no pass."""
from __future__ import annotations

import argparse
import json

from pets_release.offline import entry_point

from . import production
from .harness import evaluate_frames, headline, load_frames
from .predictors import regex_predictor

BASELINE_NOTE = "regex baseline: a trivial non-product predictor; these numbers say nothing about the shipped redactor"


def _predictor(mode, kit):
    if mode == "regex-baseline":
        return (lambda dev: regex_predictor), None, {"mode": mode, "note": BASELINE_NOTE}
    info = {"mode": "production", "entry_point": production.ENTRY_POINT,
            "passes": [p.name for p in production.shipped_passes()],
            "lexicon_fitting": "gazetteer from development gold PERSON spans only"}
    return production.production_factory, production.person_variants(kit), info


@entry_point
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--predictor", choices=("production", "regex-baseline"), default="production")
    ap.add_argument("--precision-floor", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--report-only", action="store_true",
                    help="measure and print without a floor; exits 0 and claims no pass")
    a = ap.parse_args(argv)
    frame, notes = load_frames(a.kit)
    factory, variants, info = _predictor(a.predictor, a.kit)
    rep = evaluate_frames(frame, notes, factory, precision_floor=a.precision_floor, out_dir=a.out,
                          person_variants=variants, predictor_info=info)
    print(json.dumps({"predictor": info, "split_mode": rep["split_mode"], "split": rep["split"],
                      "precision_floor": rep["precision_floor"], "headline": headline(rep),
                      "person_twice_held_out": rep["person_twice_held_out"],
                      "turn_held_out": {k: rep["turn_held_out"][k] for k in (
                          "split_mode", "note", "satisfies_spec_conversation_boundary", "split",
                          "conversations_in_both_partitions")}}, sort_keys=True))
    if rep["passed"] is None:  # floor unset: unknown, never a pass
        return 0 if a.report_only else 2
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
