"""Gate-consistent redaction across turns (must-fix #92).

The passes look at one turn at a time (plus cue context), so an identifier split across adjacent
turns of one conversation can survive: a cue ending one turn and its value starting the next, or one
value cut in two. After the passes, this step runs the gate's own text detectors with the gate's own
N-turn stitching over the *redacted* turns: ``checks.text._scan.conversation_hits`` (the function
behind the ``text.*`` checks, shared, not copied; same windows, same normalised views, same merge
rule). Every hit that touches more than one turn becomes a forced candidate on the source turns and
the conversation is redacted again, until the gate finds no such hit. A single-turn hit is handled the
same way only in a turn this step has already redacted (a cue turn whose kept words still make a hit
with a value fragment left in it); other single-turn hits are the passes' business (their precision is
pinned by the redactor tests and the kit exact-match floor), so this step never widens them.

What a hit redacts (its parts are the (turn, start, end) fragments the gate reports):

* value-shaped labels (card, IBAN, phone, e-mail, ...): every fragment, so a split value loses both
  halves; all fragments of one hit share one value key, so they get one placeholder number;
* cue-introduced labels (``CUE_LABELS``): each fragment from its first value-bearing token (a digit,
  a spoken digit, an inner capital or a symbol). A non-final fragment with none holds only the cue
  words and is kept; a final fragment with none loses its last token (the value word);
* a hit whose region would redact nothing new is escalated to its whole fragments; if that still
  redacts nothing new, the conversation cannot be made clean and ``ValueError`` is raised (fail
  closed, never a silent leak).

Forced candidates outrank every pass (``PRIORITY_FORCED``). A forced region that overlaps an earlier
redaction is widened to cover it, and overlapping forced regions in one turn are merged, so forced
coverage only grows and the loop ends.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from .labels import LABELS
from .passes import PRIORITY_VALIDATED, Candidate, ConversationView, Pass, Turn

PASS_NAME = "gate-cross-turn"
PRIORITY_FORCED = PRIORITY_VALIDATED + 100
CUE_LABELS = frozenset({"SECRET", "USERNAME", "ACCOUNT_NUMBER"})

_TOKEN_RE = re.compile(r"\S+")
_EDGE_PUNCT = ".,;:!?\"'()¦"
_WORD_SYMBOLS = "'’-"
_PLACEHOLDER_RE = re.compile(r"\[[A-Z_]+_\d+\]")


def _gate():
    # imported lazily: the gate package imports the whole check registry
    from pets_release.checks import text as gate
    from pets_release.checks.text import _normalise, _scan

    return gate, _scan, _normalise


def detectors() -> list[tuple[str, Callable, str]]:
    """(label, detector, view) of every high-severity gate text check, in check-name order. (Low-severity
    hits are counted residual risk the gate never refuses, e.g. private IPs; the passes own those.)"""
    gate, _scan, _n = _gate()
    return [(label, det, view) for _name, (_a, label, det, view) in sorted(gate.TEXT_CHECKS.items())]


def gate_hits(texts: Sequence[str]) -> list[tuple[str, list[tuple[int, int, int]]]]:
    """[(label, sorted parts)] the gate's text checks find in these turns of one conversation."""
    _gate_mod, _scan, _n = _gate()
    conv = _scan.conversation(list(texts))
    out = []
    for label, det, view in detectors():
        for parts in _scan.conversation_hits(conv, det, view):
            out.append((label, sorted(parts)))
    return out


def _value_bearing(tok: str) -> bool:
    _g, _s, normalise = _gate()
    t = tok.strip(_EDGE_PUNCT)
    if not t or _PLACEHOLDER_RE.search(tok):
        return False
    if any(c.isdigit() for c in t) or t.lower() in normalise.DIGIT_WORDS:
        return True
    if any(c.isupper() for c in t[1:]) and any(c.islower() for c in t):
        return True
    return any(not (c.isalnum() or c in _WORD_SYMBOLS) for c in t)


def _trimmed(label: str, text: str, s: int, e: int, last: bool) -> tuple[int, int] | None:
    """The region of one fragment [s, e) of ``text`` to redact (see module doc), or None to keep it."""
    toks = [(s + m.start(), s + m.end()) for m in _TOKEN_RE.finditer(text[s:e])]
    if not toks:
        return None
    if label not in CUE_LABELS:
        return toks[0][0], toks[-1][1]
    for ts, te in toks:
        if _value_bearing(text[ts:te]):
            return ts, toks[-1][1]
    return toks[-1] if last else None


class _OffsetMap:
    """Maps offsets in one redacted turn back to its source turn (placeholders map to their span)."""

    def __init__(self, spans: list[dict]):
        self.segs = []  # (src_start, src_end, red_start, red_end)
        delta = 0
        for sp in sorted(spans, key=lambda x: x["start"]):
            rs = sp["start"] + delta
            re_ = rs + len(sp["placeholder"])
            self.segs.append((sp["start"], sp["end"], rs, re_))
            delta += len(sp["placeholder"]) - (sp["end"] - sp["start"])

    def start(self, p: int) -> int:
        delta = 0
        for ss, se, rs, re_ in self.segs:
            if p < rs:
                break
            if p < re_:
                return ss
            delta = re_ - se
        return p - delta

    def end(self, p: int) -> int:
        delta = 0
        for ss, se, rs, re_ in self.segs:
            if p <= rs:
                break
            if p <= re_:
                return se
            delta = re_ - se
        return p - delta


class _ForcedPass:
    name = PASS_NAME
    labels = frozenset(LABELS)

    def __init__(self, forced: dict[int, list[list]]):
        self.forced = forced

    def run(self, view: ConversationView):
        for i in sorted(self.forced):
            for s, e, label, key in sorted(self.forced[i], key=lambda r: r[0]):
                yield Candidate(i, s, e, label, priority=PRIORITY_FORCED, key=key, source=PASS_NAME)


def _new_chars(intervals: list[tuple[int, int]], s: int, e: int) -> bool:
    """True when [s, e) holds a position outside every interval."""
    pos = s
    for a, b in sorted(intervals):
        if b <= pos:
            continue
        if a > pos:
            return True
        pos = b
        if pos >= e:
            return False
    return pos < e


def _widen(intervals: list[tuple[int, int]], s: int, e: int) -> tuple[int, int]:
    changed = True
    while changed:
        changed = False
        for a, b in intervals:
            if a < e and s < b and (a < s or b > e):
                s, e = min(s, a), max(e, b)
                changed = True
    return s, e


def _add_forced(forced: dict[int, list[list]], turn: int, s: int, e: int, label: str, key: str) -> None:
    rows = forced.setdefault(turn, [])
    keep_label, keep_key = label, key
    for r in sorted([r for r in rows if r[0] < e and s < r[1]], key=lambda r: r[0]):
        rows.remove(r)
        s, e = min(s, r[0]), max(e, r[1])
        keep_label, keep_key = r[2], r[3]  # an earlier forced value keeps its identity
    rows.append([s, e, keep_label, keep_key])


def redact_until_clean(redact_once, conversation_id: str, turns: Sequence[Turn], passes: Sequence[Pass],
                       normalise: Callable[[str, str], str]):
    """``redact_once(conversation_id, turns, passes, normalise)`` repeated with forced candidates for
    the gate's text-check hits until the redacted turns have none (see module doc)."""
    red = redact_once(conversation_id, turns, passes, normalise)
    index = {t.turn_id: i for i, t in enumerate(turns)}
    if len(index) != len(turns):
        raise ValueError("turn ids must be unique within a conversation")
    forced: dict[int, list[list]] = {}
    for _round in range(sum(len(t.text) for t in turns) + 1):
        texts = [red.texts[t.turn_id] for t in turns]
        hits = [(label, parts) for label, parts in gate_hits(texts)
                if len({p[0] for p in parts}) > 1 or parts[0][0] in forced]
        if not hits:
            return red
        by_turn: dict[int, list[dict]] = {}
        for sp in red.spans:
            by_turn.setdefault(index[sp["record_id"]], []).append(sp)
        maps = [_OffsetMap(by_turn.get(i, [])) for i in range(len(turns))]
        covered = {i: [(sp["start"], sp["end"]) for sp in by_turn.get(i, [])] for i in range(len(turns))}
        progress = False
        for label, parts in hits:
            def regions(trim: bool, label=label, parts=parts):
                out = []
                for n, (t, s, e) in enumerate(parts):
                    r = _trimmed(label, texts[t], s, e, n == len(parts) - 1) if trim else (s, e)
                    if r is not None:
                        out.append((t, maps[t].start(r[0]), maps[t].end(r[1])))
                return out

            chosen = regions(True)
            if not any(_new_chars(covered[t], s, e) for t, s, e in chosen):
                chosen = regions(False)
                if not any(_new_chars(covered[t], s, e) for t, s, e in chosen):
                    continue
            progress = True
            value = "".join(turns[t].text[s:e] for t, s, e in chosen)
            key = normalise(label, value)
            for t, s, e in chosen:
                s, e = _widen(covered[t], s, e)
                _add_forced(forced, t, s, e, label, key)
        if not progress:
            raise ValueError("cross-turn redaction cannot remove a gate text-check hit")
        red = redact_once(conversation_id, turns, [*passes, _ForcedPass(forced)], normalise)
    raise ValueError("cross-turn redaction did not converge")
