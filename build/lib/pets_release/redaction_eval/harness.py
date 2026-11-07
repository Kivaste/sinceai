"""Harness: frame -> dev-fitted predictor -> aggregate-only report (+ local spot-check sheet)."""
from __future__ import annotations

import json
from pathlib import Path

from .frame import load_clinical_notes_frame, load_cs_frame, subset
from .scoring import check_precision_floor, person_twice, score_frame
from .split import split_by_skeleton
from .spotcheck import export_spot_check

SPLIT_MODE = "turn"
SPLIT_NOTE = ("Turn-level template-held-out split: a turn is held out iff its skeleton hash is held out. "
              "The spec's strict conversation rule holds out 0 conversations on the real kit "
              "(see strict_conversation_split); conversations may therefore straddle the partitions.")
PERSON_VARIANTS = ("controller_gazetteer", "dev_lexicon")


def predict_all(frame, predictor) -> dict:
    return {tid: predictor(text) for tid, text in sorted(frame.texts.items())}


def _person_section(frame, split, held, dev_frame, person_variants):
    have = person_variants or {}
    missing = [v for v in PERSON_VARIANTS if v not in have]
    if missing:
        return {"status": "not_measured",
                "reason": "missing named variant(s): " + ", ".join(missing)}
    preds = [predict_all(frame, have[v](dev_frame)) for v in PERSON_VARIANTS]
    out = person_twice(frame.gold, preds[0], preds[1], held)
    out["status"] = "measured"
    out["variants"] = list(PERSON_VARIANTS)
    return out


def evaluate_frames(frame, notes, make_predictor, precision_floor=None, person_variants=None,
                    out_dir=None, repo_root=None, sheet_n=200) -> dict:
    """make_predictor(dev_frame) -> predictor(text) -> spans. It receives development turns only;
    held-out turns are never passed to it. person_variants: {'controller_gazetteer': factory,
    'dev_lexicon': factory}, factories with the same signature."""
    split = split_by_skeleton(frame, mode=SPLIT_MODE)
    held = set(split.held_out_turns)
    dev_frame = subset(frame, split.dev_turns)
    predictor = make_predictor(dev_frame)
    pred = predict_all(frame, predictor)
    dev_convs = {frame.conversation_of[t] for t in split.dev_turns}
    held_convs = {frame.conversation_of[t] for t in held}
    report = {
        "split_mode": SPLIT_MODE,
        "split_note": SPLIT_NOTE,
        "conversations_in_both_partitions": len(dev_convs & held_convs),
        "frame": {"turns": len(frame.texts), "gold_spans": sum(len(v) for v in frame.gold.values()),
                  "gold_absent_turns": sum(1 for v in frame.gold.values() if not v)},
        "full_train": score_frame(frame.gold, pred),
        "split": split.summary(),
        "strict_conversation_split": split_by_skeleton(frame, mode="conversation").summary(),
        "held_out": score_frame({k: frame.gold[k] for k in held}, {k: pred[k] for k in held}),
        "person_twice_held_out": _person_section(frame, split, held, dev_frame, person_variants),
        "zero_shot_frame": {"notes": len(notes.texts), "gold_dropped": dict(notes.gold_dropped)},
        "zero_shot_clinical_notes": score_frame(notes.gold, predict_all(notes, predictor)),
    }
    if precision_floor is None:
        report["precision_floor"] = {"status": "not_set"}
        report["passed"] = None  # unknown is not a pass; callers must not read None as success
    else:
        ok = check_precision_floor(report["held_out"], precision_floor)
        report["precision_floor"] = {
            "status": "pass" if ok else "fail", "floor": precision_floor,
            "precision": report["held_out"]["micro_f2_all"].get("precision"),
        }
        report["passed"] = ok
    if out_dir is not None:
        report["spot_check_rows"] = export_spot_check(
            frame, pred, Path(out_dir) / "spot_check.csv", n=sheet_n,
            repo_root=repo_root, ids=sorted(held) or None)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def load_frames(kit_root):
    return load_cs_frame(kit_root), load_clinical_notes_frame(kit_root)


def run_harness(kit_root, make_predictor, **kw) -> dict:
    frame, notes = load_frames(kit_root)
    return evaluate_frames(frame, notes, make_predictor, **kw)


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
