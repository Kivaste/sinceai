"""Controller gazetteer: names, cities and streets of the controller's own source tables.

Built at runtime from in-memory values the caller passes in; it has no ``save`` and the package
never writes a file. The committed lexicons (``data/*.csv``) hold general-knowledge terms only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_NAME_PART = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")
_TITLES = frozenset({"dr", "mr", "mrs", "ms", "miss", "prof", "herra", "rouva", "neiti"})


@dataclass(frozen=True)
class Gazetteer:
    given: frozenset[str] = frozenset()
    family: frozenset[str] = frozenset()
    cities: frozenset[str] = frozenset()
    streets: frozenset[str] = frozenset()
    # conversation id -> full names of the parties known to belong to that conversation (customer, agent)
    parties: tuple = ()

    @classmethod
    def from_tables(
        cls,
        full_names: Iterable[str] = (),
        cities: Iterable[str] = (),
        streets: Iterable[str] = (),
        parties: Mapping[str, Iterable[str]] | None = None,
    ) -> Gazetteer:
        """``full_names``: "Given [Given…] Family"; ``streets``: street names or "Street 12 B 3" addresses."""
        given: set[str] = set()
        family: set[str] = set()
        for full in full_names:
            parts = [p for p in _NAME_PART.findall(full or "") if p.lower().rstrip(".") not in _TITLES]
            if not parts:
                continue
            if len(parts) == 1:
                given.add(parts[0])
                continue
            family.add(parts[-1])
            given.update(parts[:-1])
        city_set = {c.strip() for c in cities if c and c.strip()}
        street_set: set[str] = set()
        for s in streets:
            m = re.match(r"\s*([^\W\d_][^\d,]*?)\s*(?:\d|,|$)", s or "")
            if m and m.group(1).strip():
                street_set.add(m.group(1).strip())
        party_t = tuple(sorted((cid, tuple(sorted({n for n in names if n}))) for cid, names in (parties or {}).items()))
        return cls(frozenset(given), frozenset(family), frozenset(city_set), frozenset(street_set), party_t)

    def party_names(self) -> dict[str, tuple[str, ...]]:
        return dict(self.parties)

    def __bool__(self) -> bool:
        return bool(self.given or self.family or self.cities or self.streets or self.parties)
