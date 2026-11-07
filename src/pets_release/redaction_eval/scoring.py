"""Exact-match scoring pinned to pets_eval.text.span_scores(mode="exact").

Frame = all train turns; gold-absent turns are empty so predictions there are false positives.
Note: the CS utility module's span_scores defaults to overlap and untyped; do not use it here.
"""
from __future__ import annotations

CS_S1_TARGET_LABELS = ("NATIONAL_ID", "PAYMENT_CARD", "IBAN", "SECRET")


def _pets_eval_text():
    from pets_eval import text  # the one pinned scorer

    return text


def exact_scores(gold: dict, pred: dict, labels=None) -> dict:
    return _pets_eval_text().span_scores(gold, pred, mode="exact", labels=labels)


def _support(gold: dict, labels=None) -> dict:
    out: dict = {}
    for spans in gold.values():
        for s in spans:
            if labels is None or s["label"] in labels:
                out[s["label"]] = out.get(s["label"], 0) + 1
    return dict(sorted(out.items()))


def _micro_block(gold, pred, labels=None) -> dict:
    r = exact_scores(gold, pred, labels)
    m = r["micro"]
    return {
        "precision": m["precision"],
        "recall": m["recall"],
        "f1": m["f1"],
        "f2": m["f2"],
        "tp": m["tp"],
        "fp": m["fp"],
        "fn": m["fn"],
        "support": _support(gold, labels),
        "per_label": {k: {"precision": v["precision"], "recall": v["recall"], "f2": v["f2"]}
                      for k, v in r["per_label"].items()},
    }


def score_frame(gold: dict, pred: dict) -> dict:
    """Three reported numbers, each with per-label support. Aggregate only."""
    ident = _pets_eval_text().IDENTIFYING
    target = _micro_block(gold, pred, set(CS_S1_TARGET_LABELS))
    target["support"] = {lab: _support(gold, {lab}).get(lab, 0) for lab in CS_S1_TARGET_LABELS}
    health = exact_scores(gold, pred, {"HEALTH"})["per_label"].get("HEALTH", {"tp": 0, "fn": 0})
    target["health_hits"] = health["tp"]
    target["health_support"] = health["tp"] + health["fn"]
    return {
        "mode": "exact",
        "n_records": len(gold),
        "micro_f2_all": _micro_block(gold, pred),
        "identifying_micro": _micro_block(gold, pred, set(ident)),
        "cs_s1_target": target,
    }


def person_twice(gold: dict, pred_gazetteer: dict, pred_dev_lexicon: dict, ids) -> dict:
    """PERSON exact-match reported twice over `ids` (normally the held-out turns)."""
    ids = set(ids)
    g = {k: v for k, v in gold.items() if k in ids}
    out = {}
    for name, pred in (("controller_gazetteer", pred_gazetteer), ("dev_only_lexicon", pred_dev_lexicon)):
        p = {k: v for k, v in pred.items() if k in ids}
        b = _micro_block(g, p, {"PERSON"})
        out[name] = {"precision": b["precision"], "recall": b["recall"], "f2": b["f2"],
                     "support": b["support"].get("PERSON", 0)}
    return out


def check_precision_floor(scores: dict, floor: float) -> bool:
    """Fail closed: a missing precision is a fail."""
    try:
        return float(scores["micro_f2_all"]["precision"]) >= floor
    except (KeyError, TypeError, ValueError):
        return False
