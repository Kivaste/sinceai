"""LOCATION (towns, countries, regions, landmarks) and ORG (known names, legal-form names, cue + capitalised run)."""

from __future__ import annotations

import re

from ..passes import PRIORITY_LEXICON
from .base import LexiconPass
from .gazetteer import Gazetteer
from .loader import Rules
from .person import _cue_re
from .textutil import StemIndex, sentence_start, tokens

_STOP = frozenset(
    ["ja", "and", "och", "mutta", "but", "koska", "because", "että", "that", "kun", "when", "jos", "if", "ei", "en", "et", "haluan", "haluaisin", "tarvitsen", "voitteko", "voisitko", "sitten", "niin", "mä", "minä", "me", "i", "we", "my", "so", "please", "kiitos", "nyt", "kanssa", "with", "eli", "tai", "or", "vai", "sillä", "jotta", "enkä", "kyllä", "joo", "mutta", "olen", "on", "oli", "ovat", "kuin", "the", "a", "an", "is", "was"]
)


class LocationPass(LexiconPass):
    name = "lexicon.location"
    label = "LOCATION"

    def __init__(self, entries: dict, rules: Rules, gazetteer: Gazetteer | None = None):
        self.index = StemIndex()
        self.names = StemIndex()  # person names: a minor place that is also a name is read as a name
        for k in ("names_given", "names_family"):
            for e in entries.get(k, ()):
                self.names.add(e.term, "name")
        if gazetteer:
            for n in gazetteer.given | gazetteer.family:
                self.names.add(n, "name")
        for e in entries.get("places", ()):
            if e.match == "lemma":
                self.index.add(e.term, "place-minor" if e.notes == "municipality" else "place")
        if gazetteer:
            for c in gazetteer.cities:
                self.index.add(c, "place")
        self.deny = frozenset(e.term.lower() for e in entries.get("denylist", ()) if e.match == "deny")
        self.exclude_ending = rules.case_ending("LOCATION") == "exclude"
        self.cue = _cue_re([e.term for e in entries.get("places", ()) if e.match == "cue-strong"])
        names = {e.term.lower() for k in ("names_given", "names_family", "orgs") for e in entries.get(k, ())}
        self.not_places = self.deny | frozenset(names)
        self.place_end = re.compile(r"(?:ssa|ssä|sta|stä|lla|llä|lta|ltä|lle|seen|han|hen|hin|iin|ssa|n)$", re.IGNORECASE)

    def is_known(self, word: str) -> bool:
        return self.index.match(word) is not None

    def find(self, text: str) -> list[tuple[int, int]]:
        out = []
        for t in tokens(text):
            m = self.index.match(t.text)
            if not m:
                continue
            if t.low in self.deny and (not t.cap or sentence_start(text, t.start)):
                continue
            if not t.cap and m[1] < 5:
                continue
            if "place" not in m[0] and self.names.match(t.text):
                continue
            out.append((t.start, t.start + m[1] if self.exclude_ending else t.end))
        if self.cue:
            for t in tokens(text):
                if not t.cap or len(t.text) < 4 or t.low in self.not_places or sentence_start(text, t.start):
                    continue
                if self.index.match(t.text) or not self.cue.search(text[max(0, t.start - 40): t.start]):
                    continue
                if self.place_end.search(t.text):
                    out.append((t.start, t.end))
        return out


class OrgPass(LexiconPass):
    name = "lexicon.org"
    label = "ORG"
    priority = PRIORITY_LEXICON + 5

    def __init__(self, entries: dict, rules: Rules, gazetteer: Gazetteer | None = None):
        orgs = entries.get("orgs", ())
        phrases = [e.term for e in orgs if e.match == "phrase"]
        self.exclude_ending = rules.case_ending("ORG") == "exclude"
        short = [p for p in phrases if len(p) <= 3]
        long_ = [p for p in phrases if len(p) > 3]
        tail = r"(?P<end>[^\W\d_]{0,6})" if not self.exclude_ending else r"(?P<end>)"
        self.long_re = (
            re.compile(r"(?<![\w-])(?:" + "|".join(sorted(map(re.escape, long_), key=len, reverse=True)) + r")" + tail + r"(?![\w-])", re.IGNORECASE)
            if long_
            else None
        )
        self.short_re = (
            re.compile(r"(?<![\w-])(?:" + "|".join(sorted(map(re.escape, short), key=len, reverse=True)) + r")(?![\w-])") if short else None
        )
        suffixes = [e.term for e in orgs if e.match == "legal-suffix"]
        alt = "|".join(sorted(map(re.escape, suffixes), key=len, reverse=True))
        self.legal_re = re.compile(r"(?<![\w-])(?:" + alt + r")(?![\w])") if suffixes else None
        self.lower_run = rules.int_of("@org_lower_run", "ORG", 3)
        self.cue = _cue_re([e.term for e in orgs if e.match == "cue-strong" and e.boundary != "multi"])
        self.cue_multi = _cue_re([e.term for e in orgs if e.match == "cue-strong" and e.boundary == "multi"])
        self.deny = frozenset(e.term.lower() for e in entries.get("denylist", ()) if e.match == "deny")
        self.controller = frozenset(e.term.lower() for e in entries.get("denylist", ()) if e.notes.startswith("controller"))
        weak = {e.term.lower() for e in entries.get("cues", ()) if e.match == "cue-weak"}
        self.stop_lead = self.deny | frozenset(weak) | {"asiakas"}

    def find(self, text: str) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for rx in (self.long_re, self.short_re):
            if rx:
                for m in rx.finditer(text):
                    if self._controller(text[m.start():m.end()]):
                        continue
                    out.append((m.start(), m.end()))
        toks = tokens(text)
        # legal-form names: capitalised words (up to 4) ending in Oy/Ltd/...
        if self.legal_re:
            for m in self.legal_re.finditer(text):
                j = None
                for idx, t in enumerate(toks):
                    if t.start >= m.start():
                        j = idx
                        break
                if j is None:
                    continue
                start_i = j
                while start_i > 0 and j - start_i < 4:
                    p = toks[start_i - 1]
                    if not p.cap or text[p.end:toks[start_i].start] not in (" ", " & ", "-"):
                        break
                    start_i -= 1
                words = list(range(start_i, j))
                while words and (toks[words[0]].low in self.stop_lead) and (sentence_start(text, toks[words[0]].start) or True):
                    words.pop(0)
                if not words:
                    continue
                s, e = toks[words[0]].start, m.end()
                if self._controller(text[s:e]):
                    continue
                out.append((s, e))
        # cue + run (capitalised run, or a short lower-case run for ASR output)
        if self.cue or self.cue_multi:
            for idx, t in enumerate(toks):
                window = text[max(0, t.start - 40): t.start]
                plain = bool(self.cue and self.cue.search(window))
                multi = bool(self.cue_multi and self.cue_multi.search(window))
                if not (plain or multi):
                    continue
                if t.low in _STOP or (not t.cap and t.low in self.stop_lead):
                    continue
                limit = 4 if t.cap else self.lower_run
                end_i = idx
                while end_i + 1 < len(toks) and end_i - idx < limit - 1:
                    nxt = toks[end_i + 1]
                    if text[toks[end_i].end:nxt.start] != " " or nxt.low in _STOP or (t.cap and not nxt.cap):
                        break
                    end_i += 1
                e = toks[end_i].end
                if end_i + 1 < len(toks) and self.legal_re and self.legal_re.match(text, toks[end_i + 1].start) and text[e:toks[end_i + 1].start] == " ":
                    e = toks[end_i + 1].end
                if multi and not plain and end_i == idx and e == t.end:
                    continue
                if not self._controller(text[t.start:e]):
                    out.append((t.start, e))
        return out

    def _controller(self, s: str) -> bool:
        return any(w.lower() in self.controller for w in re.findall(r"[^\W\d_]+", s))
