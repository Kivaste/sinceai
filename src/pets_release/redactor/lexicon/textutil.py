"""Tokens, Finnish/Swedish case endings and a stem index for inflected lookups."""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
_VOWELS = "aeiouyäöå"


@dataclass(frozen=True)
class Tok:
    start: int
    end: int
    text: str

    @property
    def low(self) -> str:
        return self.text.lower()

    @property
    def cap(self) -> bool:
        return self.text[:1].isupper()


def tokens(text: str) -> list[Tok]:
    return [Tok(m.start(), m.end(), m.group()) for m in TOKEN_RE.finditer(text)]


def sentence_start(text: str, pos: int) -> bool:
    """True when ``pos`` begins a sentence (only whitespace / quotes / brackets before it, or after . ! ? : newline)."""
    i = pos - 1
    while i >= 0 and (text[i] in " \t\"'“”‘’([«-" or text[i] == " "):
        i -= 1
    return i < 0 or text[i] in ".!?:\n\r"


_BASE_ENDINGS = ["n", "a", "ä", "ta", "tä", "na", "nä", "ssa", "ssä", "sta", "stä", "lla", "llä", "lta", "ltä", "lle", "ksi", "tta", "ttä", "han", "hen", "hin", "hon", "hyn", "hän", "seen", "een", "in", "ien", "iden", "ten", "iin", "ille", "illa", "illä", "ina", "inä", "ine", "ineen", "ia", "iä", "ja", "jä", "je", "s", "es", "ens", "en", "et", "ets", "ssaan", "ssään", "lleen", "ltaan", "sta", "sen", "sin", "ista", "istä", "issa", "issä", "ilta", "iltä", "ihin", "ihmin", "hyvin"]
CASE_ENDINGS: frozenset[str] = frozenset(
    {""}
    | set(_BASE_ENDINGS)
    | {"e" + e for e in ("lla", "llä", "lta", "ltä", "lle", "sta", "stä", "ssa", "ssä", "ksi", "na", "nä", "tta", "ttä", "n", "a", "ä")}
    | {"'s", "’s", "n'", ":n", ":lle", ":ssa", ":sta"}
)

_GRADATION = (("kk", "k"), ("pp", "p"), ("tt", "t"), ("nk", "ng"), ("mp", "mm"), ("nt", "nn"), ("lt", "ll"), ("rt", "rr"), ("ht", "hd"), ("rk", "r"), ("lk", "l"))


def stems(lemma: str) -> set[str]:
    """Stem variants of a lemma: itself, vowel-dropped, -nen -> -se, consonant gradation, i -> e."""
    w = lemma.lower()
    out = {w}
    if len(w) > 4 and w.endswith("nen"):
        out |= {w[:-3] + "se", w[:-3] + "s"}
    if len(w) > 3 and w.endswith("s") and w[-2] in _VOWELS:
        out.add(w[:-1] + "kse")
    base = set(out)
    for s in base:
        if len(s) > 3 and s[-1] in _VOWELS:
            out.add(s[:-1])
    for s in set(out):
        core = s.rstrip(_VOWELS)
        vow = s[len(core):]
        if not vow or not core:
            continue
        for strong, weak in _GRADATION:
            if core.endswith(strong) and len(core) > len(strong):
                out.add(core[: -len(strong)] + weak + vow)
                out.add(core[: -len(strong)] + weak + vow[:-1] + "e" if vow.endswith("i") else core[: -len(strong)] + weak + vow)
        if vow.endswith("i") and len(s) > 3:
            out.add(s[:-1] + "e")
    return {s for s in out if len(s) >= 2}


class StemIndex:
    """Maps stems (and their case endings) back to the kinds of the lemmas they came from."""

    def __init__(self) -> None:
        self._d: dict[str, set[str]] = {}

    def add(self, lemma: str, kind: str) -> None:
        for s in stems(lemma):
            self._d.setdefault(s, set()).add(kind)
        self._d.setdefault(lemma.lower(), set()).add(kind)

    def __len__(self) -> int:
        return len(self._d)

    def match(self, token: str) -> tuple[frozenset[str], int] | None:
        """(kinds, length of the matched stem in ``token``) for the longest stem + allowed ending, else None."""
        cf = token.lower()
        n = len(cf)
        hit = self._match_one(cf)
        if hit:
            return hit
        if "-" in cf and not cf.startswith("-") and not cf.endswith("-"):
            kinds: set[str] = set()
            for part in cf.split("-"):
                h = self._match_one(part)
                if not h:
                    return None
                kinds |= h[0]
            return frozenset(kinds), n
        return None

    def _match_one(self, cf: str) -> tuple[frozenset[str], int] | None:
        n = len(cf)
        for L in range(n, 1, -1):
            kinds = self._d.get(cf[:L])
            if not kinds:
                continue
            tail = cf[L:]
            if L == n or (L >= 3 and tail in CASE_ENDINGS):
                return frozenset(kinds), L
        return None
