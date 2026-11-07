"""Redacted customer_service eval turns (``turn_id,text``) and detected spans (JSONL) for the organisers.

The redactor's output is not proof (D37): the exact export bytes go through the gate's production ``text.*`` checks
and its cell-level checks (rescans, raw timestamps, 64-hex, original values, unkeyed hashes; #148), over the turn
texts, the turn ids as both files decode them, and the decoded spans. A turn with a high-severity hit is masked whole
with one typed placeholder and one whole-turn span of its label; the checks re-run until clean. A hit in an ID or the
spans refuses. Counts only reach the index; no text leaves this module.
"""
from __future__ import annotations

import csv
import io
import json
import re
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from pets_release.kit import Kit, KitError
from pets_release.redactor import Turn, default_passes, redact_conversation
from pets_release.redactor.labels import LABELS, PLACEHOLDER_TYPE, parse_placeholder, placeholder
from pets_release.submission.errors import SubmissionRefused

DATASET = "customer_service"
TURN_COLUMNS = ("turn_id", "conversation_id", "seq", "text")
CONV_COLUMNS = ("conversation_id", "split")
EVAL_SPLIT = "eval"
EXPORT_HEADER = ["turn_id", "text"]

# Staged views of the export bytes for the gate runner: the redacted texts stitched per conversation (the order
# and grouping come from the kit by turn_id), and every spans line as its own free-text row.
_TURNS_FILE = "eval_turns.csv"
_SPANS_FILE = "eval_spans.csv"
_IDS_FILE = "eval_ids.csv"  # the turn ids as decoded from both exports; a hit here cannot be masked
_CONTRACT = {
    "healthInTextRequired": True,  # CS-S1 privacy target no-health-in-text: max_hits 0
    "files": {
        _TURNS_FILE: {"columns": {
            "conversation_id": {"form": "categorical"},
            "seq": {"form": "categorical"},
            "text": {"form": "text", "params": {"conversation": "conversation_id", "order": "seq"}}}},
        _SPANS_FILE: {"columns": {"line": {"form": "text"}}},
        _IDS_FILE: {"columns": {"id": {"form": "text"}}},
    },
}
_EXPORT_FILE = "customer_service_eval_redacted.csv"  # the cell checks see the redacted file's exact bytes
_CELL_CONTRACT = {
    "tokens": [],  # nothing in the eval exports is a keyed token: any 64-hex is a hit
    "files": {
        _EXPORT_FILE: {"columns": {"turn_id": {"form": "categorical"}, "text": {"form": "text"}}},
        _SPANS_FILE: {"columns": {"line": {"form": "text"}}},
        _IDS_FILE: {"columns": {"id": {"form": "text"}}},
    },
}
# Cell-check labels that are not span labels -> the span label of a whole masked turn.
_CHECK_LABELS = {"RAW_TIMESTAMP": "DATE", "HEX64_OUTSIDE_TOKEN": "SECRET"}
# producer.original-values labels are "<table>.<column>" of a CS-S1 direct identifier -> its span label.
_IDENTIFIER_LABELS = {"full_name": "PERSON", "agent_name": "PERSON", "street_address": "ADDRESS", "email": "EMAIL",
                      "phone": "PHONE", "iban": "IBAN", "hetu": "NATIONAL_ID", "customer_id": "ACCOUNT_NUMBER",
                      "customer_number": "ACCOUNT_NUMBER", "contract_number": "ACCOUNT_NUMBER"}
_BRACKETED = re.compile(r"\[[A-Z_0-9]+\]")  # candidate placeholders; parse_placeholder decides
INDEPENDENCE_NOTE = ("reduced for masked turns: the production checks that flagged a turn also decided its masking, "
                     "so no independent check confirms those turns (D29/D37)")


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
    texts, spans, order, lengths = _redact(sub, passes)
    redactor_spans = sum(len(v) for v in spans.values())
    context = producer_context(kit)
    redacted, spans_bytes, gate = _gate(texts, spans, order, lengths, context)
    counts = {"conversations": len(eval_ids & set(sub["conversation_id"])), "turns": len(texts),
              "redactorSpans": redactor_spans, "spans": sum(len(v) for v in spans.values()), **gate,
              "maskingEffect": masking_effect(kit, turns, convs, passes, context)}
    return redacted, spans_bytes, counts


def _redact(sub, passes) -> tuple[dict, dict, dict, dict]:
    """(texts, spans, order, lengths) of the turns in ``sub``, redacted one conversation at a time."""
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
    return texts, spans, order, lengths


# ---------------------------------------------------------------- the masking effect on the redaction metrics

GOLD_FILE = ("metadata", "pii_spans", "customer_service__turns__text.jsonl")
EFFECT_FRAME = ("customer_service train split, conversation-level skeleton-held-out conversations (labelled); "
                "the eval split's labels are not in the kit")


def _not_measured(reason: str) -> dict:
    return {"status": "not_measured", "reason": reason}


def _micro(gold: dict, pred: dict) -> dict:
    from pets_release.redaction_eval.scoring import score_frame

    m = score_frame(gold, pred)["micro_f2_all"]
    return {k: None if m[k] is None else round(float(m[k]), 4) for k in ("precision", "recall", "f2")}


def masking_effect(kit: Kit, turns, convs, passes, context: dict) -> dict:
    """Exact-match micro precision/recall/F2 (all labels) of the packaging pipeline on the labelled held-out
    conversations, before and after the D37 whole-turn masking; ``not_measured`` with a reason where the kit
    gives no labelled held-out frame. Aggregates only."""
    from pets_release.redaction_eval.frame import build_frame, load_spans
    from pets_release.redaction_eval.split import split_by_skeleton

    path = kit.root.joinpath(*GOLD_FILE)
    if not path.is_file():
        return _not_measured("no labelled customer_service spans in the kit (" + "/".join(GOLD_FILE) + ")")
    try:
        gold = load_spans(path)
    except (OSError, ValueError, KeyError, TypeError):
        return _not_measured("the labelled customer_service spans could not be read")
    frame = build_frame(turns.to_dict("records"), convs.to_dict("records"), gold)
    held = sorted(split_by_skeleton(frame).held_out_turns)
    if not held:
        return _not_measured("the conversation-level held-out labelled frame is empty on this kit")
    try:
        texts, spans, order, lengths = _redact(turns[turns["turn_id"].isin(set(held))], passes)
        truth = {t: frame.gold[t] for t in held}
        before = _micro(truth, {t: list(spans[t]) for t in held})
        _r, _s, gate = _gate(texts, spans, order, lengths, context)
        after = _micro(truth, {t: spans[t] for t in held})
    except SubmissionRefused as e:
        return _not_measured(f"masking could not be replayed on the held-out frame ({e.code})")
    except ModuleNotFoundError:
        return _not_measured("the pinned scorer (pets_eval) is not importable")
    if any(not isinstance(m[k], float) for m in (before, after) for k in m):  # `measured` means every number is real
        return _not_measured("a held-out metric is undefined (the scorer returned no number)")
    return {"status": "measured", "frame": EFFECT_FRAME, "metric": "exact-match micro, all labels",
            "conversations": len({frame.conversation_of[t] for t in held}), "turns": len(held),
            "maskedTurns": gate["maskedTurns"], "before": before, "after": after}


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


def _cell_checks() -> list:
    """The gate's cell-level production checks that apply to the eval bytes (#148): every per-label rescan, raw
    timestamps, 64-hex outside tokens, original-value survival and unkeyed hashes. Key material is scanned over
    the whole bundle by the packager; the structural/contract/k checks have no eval-file counterpart."""
    from pets_release.checks import registry
    from pets_release.checks.cells.labels import LABEL_CHECKS
    from pets_release.checks.producer.values import ORIGINAL_VALUES, UNKEYED_HASHES

    want = {*LABEL_CHECKS, ORIGINAL_VALUES, UNKEYED_HASHES}
    try:
        got = {c.name: c for c in registry.all_checks() if c.name in want}
    except registry.RegistryError:
        raise SubmissionRefused("cs_eval_checks_unavailable") from None
    if set(got) != want:
        raise SubmissionRefused("cs_eval_checks_unavailable")
    return [got[n] for n in sorted(want)]


def producer_context(kit: Kit) -> dict:
    """The original-value context of the producer checks: the kit's customer_service tables and the CS-S1
    policy's direct identifiers present in them (values stay in memory). None present refuses later (not run)."""
    from pets_release.policy import get_policy

    try:
        source = kit.load_dataset(DATASET)
    except KitError:
        raise SubmissionRefused("cs_eval_unavailable") from None
    idents = sorted(get_policy("CS-S1").direct_identifiers)
    return {"source": source,
            "identifiers": [{"table": t, "column": c} for t, c in idents if t in source and c in source[t].columns]}


_SPAN_KEYS = {"start", "end", "label"}


def _decode_line(line: str) -> tuple[str, list]:
    """(record_id, decoded strings of the spans) of one spans line, decoded strictly; refuses any other shape."""
    try:
        rec = json.loads(line)
    except ValueError:
        raise SubmissionRefused("cs_eval_format") from None
    if not isinstance(rec, dict) or set(rec) != {"record_id", "spans"} or not isinstance(rec["record_id"], str) \
            or not isinstance(rec["spans"], list):
        raise SubmissionRefused("cs_eval_format")
    strings = []
    for s in rec["spans"]:
        if not isinstance(s, dict) or set(s) != _SPAN_KEYS or not isinstance(s["label"], str) \
                or any(type(s[k]) is not int for k in ("start", "end")):
            raise SubmissionRefused("cs_eval_format")
        strings.append(s["label"])
    return rec["record_id"], strings


def _parse_export(redacted: bytes, spans: bytes) -> tuple[list, list, list]:
    """(turn rows, spans lines, decoded spans lines) as a reader of the exact bytes recovers them; refuses
    anything ambiguous. Decoded lines undo the JSON escaping (``\\t``, ``\\u001f``) that hides text from a raw scan."""
    try:
        rows = list(csv.reader(io.StringIO(redacted.decode("utf-8"), newline="")))
        lines = spans.decode("utf-8").split("\n")
    except UnicodeDecodeError:
        raise SubmissionRefused("cs_eval_format") from None
    if not rows or rows[0] != EXPORT_HEADER or any(len(r) != 2 for r in rows[1:]) or lines[-1] != "":
        raise SubmissionRefused("cs_eval_format")
    return rows[1:], lines[:-1], [_decode_line(x) for x in lines[:-1]]


def _write_csv(path: Path, header: list, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _run(stage: Path, contract: dict, context: dict, checks: list) -> list:
    """The checks' violations on a staged folder; any check not run, errored or not applicable refuses."""
    from pets_release.checks.runner import run_checks

    res = run_checks(stage, contract, context, checks=checks)
    if (res.registry_error is not None or sorted(r.check for r in res.records) != sorted(c.name for c in checks)
            or any(r.status not in ("pass", "fail") for r in res.records)):
        raise SubmissionRefused("cs_eval_check_error")  # not run, errored or not applicable is never clean
    return [v for r in res.records for v in r.violations]


def _scan(redacted: bytes, spans: bytes, order: dict, checks: tuple, context: dict):
    """Run the checks on the exact export bytes. Returns (turn ids, violations): turn-text violations name the
    staged turns file (rows in turn-id order); every other file or column is an ID, spans or header hit."""
    rows, lines, decoded = _parse_export(redacted, spans)
    ids = [r[0] for r in rows]
    if len(lines) != len(ids) or set(ids) != set(order) or [d[0] for d in decoded] != ids:
        raise SubmissionRefused("cs_eval_format")
    text_checks, cell_checks = checks
    with tempfile.TemporaryDirectory(prefix="pets-cs-eval-gate-") as tmp:
        stage, cells = Path(tmp) / "text", Path(tmp) / "cells"
        stage.mkdir()
        cells.mkdir()
        _write_csv(stage / _TURNS_FILE, ["conversation_id", "seq", "text"], [[*order[t], x] for t, x in rows])
        # Every ID as both readers recover it: the CSV turn_id and the decoded JSON record_id (#148).
        id_rows = [[t] for t in ids] + [[d[0]] for d in decoded]
        _write_csv(stage / _IDS_FILE, ["id"], id_rows)
        # The raw spans lines and every decoded string value in them.
        span_rows = [[x] for x in lines] + [[s] for d in decoded for s in d[1]]
        _write_csv(stage / _SPANS_FILE, ["line"], span_rows)
        found = _run(stage, _CONTRACT, {"phase": "gate"}, text_checks)
        # The cell-level production checks (#148) on the redacted file's exact bytes and the same ID/spans views;
        # a turn-text hit is reported against the turns file so one masking path handles both.
        (cells / _EXPORT_FILE).write_bytes(redacted)
        _write_csv(cells / _IDS_FILE, ["id"], id_rows)
        _write_csv(cells / _SPANS_FILE, ["line"], span_rows)
        for v in _run(cells, _CELL_CONTRACT, {"phase": "gate", **context}, cell_checks):
            if v.file == _EXPORT_FILE:
                v = replace(v, file=_TURNS_FILE if v.column == "text" else _IDS_FILE)
            found.append(v)
    return ids, found


def _span_label(check_label: str) -> str:
    """The span label (and so the placeholder type) of a checker hit; an unmapped label refuses (fail closed)."""
    if check_label in PLACEHOLDER_TYPE:
        return check_label
    if ":" in check_label:  # producer.unkeyed-hashes: "<algo>:<table>.<column>", an identifier's digest
        return "SECRET"
    label = _CHECK_LABELS.get(check_label) or _IDENTIFIER_LABELS.get(check_label.rpartition(".")[2])
    if label is None:
        raise SubmissionRefused("cs_eval_unlabelled_hit")
    return label


def _mask(tid: str, label: str, texts: dict, order: dict) -> str:
    """One typed placeholder for a whole masked turn, numbered after every ``label`` placeholder already in the
    turn's conversation (per-conversation numbering, as the redactor's)."""
    conv = order[tid][0]
    used = [0]
    for t, x in texts.items():
        if order[t][0] == conv:
            for m in _BRACKETED.findall(x):
                p = parse_placeholder(m)
                if p is not None and p[0] == label:
                    used.append(p[1])
    return placeholder(label, max(used) + 1)


def _gate(texts: dict, spans: dict, order: dict, lengths: dict, context: dict) -> tuple[bytes, bytes, dict]:
    """Mask flagged turns whole until the checks find no high-severity hit; mutates ``texts`` and ``spans``.

    A masked turn becomes one typed placeholder and one whole-turn span of the same label (the redactor's
    placeholder<->label table), so the two files cannot drift."""
    checks = (_text_checks(), _cell_checks())
    flagged: dict[str, set] = {}  # turn id -> labels the checker found there
    for _ in range(len(texts) + 1):
        redacted, spans_bytes = _serialise(texts, spans)
        ids, found = _scan(redacted, spans_bytes, order, checks, context)
        high = [v for v in found if v.severity == "high"]
        if any(v.file == _IDS_FILE for v in high):
            raise SubmissionRefused("cs_eval_id_flagged")  # turn ids must ship as they are; nothing to mask
        if any(v.file == _SPANS_FILE for v in high):
            raise SubmissionRefused("cs_eval_spans_flagged")
        if any(v.file != _TURNS_FILE for v in high):
            raise SubmissionRefused("cs_eval_check_error")  # a hit in a file this gate did not stage: never guess
        new = {}
        for v in high:
            for row in v.locations:
                tid = ids[row]
                if tid not in flagged:
                    new.setdefault(tid, set()).add(v.label)
        if not high:
            low = sum(v.count for v in found if v.severity == "low")
            by_label: dict[str, int] = {}
            for labels in flagged.values():
                for label in labels:
                    by_label[label] = by_label.get(label, 0) + 1
            return redacted, spans_bytes, {
                "maskedTurns": len(flagged), "maskedTurnsByLabel": dict(sorted(by_label.items())),
                "lowSeverityHits": low, "textChecks": [c.name for c in checks[0]],
                "cellChecks": [c.name for c in checks[1]],
                "checkerIndependence": {"reducedForTurns": len(flagged), "note": INDEPENDENCE_NOTE}}
        if not new:
            raise SubmissionRefused("cs_eval_unmaskable")  # a hit survives in a masked turn: never ship it
        for tid, labels in sorted(new.items()):
            flagged[tid] = labels
            label = min((_span_label(x) for x in labels), key=LABELS.index)
            texts[tid] = _mask(tid, label, texts, order)
            spans[tid] = [{"start": 0, "end": lengths[tid], "label": label}] if lengths[tid] else []
    raise SubmissionRefused("cs_eval_unmaskable")
