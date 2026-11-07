"""Per-conversation placeholder table.

Numbers are assigned per (label, value key) in order of first appearance and
restart for each conversation, so a placeholder carries no identity across
conversations. Lives only in memory; nothing here is ever written out.
"""

from __future__ import annotations

from collections.abc import Callable

from .labels import placeholder
from .normalise import value_key

Normaliser = Callable[[str, str], str]


class PlaceholderTable:
    def __init__(self, normalise: Normaliser = value_key) -> None:
        self._normalise = normalise
        self._numbers: dict[tuple[str, str], int] = {}
        self._next: dict[str, int] = {}

    def assign(self, label: str, value: str, key: str | None = None) -> str:
        k = key if key is not None else self._normalise(label, value)
        ident = (label, k)
        if ident not in self._numbers:
            n = self._next.get(label, 0) + 1
            self._next[label] = n
            self._numbers[ident] = n
        return placeholder(label, self._numbers[ident])
