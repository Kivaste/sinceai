"""Reads the editable lexicon CSVs (pinned columns ``term,lang,label,match,boundary,notes``).

The CSVs are the only configuration of the lexicon passes: general-knowledge terms, cue words,
denylists and per-label boundary rules. Nothing here ever writes a file.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

COLUMNS = ("term", "lang", "label", "match", "boundary", "notes")
DATA_DIR = Path(__file__).parent / "data"

# What the ``match`` column may say (each pass documents the kinds it reads in data/README.md).
MATCH_KINDS = frozenset(
    {
        "lemma",  # dictionary form; inflected forms (case endings, consonant gradation) are matched
        "phrase",  # fixed multi-word or single-word expression, optional trailing ending
        "prefix",  # word-initial stem (health terms, compounds)
        "street",  # street-name ending (katu, tie, ...)
        "apartment-marker",
        "legal-suffix",  # Oy, Ltd, ... ending an organisation name
        "cue",  # clause starter kept inside a span (HEALTH)
        "cue-strong",  # a value of that label follows; the cue is excluded
        "cue-weak",  # only known values count after it
        "stopword",  # connective that never opens a span
        "deny",  # common word, never a name when lowercase / sentence-initial
        "month",
        "month-abbr",
        "month-stem",
        "rule",  # boundary rule row: term starts with '@'
    }
)


@dataclass(frozen=True)
class Entry:
    term: str
    lang: str
    label: str
    match: str
    boundary: str
    notes: str


def read_csv(path: Path) -> list[Entry]:
    with open(path, encoding="utf-8-sig", newline="") as fh:  # Excel adds a BOM
        reader = csv.reader(fh)
        header = next(reader, None)
        if tuple(header or ()) != COLUMNS:
            raise ValueError(f"{Path(path).name}: header must be {','.join(COLUMNS)}")
        out = []
        for n, row in enumerate(reader, 2):
            if not row:
                continue
            if len(row) != len(COLUMNS):
                raise ValueError(f"{Path(path).name}:{n}: expected {len(COLUMNS)} columns")
            e = Entry(*[c.strip() for c in row])
            if e.match not in MATCH_KINDS:
                raise ValueError(f"{Path(path).name}:{n}: unknown match kind {e.match!r}")
            if not e.term:
                raise ValueError(f"{Path(path).name}:{n}: empty term")
            out.append(e)
        return out


@lru_cache(maxsize=8)
def _load(data_dir: str) -> dict[str, tuple[Entry, ...]]:
    d = Path(data_dir)
    return {p.stem: tuple(read_csv(p)) for p in sorted(d.glob("*.csv"))}


def load(data_dir: Path | str | None = None) -> dict[str, tuple[Entry, ...]]:
    """All CSVs by file stem, in sorted order. Cached per directory (edit CSVs, restart)."""
    return _load(str(data_dir or DATA_DIR))


@dataclass(frozen=True)
class Rules:
    """The ``boundaries.csv`` rows: per-label boundary switches."""

    table: dict

    def get(self, key: str, label: str, default: str = "") -> str:
        return self.table.get((key, label), default)

    def case_ending(self, label: str) -> str:
        return self.get("@case_ending", label, "include")

    def int_of(self, key: str, label: str, default: int) -> int:
        raw = self.get(key, label, str(default))
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"boundaries.csv: {key} for {label} must be an integer, got {raw!r}") from None


def load_rules(data_dir: Path | str | None = None) -> Rules:
    rows = load(data_dir).get("boundaries", ())
    return Rules({(e.term, e.label): e.boundary for e in rows if e.match == "rule"})
