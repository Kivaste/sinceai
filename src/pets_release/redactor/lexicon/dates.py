"""DATE (numeric and written dates) and AGE (the number only, never the unit or the cue)."""

from __future__ import annotations

import re

from .base import LexiconPass
from .loader import Rules

_END = r"(?:ta|tä|n|ssa|ssä|sta|stä|lla|llä|lta|ltä|lle|ksi|na|nä|s)?"


def _valid_dm(d: str, m: str) -> bool:
    return 1 <= int(d) <= 31 and 1 <= int(m) <= 12


class DatePass(LexiconPass):
    name = "lexicon.date"
    label = "DATE"

    def __init__(self, entries: dict, rules: Rules):
        self.trailing_dot = rules.get("@date_trailing_dot", "DATE", "include") != "exclude"
        months = [e.term for e in entries.get("dates", ()) if e.match == "month"]
        stems_ = [e.term for e in entries.get("dates", ()) if e.match == "month-stem"]
        abbr = [e.term for e in entries.get("dates", ()) if e.match == "month-abbr"]
        full = "|".join(sorted(map(re.escape, months), key=len, reverse=True))
        stem = "|".join(sorted(map(re.escape, stems_), key=len, reverse=True))
        ab = "|".join(sorted(map(re.escape, abbr), key=len, reverse=True))
        mon = rf"(?:(?:{full}){_END}|(?:{stem})kuu{_END}|(?:{ab})\.?)"
        self.mon = mon
        f = re.IGNORECASE
        self.numeric = re.compile(r"(?<![\d.,/-])(\d{1,2})\.\s?(\d{1,2})\.(?:\s?(\d{4}|\d{2})(?![\d]))?(?![\d])")
        self.iso = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
        self.slash = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])")
        self.d_mon = re.compile(rf"(?<![\d.])(\d{{1,2}})(?:st|nd|rd|th)?\.?\s+(?:of\s+)?{mon}(?:\s+(\d{{4}}))?(?![\w])", f)
        self.mon_d = re.compile(rf"(?<![\w]){mon}\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{{4}})(?!\d))?", f)

    def find(self, text: str) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for m in self.numeric.finditer(text):
            if _valid_dm(m.group(1), m.group(2)):
                out.append(self._trim(text, m.start(), m.end()))
        for m in self.iso.finditer(text):
            if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
                out.append((m.start(), m.end()))
        for m in self.slash.finditer(text):
            if _valid_dm(m.group(1), m.group(2)) or _valid_dm(m.group(2), m.group(1)):
                out.append((m.start(), m.end()))
        for m in self.d_mon.finditer(text):
            if 1 <= int(m.group(1)) <= 31:
                out.append((m.start(), m.end()))
        for m in self.mon_d.finditer(text):
            if 1 <= int(m.group(1)) <= 31:
                out.append(self._trim(text, m.start(), m.end()))
        return out

    def _trim(self, text: str, s: int, e: int) -> tuple[int, int]:
        if not self.trailing_dot and text[e - 1] == ".":
            e -= 1
        return s, e


_N = r"(?P<n>\d{1,3})(?!\d)"
_AGE_PATTERNS = [
    rf"(?<![\d.,]){_N}\s?-\s?vuotia\w*",
    rf"(?<![\d.,]){_N}\s?(?:-\s?)?(?:year|yr)s?[- ]old",
    rf"(?<![\d.,]){_N}\s+years?\s+of\s+age",
    rf"(?<![\d.,]){_N}\s+(?:vuotta|v\.?)\s+vanha\w*",
    rf"(?<![\d.,]){_N}\s+år\s+gammal",
    rf"(?<![\d.,]){_N}\s?-\s?årig\w*",
    rf"(?<![\d.,]){_N}\s?(?:y/o|yo)(?![\w])",
    rf"\b(?:olen|oon|oli|täytän|täytin|täyttää|täyttäisin)\s+{_N}(?=\s*(?:vuotta|vuotias|v\b|ja\b|,|\.|!|\?|$))",
    rf"\b(?:I\s+am|I'm|im|i\s+turn|turning)\s+{_N}(?=\s*(?:years?|yo\b|y/o|and\b|,|\.|!|\?|$))",
    rf"\bjag\s+är\s+{_N}(?=\s*(?:år|och\b|,|\.|!|\?|$))",
    rf"\b(?:aged?|age\s+of|age:?)\s+{_N}",
    rf"\bik[äa](?:ni|si|nsä)?(?:\s+on|:)?\s+{_N}",
    rf"\b(?:on|oli|olen|olet|ovat)\s+{_N}\s+vuo(?:tta|den)(?!\s*(?:sitten|voimassa|asiakas|ollut|jälkeen|aiemmin|sopimus|kestänyt|käyttänyt|palvellut))",
]


class AgePass(LexiconPass):
    name = "lexicon.age"
    label = "AGE"

    def __init__(self, entries: dict, rules: Rules):
        self.res = [re.compile(p, re.IGNORECASE) for p in _AGE_PATTERNS]

    def find(self, text: str) -> list[tuple[int, int]]:
        out = []
        for rx in self.res:
            for m in rx.finditer(text):
                if 0 < int(m.group("n")) <= 120:
                    out.append((m.start("n"), m.end("n")))
        return out
