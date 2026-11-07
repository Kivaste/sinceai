"""Redacted customer_service eval turns (``turn_id,text``) and detected spans (JSONL) for the organisers.

The redactor's output is not proof (D37): the exact export bytes go through the gate's production ``text.*``
checks before publication. A turn with a high-severity hit is masked whole (``MASK``) and its spans become one
whole-turn span per label; the checks re-run until clean. Counts only reach the index; no text leaves this module.
"""
from __future__ import annotations

import csv
import io
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pets_release.kit import Kit, KitError
from pets_release.redactor import Turn, default_passes, redact_conversation
from pets_release.submission.errors import SubmissionRefused

DATASET = "customer_service"
TURN_COLUMNS = ("turn_id", "conversation_id", "seq", "text")
CONV_COLUMNS = ("conversation_id", "split")
EVAL_SPLIT = "eval"
EXPORT_HEADER = ["turn_id", "text"]
MASK = "[REDACTED]"  # a placeholder shape the gate's normaliser masks, so a masked turn re-checks clean

# Staged views of the export bytes for the gate runner: the redacted texts stitched per conversation (the order
# and grouping come from the kit by turn_id), and every spans line as its own free-text row.
_TURNS_FILE = "eval_turns.csv"
_SPANS_FILE = "eval_spans.csv"
_CONTRACT = {
    "healthInTextRequired": True,  # CS-S1 privacy target no-health-in-text: max_hits 0
    "files": {
        _TURNS_FILE: {"columns": {
            "conversation_id": {"form": "categorical"},
            "seq": {"form": "categorical"},
            "text": {"form": "text", "params": {"conversation": "conversation_id", "order": "seq"}}}},
        _SPANS_FILE: {"columns": {"line": {"form": "text"}}},
    },
}


def _seq(value: str) -> int:
    if not value.isascii() or not value.isdigit():
        raise SubmissionRefused("cs_eval_bad_seq")
    return int(value)


def _serialise(texts: dict, spans: dict) -> tuple[bytes, bytes]:
    ids = sorted(texts)
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(EXPORT_HEADER)
    w.writerows([[t, texts[t]] for t in ids])
    lines = [json.dumps({"record_id": t, "spans": sorted(spans[t], key=lambda s: (s["start"], s["end"], s["label"]))},
                        ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for t in ids]
    return buf.getvalue().encode("utf-8"), "".join(lines).encode("utf-8")


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
    order: dict[str, tuple[str, str]] = {}  # turn_id -> (conversation_id, seq): stitching for the gate checks
    lengths: dict[str, int] = {}
    for cid, group in sorted(sub.groupby("conversation_id", sort=True), key=lambda kv: kv[0]):
        ordered = sorted(group.itertuples(index=False), key=lambda r: (_seq(r.seq), r.turn_id))
        red = redact_conversation(cid, [Turn(r.turn_id, r.text, "", r.seq) for r in ordered], passes)
        texts.update(red.texts)
        for r in ordered:
            spans[r.turn_id] = []
            order[r.turn_id] = (cid, str(_seq(r.seq)))
            lengths[r.turn_id] = len(r.text)
        for s in red.spans:
            spans[s["record_id"]].append({"start": s["start"], "end": s["end"], "label": s["label"]})
    if set(texts) != set(sub["turn_id"]) or set(spans) != set(texts):
        raise SubmissionRefused("cs_eval_incomplete")
    redactor_spans = sum(len(v) for v in spans.values())
    redacted, spans_bytes, gate = _gate(texts, spans, order, lengths)
    counts = {"conversations": len(eval_ids & set(sub["conversation_id"])), "turns": len(texts),
              "redactorSpans": redactor_spans, "spans": sum(len(v) for v in spans.values()), **gate}
    return redacted, spans_bytes, counts


# ---------------------------------------------------------------- the gate on the export bytes

def _text_checks() -> list:
    """The gate's registered text checks, every one of them; any missing or an untrustworthy registry refuses."""
    from pets_release.checks import registry
    from pets_release.checks.text import HEALTH_CHECK, TEXT_CHECKS

    want = {*TEXT_CHECKS, HEALTH_CHECK}
    try:
        got = {c.name: c for c in registry.all_checks() if c.name in want}
    except registry.RegistryError:
        raise SubmissionRefused("cs_eval_checks_unavailable") from None
    if set(got) != want:
        raise SubmissionRefused("cs_eval_checks_unavailable")
    return [got[n] for n in sorted(want)]


def _parse_export(redacted: bytes, spans: bytes) -> tuple[list, list]:
    """(turn rows, spans lines) as a reader of the exact bytes recovers them; refuses anything ambiguous."""
    try:
        rows = list(csv.reader(io.StringIO(redacted.decode("utf-8"), newline="")))
        lines = spans.decode("utf-8").split("\n")
    except UnicodeDecodeError:
        raise SubmissionRefused("cs_eval_format") from None
    if not rows or rows[0] != EXPORT_HEADER or any(len(r) != 2 for r in rows[1:]) or lines[-1] != "":
        raise SubmissionRefused("cs_eval_format")
    return rows[1:], lines[:-1]


def _write_csv(path: Path, header: list, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _scan(redacted: bytes, spans: bytes, order: dict, checks: list):
    """Run the checks on the exact export bytes. Returns (turn ids, records) of the redacted-file rows."""
    from pets_release.checks.runner import run_checks

    rows, lines = _parse_export(redacted, spans)
    ids = [r[0] for r in rows]
    if len(lines) != len(ids) or set(ids) != set(order):
        raise SubmissionRefused("cs_eval_format")
    with tempfile.TemporaryDirectory(prefix="pets-cs-eval-gate-") as tmp:
        stage = Path(tmp)
        _write_csv(stage / _TURNS_FILE, ["conversation_id", "seq", "text"], [[*order[t], x] for t, x in rows])
        _write_csv(stage / _SPANS_FILE, ["line"], [[x] for x in lines])
        res = run_checks(stage, _CONTRACT, {"phase": "gate"}, checks=checks)
    if (res.registry_error is not None or sorted(r.check for r in res.records) != sorted(c.name for c in checks)
            or any(r.status not in ("pass", "fail") for r in res.records)):
        raise SubmissionRefused("cs_eval_check_error")  # not run, errored or not applicable is never clean
    return ids, res.records


def _gate(texts: dict, spans: dict, order: dict, lengths: dict) -> tuple[bytes, bytes, dict]:
    """Mask flagged turns whole until the checks find no high-severity hit; mutates ``texts`` and ``spans``."""
    checks = _text_checks()
    flagged: dict[str, set] = {}  # turn id -> labels the checker found there
    for _ in range(len(texts) + 1):
        redacted, spans_bytes = _serialise(texts, spans)
        ids, records = _scan(redacted, spans_bytes, order, checks)
        high = [v for r in records for v in r.violations if v.severity == "high"]
        if any(v.file == _SPANS_FILE for v in high):
            raise SubmissionRefused("cs_eval_spans_flagged")  # turn ids must ship as they are; nothing to mask
        new = {}
        for v in high:
            for row in v.locations:
                tid = ids[row]
                if tid not in flagged:
                    new.setdefault(tid, set()).add(v.label)
        if not high:
            low = sum(v.count for r in records for v in r.violations if v.severity == "low")
            by_label: dict[str, int] = {}
            for labels in flagged.values():
                for label in labels:
                    by_label[label] = by_label.get(label, 0) + 1
            return redacted, spans_bytes, {"maskedTurns": len(flagged), "maskedTurnsByLabel": dict(sorted(by_label.items())),
                                           "lowSeverityHits": low, "textChecks": [c.name for c in checks]}
        if not new:
            raise SubmissionRefused("cs_eval_unmaskable")  # a hit survives in a masked turn: never ship it
        for tid, labels in new.items():
            flagged[tid] = labels
            texts[tid] = MASK
            kinds = labels | {s["label"] for s in spans[tid]}
            spans[tid] = [{"start": 0, "end": lengths[tid], "label": k} for k in sorted(kinds)] if lengths[tid] else []
    raise SubmissionRefused("cs_eval_unmaskable")
