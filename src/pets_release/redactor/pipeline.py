"""Redactor pipeline: turns of one conversation in; Spans and placeholder-substituted turns out."""

from __future__ import annotations

import dataclasses
import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import cross_turn
from .labels import LABELS
from .normalise import value_key
from .passes import Candidate, ConversationView, Pass, Turn
from .placeholders import PlaceholderTable
from .structured import StructuredPass

LEXICON_MODULE = "pets_release.redactor.lexicon"


def placeholder_identity(label: str, value: str) -> str:
    """Value identity for placeholder numbering: the pseudonymiser's normaliser (ticket 06: case,
    separators, spoken digits, fi/sv name case endings) for the labels it knows, else the local one."""
    from pets_release.pseudonym import normalise as pseudo_normalise

    if label in PSEUDONYM_LABELS:
        return pseudo_normalise(value, label)
    return value_key(label, value)


PSEUDONYM_LABELS = frozenset(importlib.import_module("pets_release.pseudonym.normalise").LABELS)


@dataclass(frozen=True)
class Redaction:
    spans: list[dict]  # Span = {record_id, start, end, label, placeholder}, sorted by turn order, start
    texts: dict[str, str]  # turn_id -> placeholder-substituted text
    passes_run: tuple[str, ...]


def default_passes(require_lexicon: bool = False) -> list[Pass]:
    """The structured pass plus, when installed, the lexicon passes from ticket 13.

    The lexicon subpackage contract: ``pets_release.redactor.lexicon.passes() -> list[Pass]``.
    With ``require_lexicon=True`` a missing lexicon package is an error, never a silent skip.
    """
    out: list[Pass] = [StructuredPass()]
    try:
        lex = importlib.import_module(LEXICON_MODULE)
    except ModuleNotFoundError as e:
        if e.name != LEXICON_MODULE and not LEXICON_MODULE.startswith(str(e.name)):
            raise
        if require_lexicon:
            raise
        return out
    out.extend(lex.passes())
    return out


def _resolve(cands: list[Candidate], texts: Sequence[str]) -> list[Candidate]:
    """Pick non-overlapping candidates: priority, then length, then earlier start, then source."""
    order = sorted(cands, key=lambda c: (-c.priority, -(c.end - c.start), c.turn_index, c.start, c.source, c.label))
    taken: dict[int, list[tuple[int, int]]] = {}
    keep: list[Candidate] = []
    lost: list[Candidate] = []
    for c in order:
        occupied = taken.setdefault(c.turn_index, [])
        if any(c.start < e and s < c.end for s, e in occupied):
            lost.append(c)
            continue
        occupied.append((c.start, c.end))
        keep.append(c)
    for c in lost:  # same order: a lost candidate's cores are claimed where nothing else holds them
        occupied = taken[c.turn_index]
        for s, e in c.cores:
            if c.start <= s < e <= c.end and not any(s < oe and os < e for os, oe in occupied):
                occupied.append((s, e))
                keep.append(dataclasses.replace(c, start=s, end=e, cores=()))
    return sorted(keep, key=lambda c: (c.turn_index, c.start))


def redact_conversation(
    conversation_id: str,
    turns: Sequence[Turn],
    passes: Sequence[Pass] | None = None,
    normalise: Callable[[str, str], str] = placeholder_identity,
) -> Redaction:
    """Redact one conversation. ``turns`` must be in conversation order.

    ``normalise(label, value)`` gives the value identity for placeholder numbering when a pass does
    not supply a key (seam for the pseudonymiser's normaliser).
    """
    turns = tuple(turns)
    if passes is None:
        passes = default_passes()
    # then gate-consistent across turns: forced candidates for the gate text checks' hits (#92)
    return cross_turn.redact_until_clean(_redact_once, conversation_id, turns, tuple(passes), normalise)


def _redact_once(conversation_id: str, turns: tuple[Turn, ...], passes: Sequence[Pass],
                 normalise: Callable[[str, str], str]) -> Redaction:
    view = ConversationView(conversation_id, turns)
    texts = [t.text for t in turns]
    cands: list[Candidate] = []
    names = []
    for p in passes:
        names.append(p.name)
        for c in p.run(view):
            if c.label not in LABELS or c.label not in p.labels:
                raise ValueError(f"pass {p.name!r} emitted undeclared label {c.label!r}")
            if not (0 <= c.turn_index < len(turns)) or not (0 <= c.start < c.end <= len(texts[c.turn_index])):
                raise ValueError(f"pass {p.name!r} emitted out-of-range offsets")
            cands.append(c)
    if len(set(names)) != len(names):
        raise ValueError("pass names must be unique")
    kept = _resolve(cands, texts)

    table = PlaceholderTable(normalise)
    spans: list[dict] = []
    by_turn: dict[int, list[tuple[Candidate, str]]] = {}
    for c in kept:
        ph = table.assign(c.label, texts[c.turn_index][c.start:c.end], c.key)
        by_turn.setdefault(c.turn_index, []).append((c, ph))
        spans.append({"record_id": turns[c.turn_index].turn_id, "start": c.start, "end": c.end,
                      "label": c.label, "placeholder": ph})
    out_texts: dict[str, str] = {}
    for i, t in enumerate(turns):
        s = t.text
        for c, ph in sorted(by_turn.get(i, []), key=lambda x: -x[0].start):
            s = s[: c.start] + ph + s[c.end:]
        out_texts[t.turn_id] = s
    return Redaction(spans, out_texts, tuple(names))
