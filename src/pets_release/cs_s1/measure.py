"""CS-S1 measurements for the manifest: purpose checks before/after (CS-U5 twice when turn_id is a
pseudonym) and exact-match redaction scores on the template-held-out split (ticket 14's harness pieces).
Aggregates only; nothing here returns a row value."""
from __future__ import annotations

import math
from pathlib import Path

from pets_release.cs_s1.lineage import restore_turn_ids
from pets_release.manifest import not_measured

GOLD = Path("metadata") / "pii_spans" / "customer_service__turns__text.jsonl"
RESIDUAL_LABELS = ("PERSON", "ADDRESS", "LOCATION", "ORG", "DATE", "AGE")
ADAPTED = "CS-U5.lineage-adapted"
UTILITY_SOURCE = "pets-eval utility tasks in-process via the kiteval adapter (original vs original = before)"


def _num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def utility(scenario_id, source, protected, rowmap_turns, *, root) -> tuple[dict, dict]:
    """(measured.utility block, {task: {before, after, status}}). ``rowmap_turns``: row map of the
    released turns when turn_id is a pseudonym (adds the separately labelled lineage-adapted CS-U5)."""
    from pets_release.kiteval import purpose_check, purpose_checks

    orig = {k: source[k] for k in ("conversations", "turns")}
    before = {r["id"]: r for r in purpose_checks(scenario_id, orig, orig, root=root)}
    after = {r["id"]: r for r in purpose_checks(scenario_id, orig, protected, root=root)}
    tasks = []
    for tid in sorted(after):
        a, b = after[tid], before.get(tid, {})
        status = a["status"] if a["status"] in ("ok", "not_answerable") else "error"
        tasks.append({"task": tid, "status": status, "before": _num(b.get("score")), "after": _num(a.get("score"))})
    if rowmap_turns is not None:
        adapted_prot = dict(protected, turns=restore_turn_ids(protected["turns"], rowmap_turns))
        a = purpose_check("CS-U5", orig, adapted_prot)
        status = a["status"] if a["status"] in ("ok", "not_answerable") else "error"
        tasks.append({"task": ADAPTED, "status": status, "before": _num(before.get("CS-U5", {}).get("score")),
                      "after": _num(a.get("score"))})
    tasks.sort(key=lambda t: t["task"])
    block = {"status": "measured", "source": UTILITY_SOURCE, "tasks": tasks}
    return block, {t["task"]: {k: t[k] for k in ("status", "before", "after")} for t in tasks}


def _pred(spans) -> dict:
    out: dict = {}
    for s in spans:
        out.setdefault(s["record_id"], []).append({"start": s["start"], "end": s["end"], "label": s["label"]})
    return out


def redaction(kit_root, spans) -> dict:
    """{"measured", "risks", "frame", "pred", "held", "report"}; ``measured`` is not_measured when the
    kit has no gold spans."""
    from pets_release.redaction_eval import load_cs_frame, score_frame, split_by_skeleton
    from pets_release.redaction_eval.scoring import exact_scores

    root = Path(kit_root)
    if not (root / GOLD).is_file():
        reason = "no gold spans in the kit for customer_service turns"
        risks = [_risk(lab, not_measured(reason)) for lab in RESIDUAL_LABELS]
        return {"measured": not_measured(reason), "risks": risks, "frame": None, "pred": None, "held": (),
                "report": {"status": "not_measured", "reason": reason}}
    frame = load_cs_frame(root)
    pred_all = _pred(spans)
    pred = {tid: pred_all.get(tid, []) for tid in frame.texts}
    split = split_by_skeleton(frame, mode="turn")
    held = tuple(sorted(split.held_out_turns))
    gold_h = {k: frame.gold[k] for k in held}
    pred_h = {k: pred[k] for k in held}
    per = exact_scores(gold_h, pred_h)["per_label"]
    sc = score_frame(gold_h, pred_h)
    full = score_frame(frame.gold, pred)
    support = sc["micro_f2_all"]["support"]
    labels = [{"label": lab, "support": int(support.get(lab, 0)), "tp": int(v["tp"]), "fp": int(v["fp"]),
               "fn": int(v["fn"]), "precision": _num(v["precision"]), "recall": _num(v["recall"])}
              for lab, v in sorted(per.items())]
    summary = [
        {"metric": "heldout.turns", "value": float(len(held))},
        {"metric": "heldout.micro.precision", "value": _num(sc["micro_f2_all"]["precision"])},
        {"metric": "heldout.micro.recall", "value": _num(sc["micro_f2_all"]["recall"])},
        {"metric": "heldout.micro.f2", "value": _num(sc["micro_f2_all"]["f2"])},
        {"metric": "heldout.identifying.recall", "value": _num(sc["identifying_micro"]["recall"])},
        {"metric": "heldout.cs_s1_target.recall", "value": _num(sc["cs_s1_target"]["recall"])},
        {"metric": "heldout.health.hits", "value": float(sc["cs_s1_target"]["health_hits"])},
        {"metric": "heldout.health.support", "value": float(sc["cs_s1_target"]["health_support"])},
        {"metric": "fulltrain.micro.recall", "value": _num(full["micro_f2_all"]["recall"])},
        {"metric": "fulltrain.micro.precision", "value": _num(full["micro_f2_all"]["precision"])},
    ]
    measured = {"status": "measured", "source": "redactor spans vs kit gold, pets_eval.text.span_scores exact",
                "mode": "exact", "frame": "all train turns; gold-absent turns count as empty",
                "split": "template-held-out (skeleton hash, 20%, turn level); scores on held-out turns",
                "labels": labels or [{"label": "PERSON", "support": 0, "tp": 0, "fp": 0, "fn": 0,
                                      "precision": None, "recall": None}],
                "summary": summary}
    by = {lab["label"]: lab for lab in labels}
    risks = []
    for lab in RESIDUAL_LABELS:
        e = by.get(lab)
        if not e or not e["support"] or e["recall"] is None:
            risks.append(_risk(lab, not_measured("no held-out gold spans for this label")))
        else:
            risks.append(_risk(lab, {"status": "measured", "value": e["recall"],
                                     "denominator": {"unit": "turns", "n": len(held)},
                                     "source": "exact-match recall on template-held-out train turns"}))
    report = _clean({"status": "measured", "split": split.summary(), "held_out": sc, "full_train": full})
    return {"measured": measured, "risks": risks, "frame": frame, "pred": pred, "held": held, "report": report}


def _clean(v):
    """JSON-safe copy for canonical bytes: NaN/inf -> None, tuples -> lists, numpy scalars -> Python."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, int):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return int(f) if float(f).is_integer() and not isinstance(v, float) else f


def _risk(label, rate) -> dict:
    return {"risk": f"text-recall-{label.lower()}", "kind": "text_recall", "label": label, "rate": rate,
            "description": f"{label} in redacted turns is a residual risk (no export assertion); exact-match "
                           "recall on the template-held-out split"}
