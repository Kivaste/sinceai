"""Typed data dictionary: table and column names, roles, subtypes and descriptions. No data values.

This is the only description of the data that can reach an LLM prompt (ADR 0002).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_DESCRIPTION = 300
_H3 = re.compile(r"^###\s+(\S+)\s*/\s*(\S+)\s*$")
_H2 = re.compile(r"^##\s+(\S+)\s*$")
_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|(.*)\|\s*$")


class DictionaryError(ValueError):
    """The dictionary has no usable section for the dataset."""


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    role: str
    subtype: str
    description: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class DataDictionary:
    dataset: str
    tables: tuple[TableInfo, ...]

    def columns(self) -> frozenset[tuple[str, str]]:
        return frozenset((t.name, c.name) for t in self.tables for c in t.columns)


def parse_dictionary(markdown: str, dataset: str) -> DataDictionary:
    """Parse the kit's docs/DATA_DICTIONARY.md for one dataset. Fails closed when nothing is found."""
    tables: dict[str, list[ColumnInfo]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        m = _H3.match(line)
        if m:
            current = m.group(2) if m.group(1) == dataset else None
            if current is not None:
                tables.setdefault(current, [])
            continue
        if _H2.match(line):
            current = None
            continue
        r = _ROW.match(line)
        if r and current is not None:
            cells = [c.strip() for c in r.group(2).split("|")]
            if len(cells) < 4:
                continue
            role, subtype, description = cells[0], cells[1], cells[-1]
            tables[current].append(ColumnInfo(r.group(1), role, subtype, description[:MAX_DESCRIPTION]))
    populated = {n: cols for n, cols in tables.items() if cols}
    if not populated:
        raise DictionaryError("data dictionary has no tables for the requested dataset")
    return DataDictionary(dataset, tuple(TableInfo(n, tuple(populated[n])) for n in sorted(populated)))
