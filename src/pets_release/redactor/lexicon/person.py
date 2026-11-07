"""PERSON: gazetteer + general name lexicon + cues + case endings.

A name token is accepted when (a) it is capitalised and known (gazetteer or lexicon), or (b) it is known
and either follows a cue or forms a known given+family pair (ASR output is often lower-case), or (c) it
is a capitalised unknown word right after a *strong* cue ("nimeni on", "my name is"). Cue words are never
part of the span. Common words that are also names (``denylist.csv``) are never names when lower-case or
sentence-initial.
"""

from __future__ import annotations

import re

from .base import LexiconPass
from .gazetteer import Gazetteer
from .loader import Rules
from .textutil import StemIndex, Tok, sentence_start, tokens

_GAP_ONE_SPACE = re.compile(r"^ $")


def _cue_re(phrases: list[str]) -> re.Pattern | None:
    if not phrases:
        return None
    alt = "|".join(sorted((re.escape(p) for p in phrases), key=len, reverse=True))
    return re.compile(r"(?:^|(?<=[\s,;:(\"“]))(?:" + alt + r")[\s,:;-]*$", re.IGNORECASE)


class PersonPass(LexiconPass):
    name = "lexicon.person"
    label = "PERSON"

    def __init__(self, entries: dict, rules: Rules, gazetteer: Gazetteer | None = None):
        self.index = StemIndex()
        for e in entries.get("names_given", ()):
            self.index.add(e.term, "given")
            self.index.add(e.term, "lex")
        for e in entries.get("names_family", ()):
            self.index.add(e.term, "family")
            self.index.add(e.term, "lex")
        self.parties = gazetteer.party_names() if gazetteer else {}
        if gazetteer:
            for n in gazetteer.given:
                self.index.add(n, "given")
                self.index.add(n, "gz")
            for n in gazetteer.family:
                self.index.add(n, "family")
                self.index.add(n, "gz")
        cues = entries.get("cues", ())
        self.strong = _cue_re([e.term for e in cues if e.match == "cue-strong" and e.label == "PERSON"])
        self.weak = _cue_re([e.term for e in cues if e.match == "cue-weak" and e.label == "PERSON"])
        self.deny = frozenset(e.term.lower() for e in entries.get("denylist", ()) if e.match == "deny")
        self.exclude_ending = rules.case_ending("PERSON") == "exclude"
        self.lower_mode = rules.get("@person_lowercase", "PERSON", "cue")
        self.gz_cap = rules.get("@person_gz_capitalised", "PERSON", "any")
        self.merge = rules.get("@person_merge", "PERSON", "merge") != "split"
        # words that must never be taken as an unknown name after a strong cue
        self.not_names = self.deny | frozenset(
            e.term.lower() for k in ("places", "orgs") for e in entries.get(k, ()) if " " not in e.term
        )

    # ------------------------------------------------------------------
    def _cue_before(self, text: str, tok: Tok, pat: re.Pattern | None) -> bool:
        if pat is None:
            return False
        window = text[max(0, tok.start - 40): tok.start]
        return bool(pat.search(window))

    def run(self, view):
        party = None
        names = self.parties.get(view.conversation_id)
        if names:
            party = StemIndex()
            for full in names:
                for part in re.findall(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", full):
                    party.add(part, "party")
        self._party = party
        yield from super().run(view)

    _party = None

    def find(self, text: str) -> list[tuple[int, int]]:
        toks = tokens(text)
        n = len(toks)
        known: list[tuple[frozenset[str], int] | None] = [self.index.match(t.text) for t in toks]
        denied = [self._denied(text, t) for t in toks]
        accepted = [False] * n
        lens = [t.end - t.start for t in toks]

        run = [0] * n  # position inside a capitalised run that starts right after a strong cue (1-based, max 3)
        for i, t in enumerate(toks):
            if self._cue_before(text, t, self.strong):
                run[i] = 1
            elif i > 0 and run[i - 1] and run[i - 1] < 3 and t.cap and text[toks[i - 1].end:t.start] == " ":
                run[i] = run[i - 1] + 1
            k = known[i]
            if k and denied[i]:
                k = None
            in_party = bool(self._party and self._party.match(t.text))
            if k is None and in_party and not denied[i] and (t.cap or len(t.text) >= 4):
                k = (frozenset({"party"}), len(t.text))
            if k:
                gz_only = "lex" not in k[0] and not in_party
                if t.cap:
                    accepted[i] = not (gz_only and self.gz_cap == "party" and not run[i] and not self._cue_before(text, t, self.weak))
                elif k[1] >= 4 and (
                    self.lower_mode == "known"
                    or (self.lower_mode == "gazetteer" and "gz" in k[0])
                    or (self.lower_mode == "party" and (in_party or ("gz" in k[0] and not self.parties)))
                    or self._cue_before(text, t, self.weak)
                    or run[i]
                    or self._pair(toks, known, denied, i)
                ):
                    accepted[i] = True
                if accepted[i] and self.exclude_ending:
                    lens[i] = k[1]
            elif run[i] and t.cap and not denied[i] and t.low not in self.not_names:
                accepted[i] = True

        spans: list[tuple[int, int]] = []
        cur_s = cur_e = None
        for i, t in enumerate(toks):
            if not accepted[i]:
                if cur_s is not None:
                    spans.append((cur_s, cur_e))
                    cur_s = cur_e = None
                continue
            end = t.start + lens[i]
            if cur_s is not None and self.merge and text[toks[i - 1].end:t.start] == " " and accepted[i - 1]:
                cur_e = end
            else:
                if cur_s is not None:
                    spans.append((cur_s, cur_e))
                cur_s, cur_e = t.start, end
        if cur_s is not None:
            spans.append((cur_s, cur_e))
        return spans

    def _denied(self, text: str, t: Tok) -> bool:
        low = t.low
        if low in self.deny:
            return (not t.cap) or sentence_start(text, t.start)
        return False

    def _pair(self, toks, known, denied, i) -> bool:
        """Lower-case known token next to another known, non-denied token separated by one space."""
        for j in (i - 1, i + 1):
            if 0 <= j < len(toks) and known[j] and not denied[j]:
                a, b = (toks[j], toks[i]) if j < i else (toks[i], toks[j])
                if b.start - a.end == 1:
                    return True
        return False
