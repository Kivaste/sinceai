"""Evaluation frame: all train turns; gold-absent turns count as empty."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Frame:
    texts: dict  # record_id -> untouched text
    gold: dict  # record_id -> list of {start,end,label}; [] when gold-absent
    conversation_of: dict = field(default_factory=dict)  # record_id -> conversation id


def build_frame(turns, conversations, gold, split: str = "train") -> Frame:
    """turns: iterable of {turn_id, conversation_id, text}; conversations: {conversation_id, split}."""
    keep = {c["conversation_id"] for c in conversations if c["split"] == split}
    texts, g, conv = {}, {}, {}
    for t in turns:
        if t["conversation_id"] not in keep:
            continue
        tid = t["turn_id"]
        texts[tid] = t["text"] if isinstance(t["text"], str) else ""
        g[tid] = [dict(s) for s in gold.get(tid, [])]
        conv[tid] = t["conversation_id"]
    return Frame(texts=texts, gold=g, conversation_of=conv)


def load_spans(path) -> dict:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["record_id"]] = [
                {"start": s["start"], "end": s["end"], "label": s["label"]} for s in r["spans"]
            ]
    return out


def load_cs_frame(kit_root) -> Frame:
    import pandas as pd

    root = Path(kit_root)
    turns = pd.read_csv(root / "data/customer_service/turns.csv", dtype=str, keep_default_na=False)
    convs = pd.read_csv(
        root / "data/customer_service/conversations.csv", dtype=str, usecols=["conversation_id", "split"]
    )
    gold = load_spans(root / "metadata/pii_spans/customer_service__turns__text.jsonl")
    return build_frame(turns.to_dict("records"), convs.to_dict("records"), gold)


def load_clinical_notes_frame(kit_root) -> Frame:
    """Zero-shot frame: every health clinical note (no train/dev role)."""
    import pandas as pd

    root = Path(kit_root)
    notes = pd.read_csv(root / "data/health/clinical_notes.csv", dtype=str, keep_default_na=False)
    gold = load_spans(root / "metadata/pii_spans/health__clinical_notes__note_text.jsonl")
    texts = dict(zip(notes["note_id"], notes["note_text"]))
    return Frame(
        texts=texts,
        gold={k: gold.get(k, []) for k in texts},
        conversation_of={k: k for k in texts},
    )


def subset(frame: Frame, ids) -> Frame:
    ids = [i for i in sorted(ids)]
    return Frame(
        texts={i: frame.texts[i] for i in ids},
        gold={i: frame.gold.get(i, []) for i in ids},
        conversation_of={i: frame.conversation_of[i] for i in ids},
    )
