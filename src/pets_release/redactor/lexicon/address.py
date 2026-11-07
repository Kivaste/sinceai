"""ADDRESS: street word + number (+ staircase / apartment), absorbing a contiguous postcode and town."""

from __future__ import annotations

import re

from ..passes import PRIORITY_LEXICON
from .base import LexiconPass
from .gazetteer import Gazetteer
from .loader import Rules
from .textutil import StemIndex, tokens

_NUM = r"\d{1,3}(?!\d)[A-Za-zÅÄÖåäö]?(?![\w])(?:\s?[-–]\s?\d{1,3}(?!\d))?"
_APT_MARK = r"(?:as\.?|asunto|huoneisto|lgh|apt\.?|flat)"
_UNIT = rf"(?:\s+{_APT_MARK}\s*\d{{1,3}}(?!\d)|\s+[A-ZÅÄÖ](?![\w])(?:\s+\d{{1,3}}(?![\d\w]))?)?"
_POST = r"(?:,?\s+(?P<pc>\d{5})(?!\d)(?:\s+(?P<town>[^\W\d_][\w-]*))?)?"
_TAIL = re.compile(rf"\s+(?P<num>{_NUM}){_UNIT}{_POST}", re.IGNORECASE)
_ENGLISH = re.compile(
    r"(?<![\w-])\d{1,4}[A-Za-z]?\s+(?:[A-Z][a-z]+\s+){1,2}(?:Street|Road|Avenue|Lane|Drive|Close|Way|St\.|Rd\.|Ave\.)(?![\w])"
)
_STANDALONE_POST = re.compile(r"(?<![\w-])(?P<pc>\d{5})(?!\d)\s+(?P<town>[^\W\d_][\w-]*)")


class AddressPass(LexiconPass):
    name = "lexicon.address"
    label = "ADDRESS"
    priority = PRIORITY_LEXICON + 10

    def __init__(self, entries: dict, rules: Rules, gazetteer: Gazetteer | None, is_town):
        sfx = [e.term for e in entries.get("streets", ()) if e.match == "street"]
        self.absorb = rules.get("@postcode_town", "ADDRESS", "absorb") == "absorb"
        alt = "|".join(sorted(map(re.escape, sfx), key=len, reverse=True))
        # a street word: at least two letters before the street ending, up to six letters of case ending after it
        self.street_re = re.compile(rf"(?<![\w-])([^\W\d_][\w-]*?[^\W\d_](?:{alt})[^\W\d_]{{0,6}})(?=\s+\d)", re.IGNORECASE)
        self.streets = StemIndex()
        if gazetteer:
            for s in gazetteer.streets:
                self.streets.add(s, "street")
        self.is_town = is_town

    def _tail(self, text: str, pos: int):
        m = _TAIL.match(text, pos)
        if not m:
            return None
        end = m.end()
        if m.group("pc") and m.group("town"):
            town = m.group("town")
            if not (town[:1].isupper() or self.is_town(town)):
                end = m.start("town") - 0
                # keep only the postcode; strip the whitespace in front of the rejected word
                end = m.start("town")
                while end > 0 and text[end - 1].isspace():
                    end -= 1
        if not self.absorb and m.group("pc"):
            cut = m.start("pc")
            end = cut
            while end > 0 and text[end - 1] in " ,":
                end -= 1
        return end

    def find(self, text: str) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for m in self.street_re.finditer(text):
            end = self._tail(text, m.end(1))
            if end:
                out.append((m.start(1), end))
        if len(self.streets):
            for t in tokens(text):
                if self.streets.match(t.text):
                    end = self._tail(text, t.end)
                    if end:
                        out.append((t.start, end))
        for m in _ENGLISH.finditer(text):
            out.append((m.start(), m.end()))
        if self.absorb:
            for m in _STANDALONE_POST.finditer(text):
                if self.is_town(m.group("town")):
                    out.append((m.start(), m.end()))
        return out
