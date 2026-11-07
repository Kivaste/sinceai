"""Gate normaliser: an independent implementation, sharing no code with the redactor.

Two views of a text:

* the *digit view*: placeholders masked, spoken digits (fi/sv/en) converted when they sit
  next to another digit, spoken separators (dash/plus/slash/dot words) converted when they
  sit next to a digit;
* the *email view*: the digit view plus spoken "at" and "dot" words replaced by marker
  characters (so only spelled-out emails use them) and spoken dash/underscore converted.

Views are always computed from source text. For N-turn joins the *source* turns are joined
first and the join is normalised as one text, so a spoken identifier split at any position
(after its first digit, mid-group, at a spoken separator) normalises exactly as if unsplit.
``view(text, kind, with_map=True)`` also returns, per output character, the source span it
came from, so hits are located in source turns.
"""
from __future__ import annotations

import re

import pets_release.checks._cues as _cues

# An exact redactor placeholder such as [PHONE_1] (label from the span-label list, n >= 1);
# also bare [PHONE]. Masked with a non-space, non-word character so it can neither be a hit
# nor bridge two fragments. Any other bracketed token ("[A_1]", "[Hunter2!]") stays text.
PLACEHOLDER_RE = _cues.PLACEHOLDER_RE
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
AT_WORDS = {"at", "ät", "miukumauku", "kissanhäntä", "snabela"}
UNDERSCORE_WORDS = {"underscore", "alaviiva", "understreck"}
_SEP_WORDS = DASH_WORDS | PLUS_WORDS | SLASH_WORDS | DOT_WORDS

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
_SKIPPABLE = {"-", "+", "/", ".", "(", ")", ",", ":"}
_SNABEL_RE = re.compile(r"(?i)\bsnabel-a\b|\bat-merkki\b")


# ---------------------------------------------------------------- edit machinery


def _apply(text, edits, with_map):
    """Apply sorted, non-overlapping (start, end, replacement) edits.

    Returns (out, starts, ends): for each output char, the source span [start, end) it maps to.
    """
    out = []
    starts, ends = ([], []) if with_map else (None, None)
    last = 0
    for s, e, rep in edits:
        out.append(text[last:s])
        out.append(rep)
        if with_map:
            starts.extend(range(last, s))
            ends.extend(range(last + 1, s + 1))
            starts.extend([s] * len(rep))
            ends.extend([e] * len(rep))
        last = e
    out.append(text[last:])
    if with_map:
        starts.extend(range(last, len(text)))
        ends.extend(range(last + 1, len(text) + 1))
    return "".join(out), starts, ends


def _mask_edits(text):
    return [(m.start(), m.end(), MASK) for m in PLACEHOLDER_RE.finditer(text)]


def _snabel_edits(text):
    return [(m.start(), m.end(), " at ") for m in _SNABEL_RE.finditer(text)]


def _has_digit(tok):
    return any(ch.isdigit() for ch in tok)


def _neighbour(toks, i, step):
    j = i + step
    while 0 <= j < len(toks):
        t = toks[j].group(0)
        if t in _SKIPPABLE or t.lower() in _SEP_WORDS:
            j += step
            continue
        return t.lower()
    return None


def _digitish(tok):
    return tok is not None and (_has_digit(tok) or tok in DIGIT_WORDS)


def _digit_edits(text):
    toks = list(_TOKEN_RE.finditer(text))
    edits = []
    for i, m in enumerate(toks):
        low = m.group(0).lower()
        rep = None
        if low in DIGIT_WORDS:
            if _digitish(_neighbour(toks, i, -1)) or _digitish(_neighbour(toks, i, 1)):
                rep = DIGIT_WORDS[low]
        elif low in _SEP_WORDS and _digitish(_neighbour(toks, i, 1)) and (
            _digitish(_neighbour(toks, i, -1)) or low in PLUS_WORDS or low in DASH_WORDS
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
            edits.append((m.start(), m.end(), rep))
    return edits


def _email_edits(text):
    edits = []
    for m in _TOKEN_RE.finditer(text):
        low = m.group(0).lower()
        if low in AT_WORDS:
            edits.append((m.start(), m.end(), SPOKEN_AT))
        elif low in DOT_WORDS:
            edits.append((m.start(), m.end(), SPOKEN_DOT))
        elif low in DASH_WORDS:
            edits.append((m.start(), m.end(), "-"))
        elif low in UNDERSCORE_WORDS:
            edits.append((m.start(), m.end(), "_"))
    return edits


_STAGES = {
    "digit": (_mask_edits, _digit_edits),
    "email": (_mask_edits, _snabel_edits, _digit_edits, _email_edits),
}


def view(text, kind, with_map=False):
    """Normalised view of ``text``; with_map also returns per-char source (starts, ends)."""
    starts = ends = None
    for stage in _STAGES[kind]:
        out, s2, e2 = _apply(text, stage(text), with_map)
        if with_map:
            if starts is None:
                starts, ends = s2, e2
            else:
                starts = [starts[i] for i in s2]
                ends = [ends[i - 1] for i in e2]
        text = out
    if with_map:
        return text, starts, ends
    return text


def source_span(starts, ends, s, e):
    """Source [start, end) of output span [s, e)."""
    return starts[s], ends[e - 1]


def mask_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub(MASK, text)


def digit_view(text: str) -> str:
    return view(text, "digit")


def email_view(text: str) -> str:
    return view(text, "email")


# ---------------------------------------------------------------- N-turn joins


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


def join(texts, idx):
    """Join the source texts at positions idx with one space; return text and turn bounds."""
    parts = []
    bounds = []
    pos = 0
    for n, i in enumerate(idx):
        if n:
            parts.append(" ")
            pos += 1
        parts.append(texts[i])
        bounds.append((pos, pos + len(texts[i]), i))
        pos += len(texts[i])
    return "".join(parts), bounds
