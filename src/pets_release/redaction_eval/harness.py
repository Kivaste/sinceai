"""Harness: frame -> dev-fitted predictor -> aggregate-only report (+ local spot-check sheet)."""
from __future__ import annotations

import json
from pathlib import Path

from .frame import load_clinical_notes_frame, load_cs_frame, subset
from .scoring import check_precision_floor, person_twice, score_frame
from .split import split_by_skeleton
from .spotcheck import export_spot_check

SPLIT_MODE = "conversation"
SPLIT_NOTE = ("Conversation-level template-held-out split (spec): whole conversations are held out and no "
              "skeleton of a held-out conversation occurs in development. Built by holding out whole skeleton "
              "components (conversations linked by a shared skeleton) up to 20% of skeleton hashes. "
              "An empty held-out frame is reported as unavailable, never replaced by the turn split.")
TURN_NOTE = ("Turn-level relaxation, for comparison only: a turn is held out iff its skeleton hash is held out, "
             "so conversations straddle the partitions. Does not satisfy the spec's conversation boundary and "
             "is never used for the precision floor.")
PERSON_VARIANTS = ("controller_gazetteer", "dev_lexicon")


def predict_all(frame, predictor) -> dict:
    """Text predictors see one turn; conversation-level predictors (the shipped redactor) see each
    conversation of the frame as one unit, turns in seq order."""
    if not getattr(predictor, "conversation_level", False):
        return {tid: predictor(text) for tid, text in sorted(frame.texts.items())}
    from .production import as_turns

    by_conv: dict = {}
    for tid in frame.texts:
        by_conv.setdefault(frame.conversation_of[tid], []).append(tid)
    out: dict = {}
    for cid in sorted(by_conv):
        out.update(predictor.predict(cid, as_turns(frame, by_conv[cid])))
    return dict(sorted(out.items()))


def _person_section(frame, split, held, dev_frame, person_variants):
    have = person_variants or {}
    missing = [v for v in PERSON_VARIANTS if v not in have]
    if missing:
        return {"status": "not_measured",
                "reason": "missing named variant(s): " + ", ".join(missing)}
    convs = {frame.conversation_of[t] for t in held}
    scope = subset(frame, [t for t in frame.texts if frame.conversation_of[t] in convs])  # whole conversations
    preds = [predict_all(scope, have[v](dev_frame)) for v in PERSON_VARIANTS]
    out = person_twice(frame.gold, preds[0], preds[1], held)
    out["status"] = "measured"
    out["variants"] = list(PERSON_VARIANTS)
    return out


def _straddling(frame, split) -> int:
    dev = {frame.conversation_of[t] for t in split.dev_turns}
    return len(dev & {frame.conversation_of[t] for t in split.held_out_turns})


def _conversations_of(frame, ids):
    convs = {frame.conversation_of[t] for t in ids}
    return subset(frame, [t for t in frame.texts if frame.conversation_of[t] in convs])


def _turn_section(frame, make_predictor) -> dict:
    split = split_by_skeleton(frame, mode="turn")
    held = set(split.held_out_turns)
    predictor = make_predictor(subset(frame, split.dev_turns))
    pred = predict_all(_conversations_of(frame, held), predictor)  # whole conversations, for cross-turn context
    return {
        "split_mode": "turn",
        "note": TURN_NOTE,
        "satisfies_spec_conversation_boundary": False,
        "split": split.summary(),
        "conversations_in_both_partitions": _straddling(frame, split),
        "scores": score_frame({k: frame.gold[k] for k in held}, {k: pred[k] for k in held}),
    }


def evaluate_frames(frame, notes, make_predictor, precision_floor=None, person_variants=None,
                    out_dir=None, repo_root=None, sheet_n=200, predictor_info=None) -> dict:
    """make_predictor(dev_frame) -> predictor. It receives development turns only; held-out turns are never
    passed to it. It is called once per split (conversation split, then the labelled turn relaxation).
    person_variants: {'controller_gazetteer': factory, 'dev_lexicon': factory}, same signature."""
    split = split_by_skeleton(frame, mode=SPLIT_MODE)
    held = set(split.held_out_turns)
    dev_frame = subset(frame, split.dev_turns)
    predictor = make_predictor(dev_frame)
    pred = predict_all(frame, predictor)
    summary = split.summary()
    summary["conversations_in_both_partitions"] = _straddling(frame, split)
    if held:
        held_scores = score_frame({k: frame.gold[k] for k in held}, {k: pred[k] for k in held})
        person = _person_section(frame, split, held, dev_frame, person_variants)
    else:
        reason = "the conversation-level held-out frame is empty on this input"
        held_scores = {"status": "unavailable", "reason": reason}
        person = {"status": "not_measured", "reason": reason}
    report = {
        "predictor": predictor_info or {"mode": "caller-supplied"},
        "split_mode": SPLIT_MODE,
        "split_note": SPLIT_NOTE,
        "frame": {"turns": len(frame.texts), "gold_spans": sum(len(v) for v in frame.gold.values()),
                  "gold_absent_turns": sum(1 for v in frame.gold.values() if not v)},
        "full_train": score_frame(frame.gold, pred),
        "split": summary,
        "held_out": held_scores,
        "turn_held_out": _turn_section(frame, make_predictor),
        "person_twice_held_out": person,
        "zero_shot_frame": {"notes": len(notes.texts), "gold_dropped": dict(notes.gold_dropped)},
        "zero_shot_clinical_notes": score_frame(notes.gold, predict_all(notes, predictor)),
    }
    if precision_floor is None:
        report["precision_floor"] = {"status": "not_set"}
        report["passed"] = None  # unknown is not a pass; callers must not read None as success
    elif not held:
        report["precision_floor"] = {"status": "unavailable", "floor": precision_floor,
                                     "reason": held_scores["reason"]}
        report["passed"] = False  # an empty held-out frame is not a pass; the turn split never substitutes
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


def _three(r: dict) -> dict:
    if r.get("status") == "unavailable":
        return {"status": "unavailable", "reason": r["reason"]}
    return {
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


def headline(report: dict) -> dict:
    """The three numbers per section, with per-label support. `turn_held_out` is the labelled turn-level
    relaxation and is not the held-out result."""
    out = {sec: _three(report[sec]) for sec in ("full_train", "held_out", "zero_shot_clinical_notes")}
    out["turn_held_out"] = _three(report["turn_held_out"]["scores"])
    return out
