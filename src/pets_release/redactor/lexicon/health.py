"""HEALTH: phrase-level. A health term pulls in the few words of its own clause that state it
("minulla on kuulolaite"); the rest of the turn stays untouched and readable."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable

from ..passes import Candidate, ConversationView
from .base import LexiconPass
from .loader import Rules
from .textutil import tokens

_CLAUSE_PUNCT = re.compile(r"[.!?;:,\n\r()]")


class HealthPass(LexiconPass):
    name = "lexicon.health"
    label = "HEALTH"

    def __init__(self, entries: dict, rules: Rules):
        rows = entries.get("health", ())
        terms = [e.term for e in rows if e.match == "prefix"]
        self.term_re = re.compile(
            r"(?<![^\W_])(?:" + "|".join(sorted(map(re.escape, terms), key=len, reverse=True)) + r")", re.IGNORECASE
        )
        cues = [e.term for e in rows if e.match == "cue"]
        self.cue_re = re.compile(
            r"(?<![^\W_])(?:" + "|".join(sorted(map(re.escape, cues), key=len, reverse=True)) + r")\s+(?:\w+\s+){0,3}?$", re.IGNORECASE
        )
        self.stop = frozenset(e.term.lower() for e in rows if e.match == "stopword")
        self.left = rules.int_of("@health_left", "HEALTH", 3)
        self.right = rules.int_of("@health_right", "HEALTH", 0)

    def run(self, view: ConversationView) -> Iterable[Candidate]:
        """Phrase spans whose cores are the health-term words inside them: overlap resolution is all-or-nothing,
        so a phrase that loses to a name in its left context would otherwise leave the health term in the text."""
        for c in super().run(view):
            text = view.turns[c.turn_index].text
            toks = tokens(text)
            cores = []
            for m in self.term_re.finditer(text, c.start, c.end):
                t = next((t for t in toks if t.start <= m.start() < t.end), None)
                if t is not None and c.start <= t.start and t.end <= c.end and (t.start, t.end) not in cores:
                    cores.append((t.start, t.end))
            yield dataclasses.replace(c, cores=tuple(cores))

    def find(self, text: str) -> list[tuple[int, int]]:
        toks = tokens(text)
        spans: list[tuple[int, int]] = []
        for m in self.term_re.finditer(text):
            ti = next((i for i, t in enumerate(toks) if t.start <= m.start() < t.end), None)
            if ti is None:
                continue
            first = last = ti
            while first > 0 and ti - first < self.left:
                p = toks[first - 1]
                if _CLAUSE_PUNCT.search(text[p.end:toks[first].start]) or p.low in self.stop:
                    break
                first -= 1
            while last + 1 < len(toks) and last - ti < self.right:
                nxt = toks[last + 1]
                if _CLAUSE_PUNCT.search(text[toks[last].end:nxt.start]) or nxt.low in self.stop:
                    break
                last += 1
            start, end = toks[first].start, toks[last].end
            cm = self.cue_re.search(text[max(0, start - 40): start])
            if cm and not _CLAUSE_PUNCT.search(text[max(0, start - 40) + cm.start(): start]):
                start = max(0, start - 40) + cm.start()
            spans.append((start, end))
        return _merge(spans, text)


def _merge(spans: list[tuple[int, int]], text: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1] + 1 and not _CLAUSE_PUNCT.search(text[out[-1][1]:s]):
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
