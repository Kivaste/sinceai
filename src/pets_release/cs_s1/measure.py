"""CS-S1 redaction measurement for the manifest: exact-match scores on the template-held-out split (ticket 14's
harness pieces). Purpose checks are ``run.purpose`` (#60). Aggregates only; nothing here returns a row value."""
from __future__ import annotations

import math
from pathlib import Path

from pets_release.manifest import not_measured

GOLD = Path("metadata") / "pii_spans" / "customer_service__turns__text.jsonl"
RESIDUAL_LABELS = ("PERSON", "ADDRESS", "LOCATION", "ORG", "DATE", "AGE")


def _num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


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
                "summary": sorted(summary, key=lambda s: s["metric"])}
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
    risks += _target_risks(by, sc, len(held))
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


TARGET_LABELS = ("IBAN", "NATIONAL_ID", "PAYMENT_CARD", "SECRET")  # spec #1 CS-S1: recall >= 0.98 each
TARGET_RECALL = 0.98
_HOLDOUT = ("exact-match on the template-held-out split at turn level (skeleton hash, 20%; the accepted "
            "ticket 14 deviation from conversation level)")


# D45 (human decision): the held-out SECRET figure after the misspelled-cue rule is optimistic, because the two
# held-out misses informed that rule. Stated in every release; the target is never lowered or hidden.
_SECRET_DISCLOSURE = ("Before the misspelled-cue redactor rule (ticket 23 round 5) held-out recall was 15/17 "
                      "(0.8824). The two held-out misses informed that rule (held-out contamination), so any "
                      "later held-out figure is optimistic and the target is not shown to be met on untouched data.")


def _target_risks(by: dict, sc: dict, n_held: int) -> list[dict]:
    """Per-label held-out recall of every CS-S1 target label against the spec floor, and SECRET precision; each
    stated on its own, never only as the combined figure (Sol r1 Spec)."""
    den = {"unit": "turns", "n": n_held}
    out = []
    for lab in TARGET_LABELS:
        e = by.get(lab)
        rid = f"target-recall-{lab.lower().replace('_', '-')}"
        if not e or not e["support"] or e["recall"] is None:
            rate = not_measured("no held-out gold spans for this label")
            verdict = f"not measured against the spec floor {TARGET_RECALL}"
        else:
            rate = {"status": "measured", "value": e["recall"], "denominator": den,
                    "source": "redactor spans vs kit gold, " + _HOLDOUT}
            verdict = (f"{e['tp']}/{e['support']} held-out spans, "
                       + ("meets" if e["recall"] >= TARGET_RECALL else "BELOW") + f" the spec floor {TARGET_RECALL}")
        desc = f"{lab} recall: {verdict}; {_HOLDOUT}"
        if lab == "SECRET":
            desc = (f"SECRET recall: unmet target (spec floor {TARGET_RECALL}). {_SECRET_DISCLOSURE} This run: "
                    f"{verdict}; exact-match, template-held-out split at turn level (accepted ticket 14 deviation)")
            if len(desc) > 500:
                raise ValueError("SECRET target note longer than the manifest text limit")
        out.append({"risk": rid, "kind": "note", "label": lab, "rate": rate, "description": desc})
    sec = sc["cs_s1_target"]["per_label"].get("SECRET", {})
    p = _num(sec.get("precision"))
    out.append({"risk": "target-precision-secret", "kind": "note", "label": "SECRET",
                "rate": not_measured("no held-out SECRET predictions") if p is None else
                {"status": "measured", "value": p, "denominator": den,
                 "source": "redactor spans vs kit gold, " + _HOLDOUT},
                "description": "SECRET precision: over-redaction of gate-flagged cue spans (the #92 cross-turn step "
                               "and gate-following cue rules) is the accepted privacy-safe cost; " + _HOLDOUT})
    return out


def _risk(label, rate) -> dict:
    return {"risk": f"text-recall-{label.lower()}", "kind": "text_recall", "label": label, "rate": rate,
            "description": f"{label} in redacted turns is a residual risk (no export assertion); exact-match "
                           "recall on the template-held-out split"}
