"""Harness: frame -> predictor -> aggregate-only report (+ local spot-check sheet)."""
from __future__ import annotations

import json
from pathlib import Path

from .frame import load_clinical_notes_frame, load_cs_frame
from .scoring import person_twice, score_frame
from .split import split_by_skeleton
from .spotcheck import export_spot_check


def predict_all(frame, predictor) -> dict:
    return {tid: predictor(text) for tid, text in sorted(frame.texts.items())}


def run_harness(kit_root, predictor, out_dir=None, repo_root=None, person_variants=None, sheet_n=200) -> dict:
    """person_variants: optional {'controller_gazetteer': predictor, 'dev_only_lexicon': predictor}."""
    frame = load_cs_frame(kit_root)
    pred = predict_all(frame, predictor)
    split = split_by_skeleton(frame, mode="turn")
    held = set(split.held_out_turns)
    report = {
        "frame": {"turns": len(frame.texts), "gold_spans": sum(len(v) for v in frame.gold.values()),
                  "gold_absent_turns": sum(1 for v in frame.gold.values() if not v)},
        "full_train": score_frame(frame.gold, pred),
        "split": split.summary(),
        "strict_conversation_split": split_by_skeleton(frame, mode="conversation").summary(),
        "held_out": score_frame({k: frame.gold[k] for k in held}, {k: pred[k] for k in held}),
    }
    if person_variants:
        a = predict_all(frame, person_variants["controller_gazetteer"])
        b = predict_all(frame, person_variants["dev_only_lexicon"])
        report["person_twice_held_out"] = person_twice(frame.gold, a, b, held)
    notes = load_clinical_notes_frame(kit_root)
    report["zero_shot_clinical_notes"] = score_frame(notes.gold, predict_all(notes, predictor))
    if out_dir is not None:
        sheet = export_spot_check(frame, pred, Path(out_dir) / "spot_check.csv", n=sheet_n,
                                  repo_root=repo_root, ids=sorted(held) or None)
        report["spot_check_rows"] = min(sheet_n, len(held) or len(frame.texts))
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def headline(report: dict) -> dict:
    """The three numbers per section, with per-label support."""
    out = {}
    for sec in ("full_train", "held_out", "zero_shot_clinical_notes"):
        r = report[sec]
        out[sec] = {
            "micro_f2_all": {"f2": r["micro_f2_all"]["f2"], "precision": r["micro_f2_all"]["precision"],
                             "recall": r["micro_f2_all"]["recall"], "support": r["micro_f2_all"]["support"]},
            "identifying_micro": {"f2": r["identifying_micro"]["f2"],
                                  "precision": r["identifying_micro"]["precision"],
                                  "recall": r["identifying_micro"]["recall"],
                                  "support": r["identifying_micro"]["support"]},
            "cs_s1_target": {"recall": r["cs_s1_target"]["recall"], "support": r["cs_s1_target"]["support"],
                             "health_hits": r["cs_s1_target"]["health_hits"],
                             "health_support": r["cs_s1_target"]["health_support"]},
        }
    return out
