"""Label-aware value normalisation applied before hashing.

Goal: surface variants of one value (case, separators, spoken digits,
fi/sv name inflections) get one pseudonym, while distinct values stay
distinct. Heuristic and conservative; misses only cost a link, they never
merge record keys.

Per label:
- RECORD_KEY, SECRET: surrounding whitespace stripped only (exact).
- NATIONAL_ID: spoken digits/dash (fi/sv/en) converted, whitespace and dots
  removed, upper-cased; the HETU century sign (-, +, letter) is kept.
- PHONE: spoken digits converted; digits and a leading + kept;
  00 -> +, +358 / +46 -> trunk 0.
- IBAN, PAYMENT_CARD, ACCOUNT_NUMBER, LICENSE_PLATE: spoken digits
  converted, upper-cased, non-alphanumerics removed.
- EMAIL, USERNAME, DEVICE_ID: case-folded, whitespace removed.
- PERSON: case-folded, one space between name words, each word stripped of a
  common fi/sv case ending (Annalle/Annan/Annas -> anna;
  Virtasen/Virtaselle/Virtanen -> one stem). Stems keep >= 3 letters.
- other span labels: NFKC, case-folded, whitespace collapsed.
"""

from __future__ import annotations

import re
import unicodedata

SPAN_LABELS = frozenset(
    {
        "PERSON",
        "NATIONAL_ID",
        "EMAIL",
        "PHONE",
        "ADDRESS",
        "LOCATION",
        "DATE",
        "AGE",
        "IBAN",
        "PAYMENT_CARD",
        "ACCOUNT_NUMBER",
        "IP_ADDRESS",
        "LICENSE_PLATE",
        "ORG",
        "URL",
        "USERNAME",
        "SECRET",
        "HEALTH",
        "DEVICE_ID",
        "PROPERTY_ID",
    }
)
RECORD_KEY = "RECORD_KEY"
LABELS = SPAN_LABELS | {RECORD_KEY}

_DIGIT_WORDS = {
    # fi
    "nolla": "0",
    "yksi": "1",
    "kaksi": "2",
    "kolme": "3",
    "neljä": "4",
    "viisi": "5",
    "kuusi": "6",
    "seitsemän": "7",
    "kahdeksan": "8",
    "yhdeksän": "9",
    # sv
    "noll": "0",
    "ett": "1",
    "en": "1",
    "två": "2",
    "tre": "3",
    "fyra": "4",
    "fem": "5",
    "sex": "6",
    "sju": "7",
    "åtta": "8",
    "nio": "9",
    # en
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    # spoken separators
    "viiva": "-",
    "väliviiva": "-",
    "streck": "-",
    "bindestreck": "-",
    "dash": "-",
    "hyphen": "-",
    "minus": "-",
    "plus": "+",
}

_SPOKEN_LABELS = frozenset(
    {"NATIONAL_ID", "PHONE", "IBAN", "PAYMENT_CARD", "ACCOUNT_NUMBER", "LICENSE_PLATE"}
)
_ALNUM_LABELS = frozenset({"IBAN", "PAYMENT_CARD", "ACCOUNT_NUMBER", "LICENSE_PLATE"})
_NOSPACE_FOLD_LABELS = frozenset({"EMAIL", "USERNAME", "DEVICE_ID"})

_MIN_STEM = 3
# ordered: first match wins; (pattern, replacement)
_NAME_RULES = (
    (re.compile(r"nen$"), "s"),  # Virtanen -> virtas
    (
        re.compile(r"se(n|lle|lla|llä|lta|ltä|ssa|ssä|sta|stä|ksi|na|nä)$"),
        "s",
    ),  # Virtasen -> virtas
    (
        re.compile(r"(lle|lla|llä|lta|ltä|ssa|ssä|sta|stä|ksi|n)$"),
        "",
    ),  # Annalle -> anna
    (re.compile(r"s$"), ""),  # sv genitive: Annas -> anna
)
_NAME_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


def _spoken(text: str) -> str:
    words = re.split(r"\s+", text.casefold().strip())
    return " ".join(_DIGIT_WORDS.get(w, w) for w in words)


def _stem(word: str) -> str:
    for pattern, repl in _NAME_RULES:
        m = pattern.search(word)
        if m:
            stem = word[: m.start()] + repl
            return stem if len(stem) >= _MIN_STEM else word
    return word


def _phone(text: str) -> str:
    s = re.sub(r"[^0-9+]", "", text)
    plus = s.startswith("+")
    s = s.replace("+", "")
    if plus:
        s = "+" + s
    elif s.startswith("00"):
        s = "+" + s[2:]
    for cc in ("+358", "+46"):
        if s.startswith(cc):
            return "0" + s[len(cc) :]
    return s


def normalise(value: str, label: str) -> str:
    if label not in LABELS:
        raise ValueError("unknown pseudonym label")
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    if label in (RECORD_KEY, "SECRET"):
        return value.strip()
    text = unicodedata.normalize("NFKC", value)
    if label in _SPOKEN_LABELS:
        text = _spoken(text)
    if label == "NATIONAL_ID":
        return re.sub(r"[\s._]", "", text).upper()
    if label == "PHONE":
        return _phone(text)
    if label in _ALNUM_LABELS:
        return re.sub(r"[^0-9A-Z]", "", text.upper())
    if label in _NOSPACE_FOLD_LABELS:
        return re.sub(r"\s", "", text.casefold())
    if label == "PERSON":
        return " ".join(_stem(w) for w in _NAME_WORD.findall(text.casefold()))
    return " ".join(text.casefold().split())
