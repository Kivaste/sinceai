"""Gate normaliser: an independent implementation, sharing no code with the redactor.

Per turn it builds two views:

* the *digit view*: placeholders masked, spoken digits (fi/sv/en) converted when they sit
  next to another digit, spoken separators (dash/plus/slash/dot words) converted when they
  sit next to a digit;
* the *email view*: placeholders masked, spoken "at" and "dot" words replaced by marker
  characters so that only spelled-out emails use them, spoken dash/underscore converted.

Per conversation, :func:`windows` yields joins of up to three consecutive turns so a fragment
that ends one turn and one that starts a later turn form one candidate.
"""
from __future__ import annotations

import re

# A typed, numbered placeholder such as [PHONE_1]; also bare [PHONE]. Masked with a
# non-space, non-word character so it can neither be a hit nor bridge two fragments.
PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z_]*(?:_\d+)?\]")
MASK = " ¦ "

SPOKEN_AT = "\x01"
SPOKEN_DOT = "\x02"

DIGIT_WORDS = {
    # en
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # fi
    "nolla": "0", "yksi": "1", "kaksi": "2", "kolme": "3", "neljä": "4",
    "viisi": "5", "kuusi": "6", "seitsemän": "7", "kahdeksan": "8", "yhdeksän": "9",
    # sv
    "noll": "0", "ett": "1", "en": "1", "två": "2", "tre": "3", "fyra": "4",
    "fem": "5", "sex": "6", "sju": "7", "åtta": "8", "nio": "9",
}

DASH_WORDS = {"viiva", "väliviiva", "miinus", "streck", "bindestreck", "minus", "dash", "hyphen"}
PLUS_WORDS = {"plus", "plussa"}
SLASH_WORDS = {"slash", "kauttaviiva", "snedstreck"}
DOT_WORDS = {"dot", "piste", "punkt", "point"}
AT_WORDS = {"at", "ät", "miukumauku", "kissanhäntä", "snabela", "atmerkki", "at-merkki"}
UNDERSCORE_WORDS = {"underscore", "alaviiva", "understreck"}

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
_SKIPPABLE = {"-", "+", "/", ".", "(", ")", ",", ":"}


def mask_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub(MASK, text)


def _has_digit(tok: str) -> bool:
    return any(ch.isdigit() for ch in tok)


def _neighbour(toks, i, step, separator_words):
    j = i + step
    while 0 <= j < len(toks):
        t = toks[j].group(0)
        low = t.lower()
        if t in _SKIPPABLE or low in separator_words:
            j += step
            continue
        return low
    return None


def _digitish(tok) -> bool:
    return tok is not None and (_has_digit(tok) or tok in DIGIT_WORDS)


def digit_view(text: str) -> str:
    text = mask_placeholders(text)
    toks = list(_TOKEN_RE.finditer(text))
    seps = DASH_WORDS | PLUS_WORDS | SLASH_WORDS | DOT_WORDS
    out = []
    last = 0
    for i, m in enumerate(toks):
        low = m.group(0).lower()
        rep = None
        if low in DIGIT_WORDS:
            if _digitish(_neighbour(toks, i, -1, seps)) or _digitish(_neighbour(toks, i, 1, seps)):
                rep = DIGIT_WORDS[low]
        elif low in seps and _digitish(_neighbour(toks, i, 1, seps)) and (
            _digitish(_neighbour(toks, i, -1, seps)) or low in PLUS_WORDS or low in DASH_WORDS
        ):
            if low in DASH_WORDS:
                rep = "-"
            elif low in PLUS_WORDS:
                rep = "+"
            elif low in SLASH_WORDS:
                rep = "/"
            else:
                rep = "."
        if rep is not None:
            out.append(text[last:m.start()])
            out.append(rep)
            last = m.end()
    out.append(text[last:])
    return "".join(out)


_SNABEL_RE = re.compile(r"(?i)\bsnabel-a\b|\bat-merkki\b")


def email_view(text: str) -> str:
    text = _SNABEL_RE.sub(lambda m: " at ", mask_placeholders(text))
    text = digit_view(text)
    toks = list(_TOKEN_RE.finditer(text))
    out = []
    last = 0
    for m in toks:
        low = m.group(0).lower()
        rep = None
        if low in AT_WORDS:
            rep = SPOKEN_AT
        elif low in DOT_WORDS:
            rep = SPOKEN_DOT
        elif low in DASH_WORDS:
            rep = "-"
        elif low in UNDERSCORE_WORDS:
            rep = "_"
        if rep is not None:
            out.append(text[last:m.start()])
            out.append(rep)
            last = m.end()
    out.append(text[last:])
    return "".join(out)


def windows(n_turns: int, has_digit):
    """Turn-index windows for N-turn joins (window <= 3 turns).

    Yields tuples of turn positions: (k, k+1); (k, k+2) skipping a middle turn that holds
    no digit (a backchannel such as "ok"); and (k, k+1, k+2).
    """
    for k in range(n_turns):
        if k + 1 < n_turns:
            yield (k, k + 1)
        if k + 2 < n_turns:
            if not has_digit(k + 1):
                yield (k, k + 2)
            yield (k, k + 1, k + 2)


def join(views, idx):
    """Join the views at positions idx with a single space; return text and turn bounds."""
    parts = []
    bounds = []
    pos = 0
    for n, i in enumerate(idx):
        if n:
            parts.append(" ")
            pos += 1
        parts.append(views[i])
        bounds.append((pos, pos + len(views[i]), i))
        pos += len(views[i])
    return "".join(parts), bounds
