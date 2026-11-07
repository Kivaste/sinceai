"""Shared base for the lexicon passes: per-turn ``find`` -> Candidates, duplicate-free and sorted."""

from __future__ import annotations

from collections.abc import Iterable

from ..passes import PRIORITY_LEXICON, Candidate, ConversationView


def drop_overlaps(found: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Longest-first, then earliest; no two spans overlap. Result sorted by start."""
    keep: list[tuple[int, int]] = []
    for s, e in sorted(set(found), key=lambda x: (-(x[1] - x[0]), x[0])):
        if all(e <= ks or s >= ke for ks, ke in keep):
            keep.append((s, e))
    return sorted(keep)


class LexiconPass:
    name = "lexicon.base"
    label = ""
    priority = PRIORITY_LEXICON

    @property
    def labels(self) -> frozenset[str]:
        return frozenset({self.label})

    def find(self, text: str) -> list[tuple[int, int]]:
        raise NotImplementedError

    def run(self, view: ConversationView) -> Iterable[Candidate]:
        for i, turn in enumerate(view.turns):
            for s, e in drop_overlaps(self.find(turn.text)):
                if 0 <= s < e <= len(turn.text):
                    yield Candidate(i, s, e, self.label, self.priority, None, self.name)
