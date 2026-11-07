"""Gate health lexicon: versioned, editable CSV, canonical digest for the manifest.

The lexicon holds general-knowledge health terms (en/fi/sv) only; never terms taken from
kit rows. ``match`` is ``prefix`` (term at a word start, any letters may follow, to cover
inflection) or ``exact`` (whole word).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

LEXICON_NAME = "gate-health"
LEXICON_VERSION = "2026.11.1"
LEXICON_PATH = Path(__file__).with_name("data") / "health_lexicon.csv"
HEADER = ["term", "lang", "match"]


class LexiconError(Exception):
    pass


def load_rows(path: Path = LEXICON_PATH):
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header != HEADER:
            raise LexiconError("health lexicon header mismatch")
        rows = []
        for r in reader:
            if not r or not "".join(r).strip():
                continue
            if len(r) != 3 or r[2] not in ("prefix", "exact") or not r[0].strip():
                raise LexiconError("malformed health lexicon row")
            rows.append((r[0].strip().lower(), r[1].strip(), r[2]))
    if not rows:
        raise LexiconError("empty health lexicon")
    return sorted(set(rows))


def digest(path: Path = LEXICON_PATH) -> str:
    """sha256 over canonical JSON of {name, version, rows sorted}; line-ending independent."""
    body = {"name": LEXICON_NAME, "version": LEXICON_VERSION,
            "rows": [list(r) for r in load_rows(path)]}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@lru_cache(maxsize=4)
def _pattern(path_str: str):
    alts = []
    for term, _lang, match in load_rows(Path(path_str)):
        t = re.escape(term)
        alts.append(t + r"[^\W\d_]*" if match == "prefix" else t + r"(?![^\W\d_])")
    alts.sort(key=len, reverse=True)
    return re.compile(r"(?<![^\W\d_])(?:" + "|".join(alts) + ")", re.IGNORECASE)


def health_terms(text: str, path: Path = LEXICON_PATH):
    return [(m.start(), m.end()) for m in _pattern(str(path)).finditer(text)]
