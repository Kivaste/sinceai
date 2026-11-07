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

# Floors set from the first full measurement (micro P 0.9986, R 0.9932), with headroom.
MICRO_RECALL_FLOOR = 0.985
MICRO_PRECISION_FLOOR = 0.995
CS_S1_TARGETS_RECALL_FLOOR = {"NATIONAL_ID": 0.99, "PAYMENT_CARD": 0.99, "IBAN": 0.99, "SECRET": 0.90}


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
    assert sc["micro"]["recall"] >= MICRO_RECALL_FLOOR
    assert sc["micro"]["precision"] >= MICRO_PRECISION_FLOOR
    for label, floor in CS_S1_TARGETS_RECALL_FLOOR.items():
        assert sc["per_label"][label]["recall"] >= floor, label
