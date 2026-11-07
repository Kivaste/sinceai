"""Redacted customer_service eval turns (``turn_id,text``) and detected spans (JSONL) for the organisers."""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence

from pets_release.kit import Kit, KitError
from pets_release.redactor import Turn, default_passes, redact_conversation
from pets_release.submission.errors import SubmissionRefused

DATASET = "customer_service"
TURN_COLUMNS = ("turn_id", "conversation_id", "seq", "text")
CONV_COLUMNS = ("conversation_id", "split")
EVAL_SPLIT = "eval"


def _seq(value: str) -> int:
    if not value.isascii() or not value.isdigit():
        raise SubmissionRefused("cs_eval_bad_seq")
    return int(value)


def cs_eval_outputs(kit: Kit, passes: Sequence | None = None) -> tuple[bytes, bytes, dict]:
    """(redacted CSV bytes, spans JSONL bytes, aggregate counts) for every turn of every ``eval`` conversation.

    Every eval turn appears once in both files, sorted by turn_id; a turn without spans has ``"spans": []``.
    The lexicon passes are required: a missing lexicon refuses instead of silently redacting less."""
    try:
        turns = kit.load_table(DATASET, "turns")
        convs = kit.load_table(DATASET, "conversations")
    except KitError:
        raise SubmissionRefused("cs_eval_unavailable") from None
    if any(c not in turns.columns for c in TURN_COLUMNS) or any(c not in convs.columns for c in CONV_COLUMNS):
        raise SubmissionRefused("cs_eval_unavailable")
    eval_ids = set(convs.loc[convs["split"] == EVAL_SPLIT, "conversation_id"])
    sub = turns[turns["conversation_id"].isin(eval_ids)]
    if not eval_ids or sub.empty or sub["turn_id"].duplicated().any():
        raise SubmissionRefused("cs_eval_unavailable")
    try:
        passes = list(passes) if passes is not None else default_passes(require_lexicon=True)
    except ModuleNotFoundError:
        raise SubmissionRefused("cs_eval_no_lexicon") from None
    texts: dict[str, str] = {}
    spans: dict[str, list] = {}
    for cid, group in sorted(sub.groupby("conversation_id", sort=True), key=lambda kv: kv[0]):
        ordered = sorted(group.itertuples(index=False), key=lambda r: (_seq(r.seq), r.turn_id))
        red = redact_conversation(cid, [Turn(r.turn_id, r.text, "", r.seq) for r in ordered], passes)
        texts.update(red.texts)
        for tid in (r.turn_id for r in ordered):
            spans[tid] = []
        for s in red.spans:
            spans[s["record_id"]].append({"start": s["start"], "end": s["end"], "label": s["label"]})
    if set(texts) != set(sub["turn_id"]) or set(spans) != set(texts):
        raise SubmissionRefused("cs_eval_incomplete")
    ids = sorted(texts)
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["turn_id", "text"])
    w.writerows([[t, texts[t]] for t in ids])
    lines = [json.dumps({"record_id": t, "spans": sorted(spans[t], key=lambda s: (s["start"], s["end"], s["label"]))},
                        ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for t in ids]
    counts = {"conversations": len(eval_ids & set(sub["conversation_id"])), "turns": len(ids),
              "spans": sum(len(v) for v in spans.values())}
    return buf.getvalue().encode("utf-8"), "".join(lines).encode("utf-8"), counts
