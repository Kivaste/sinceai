"""Real-kit regression floor for the structured labels (marked ``kit``; skipped = not run).

Frame: all customer_service train turns; gold-absent turns count as empty; exact match via
``pets_eval.text.span_scores(mode="exact")``. Asserts aggregates only and never prints values.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from pets_release.redactor import (
    STRUCTURED_LABELS,
    StructuredPass,
    Turn,
    redact_conversation,
)

KIT = os.environ.get("PETS_KIT")
pytestmark = [pytest.mark.kit, pytest.mark.skipif(not KIT, reason="PETS_KIT not set: kit test NOT RUN")]

# REGRESSION GUARD, not the policy target. The CS-S1 privacy targets (recall 0.98 on NATIONAL_ID,
# PAYMENT_CARD, IBAN, SECRET) are evaluated on the held-out split in ticket 23 and handled by policy.
# Floors = value measured at the review-r2 head on the full train frame, minus a margin: 0.005 for
# labels with >= 100 gold spans, 0.04 for smaller ones (one miss moves those by 0.016-0.037).
# Measured (precision, recall): see the ticket 12 done-report.
MEASURED = {  # label: (precision, recall, gold support)
    "ACCOUNT_NUMBER": (0.9995, 0.9967, 3967),
    "DEVICE_ID": (0.9983, 1.0000, 572),
    "EMAIL": (0.9995, 1.0000, 1999),
    "IBAN": (1.0000, 1.0000, 1473),
    "IP_ADDRESS": (1.0000, 1.0000, 356),
    "LICENSE_PLATE": (1.0000, 1.0000, 27),
    "NATIONAL_ID": (1.0000, 1.0000, 5120),
    "PAYMENT_CARD": (0.9965, 0.9988, 856),
    "PHONE": (0.9988, 0.9825, 4217),
    "PROPERTY_ID": (1.0000, 1.0000, 103),
    "SECRET": (0.9807, 0.9807, 466),
    "URL": (1.0000, 1.0000, 440),
    "USERNAME": (1.0000, 0.9839, 62),
}
MICRO_MEASURED = (0.9989, 0.9950)
MICRO_MARGIN = 0.003


def _margin(support: int) -> float:
    return 0.005 if support >= 100 else 0.04


def _load():
    import pandas as pd

    root = Path(KIT)
    sys.path.insert(0, str(root / "toolkit"))
    from pets_eval.text import span_scores

    turns = pd.read_csv(root / "data/customer_service/turns.csv", dtype=str, keep_default_na=False)
    conv = pd.read_csv(root / "data/customer_service/conversations.csv", dtype=str, keep_default_na=False)
    train = set(conv.loc[conv["split"] == "train", "conversation_id"])
    tt = turns[turns["conversation_id"].isin(train)].copy()
    tt["_seq"] = tt["seq"].astype(int)
    tt = tt.sort_values(["conversation_id", "_seq", "turn_id"])
    frame = set(tt["turn_id"])
    gold = {k: [] for k in frame}
    with open(root / "metadata/pii_spans/customer_service__turns__text.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["record_id"] in frame:
                gold[r["record_id"]] = [{"start": s["start"], "end": s["end"], "label": s["label"]} for s in r["spans"]]
    return tt, frame, gold, span_scores


def test_structured_labels_exact_match_floor():
    tt, frame, gold, span_scores = _load()
    pred = {k: [] for k in frame}
    sp = StructuredPass()
    for cid, g in tt.groupby("conversation_id", sort=True):
        ts = [Turn(a, b, c, d) for a, b, c, d in zip(g["turn_id"], g["text"], g["speaker"], g["seq"])]
        for s in redact_conversation(cid, ts, passes=[sp]).spans:
            pred[s["record_id"]].append({"start": s["start"], "end": s["end"], "label": s["label"]})
    sc = span_scores(gold, pred, mode="exact", labels=STRUCTURED_LABELS)
    assert sc["mode"] == "exact"
    assert set(MEASURED) == set(STRUCTURED_LABELS)
    assert sc["micro"]["precision"] >= MICRO_MEASURED[0] - MICRO_MARGIN
    assert sc["micro"]["recall"] >= MICRO_MEASURED[1] - MICRO_MARGIN
    for label, (p, r, support) in MEASURED.items():
        got = sc["per_label"][label]
        assert got["tp"] + got["fn"] == support, label  # same frame as the measurement
        assert got["precision"] >= p - _margin(support), f"{label} precision"
        assert got["recall"] >= r - _margin(support), f"{label} recall"
