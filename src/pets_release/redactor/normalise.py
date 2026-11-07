"""Normalised view of a turn: spoken digits, letters and separators as symbols.

Each symbol keeps the code-point range of the original text it came from, so a
match on the normalised view projects back to exact original offsets. A *run*
is a maximal sequence of symbols separated only by gap characters (whitespace,
commas, dots, slashes, brackets) with at least one digit; runs never cross a
masked region (dates, prices, versions, already-claimed literals).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

DIGIT_WORDS: dict[str, str] = {}
for _d, _words in {
    "0": "nolla noll zero",
    "1": "yksi yks ett one",
    "2": "kaksi kaks två two",
    "3": "kolme tre three",
    "4": "neljä fyra four",
    "5": "viisi viis fem five",
    "6": "kuusi kuus sex six",
    "7": "seitsemän seittemän sju seven",
    "8": "kahdeksan kaheksan åtta eight",
    "9": "yhdeksän yheksän nio nine",
}.items():
    for _w in _words.split():
        DIGIT_WORDS[_w] = _d

SEPARATOR_WORDS: dict[str, str] = {
    w: "-" for w in ("viiva", "väliviiva", "tavuviiva", "streck", "bindestreck", "dash", "hyphen", "miinus", "minus")
}
SEPARATOR_WORDS["plus"] = "+"

# Finnish letter names (as read aloud); single letters are taken as themselves.
LETTER_NAMES: dict[str, str] = {
    "aa": "A", "bee": "B", "see": "C", "dee": "D", "ee": "E", "äf": "F", "gee": "G", "hoo": "H",
    "ii": "I", "jii": "J", "koo": "K", "äl": "L", "äm": "M", "än": "N", "oo": "O", "pee": "P",
    "kuu": "Q", "är": "R", "äs": "S", "tee": "T", "uu": "U", "vee": "V", "äks": "X", "yy": "Y",
    "cee": "C", "kaksoisvee": "W", "tset": "Z",
}

_TOKEN_RE = re.compile(r"[^\W_]+|\S")
_GAP_CHARS = set(",./()")


@dataclass(frozen=True)
class Token:
    index: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Sym:
    ch: str  # one normalised character: digit, upper-case letter, '-' or '+'
    start: int
    end: int
    tok: int


@dataclass(frozen=True)
class Run:
    turn_index: int
    syms: tuple[Sym, ...]
    first_tok: int
    last_tok: int
    words_before: int  # word tokens before the run in its turn
    words_after: int

    @property
    def text(self) -> str:
        return "".join(s.ch for s in self.syms)


def tokenize(text: str) -> list[Token]:
    return [Token(i, m.start(), m.end(), m.group()) for i, m in enumerate(_TOKEN_RE.finditer(text))]


def is_word(tok: Token) -> bool:
    return tok.text[0].isalnum()


def token_symbols(tok: Token) -> list[Sym] | None:
    """Symbols for one token, or None if the token is not part of the normalised number view."""
    t = tok.text
    low = t.lower()
    if low in DIGIT_WORDS:
        return [Sym(DIGIT_WORDS[low], tok.start, tok.end, tok.index)]
    if low in SEPARATOR_WORDS:
        return [Sym(SEPARATOR_WORDS[low], tok.start, tok.end, tok.index)]
    if t in ("-", "+", "–"):
        return [Sym("-" if t == "–" else t, tok.start, tok.end, tok.index)]
    if low in LETTER_NAMES:
        return [Sym(LETTER_NAMES[low], tok.start, tok.end, tok.index)]
    if len(t) == 1 and t.isascii() and t.isalpha():
        return [Sym(t.upper(), tok.start, tok.end, tok.index)]
    if len(t) == 2 and t.isascii() and t.isalpha() and t.isupper():
        return [Sym(c, tok.start + i, tok.start + i + 1, tok.index) for i, c in enumerate(t)]
    if t.isascii() and t.isalnum() and any(c.isdigit() for c in t):
        letters = sum(c.isalpha() for c in t)
        # 'FI49...' (IBAN), '210814A966S' (HETU) keep their letters; 'abc123'-like words are opaque.
        if letters <= 2 or re.fullmatch(r"[A-Za-z]{2}\d{2}[A-Za-z0-9]*", t) and letters <= 4:
            return [Sym(c.upper(), tok.start + i, tok.start + i + 1, tok.index) for i, c in enumerate(t)]
    return None


def turn_runs(turn_index: int, text: str, masks: list[tuple[int, int]]) -> list[Run]:
    toks = tokenize(text)

    def masked(tok: Token) -> bool:
        return any(tok.start < e and s < tok.end for s, e in masks)

    runs: list[Run] = []
    cur: list[Sym] = []
    cur_first = -1
    cur_last = -1

    def flush() -> None:
        nonlocal cur, cur_first, cur_last
        # separators stay in the run: a HETU fragment may start or end with its century sign;
        # matches (not runs) decide span boundaries
        if cur and any(s.ch.isdigit() for s in cur):
            runs.append(Run(turn_index, tuple(cur), cur[0].tok, cur[-1].tok, 0, 0))
        cur, cur_first, cur_last = [], -1, -1

    punct_gap = False  # a ',', '.', '/' or bracket since the last symbol token
    prev_literal = False  # the last symbol token was typed (digits), not spoken
    for tok in toks:
        if masked(tok):
            flush()
            punct_gap = False
            continue
        syms = token_symbols(tok)
        if syms is not None:
            literal = tok.text[0].isdigit()
            # typed groups separated by punctuation are separate values ('12 B 14, 20100'); spoken digit
            # sequences keep going across commas ('kaksi yksi, nolla kahdeksan')
            if cur and punct_gap and prev_literal and literal:
                flush()
            cur.extend(syms)
            punct_gap = False
            prev_literal = literal
            continue
        if tok.text in _GAP_CHARS and cur:
            # a bracket alone does not split typed groups: '(040) 123 4567' is one phone number
            if tok.text not in "()":
                punct_gap = True
            continue
        flush()
        punct_gap = False
    flush()

    word_idx = [t.index for t in toks if is_word(t)]
    out = []
    for r in runs:
        before = sum(1 for i in word_idx if i < r.first_tok)
        after = sum(1 for i in word_idx if i > r.last_tok)
        out.append(Run(r.turn_index, r.syms, r.first_tok, r.last_tok, before, after))
    return out


_SEP_RE = re.compile(r"[\s\-\.\(\)/_:,+]+")


def value_key(label: str, value: str) -> str:
    """Default identity of a span value for placeholder numbering: case-folded, separators removed,
    spoken digits converted."""
    words = re.findall(r"[^\W_]+|[^\w\s]", unicodedata.normalize("NFC", value).casefold())
    parts = [DIGIT_WORDS.get(w, w) for w in words]
    return _SEP_RE.sub("", "".join(parts))
