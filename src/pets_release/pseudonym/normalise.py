"""Label-aware value normalisation applied before hashing.

Goal: surface variants of one value (case, separators, spoken digits,
fi/sv name inflections) get one pseudonym, while distinct values stay
distinct. Conservative: a miss only costs a link; distinct people and
distinct record keys must never merge.

Callers pass the raw value to ``Pseudonymiser.token``, which normalises it.
Do not pre-normalise: ``normalise`` is not guaranteed idempotent, and in
conversation scope the Pseudonymiser adds context-based name linking on top.

Per label:
- RECORD_KEY, SECRET: surrounding whitespace stripped only (exact).
- NATIONAL_ID: spoken digits/dash (fi/sv/en) converted, whitespace and dots
  removed, upper-cased; the HETU century sign (-, +, letter) is kept.
- PHONE: spoken digits converted; digits and a leading + kept;
  00 -> +, +358 / +46 -> trunk 0 (a written trunk "(0)" or "0" is kept once).
- IBAN, PAYMENT_CARD, ACCOUNT_NUMBER, LICENSE_PLATE: spoken digits
  converted, upper-cased, non-alphanumerics removed.
- EMAIL, USERNAME, DEVICE_ID: case-folded, whitespace removed.
- PERSON: case-folded, one space between name words. Statelessly, only
  inflected Finnish -nen surnames return to the nominative
  (Virtasen/Virtaselle -> virtanen; stem >= 4 letters, so Hansen stays).
  Other case endings (Annalle, Annalta) are NOT stripped here: blanket
  stripping merges distinct names (Anna/Annan, Isabella/Isabelle). The
  Pseudonymiser links the multi-letter fi endings in CASE_ENDINGS only in
  conversation scope, to a name already seen in that conversation (see
  ``core``). Genitives (Annan, Eriks) and -ssa/-sta forms are never linked.
  Not covered: name order ("Surname, First"), consonant gradation
  (Matti -> Matille), titles.
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

# Stateless: inflected Finnish -nen surnames back to the nominative
# (Virtasen/Virtaselle -> virtanen). The stem before "se" must keep >= 4
# letters, so Hansen/Jensen/Larsen stay themselves.
_NEN_INFLECTED = re.compile(r"se(?:n|lle|lla|llä|lta|ltä|ssa|ssä|sta|stä|ksi|na|nä)$")
_NEN_MIN_STEM = 4

# Context-only (used by the Pseudonymiser in conversation scope): a word equal
# to a name already seen in the same conversation plus one of these endings.
# Deliberately absent: the one-letter genitives (fi -n, sv -s: Anna/Annan,
# Hans/Hansen, Erik/Eriks) and -ssa/-ssä/-sta/-stä (Lari/Larissa,
# Vane/Vanessa, Augu/Augusta): those name pairs can be different people even
# in one conversation. Known residual literal ambiguity: -lle names whose base
# is itself a name (Jane/Janelle, Noe/Noelle) link if both occur in one
# conversation with the shorter one first.
CASE_ENDINGS = ("lle", "lla", "llä", "lta", "ltä", "ksi")
MIN_BASE_NAME = 3
_RSQUO = chr(0x2019)  # typographic apostrophe, as in O'Neil
_NAME_WORD = re.compile(r"[^\W\d_]+(?:['" + _RSQUO + r"-][^\W\d_]+)*")


def _spoken(text: str) -> str:
    words = re.split(r"\s+", text.casefold().strip())
    return " ".join(_DIGIT_WORDS.get(w, w) for w in words)


def _name_word(word: str) -> str:
    m = _NEN_INFLECTED.search(word)
    if m and m.start() >= _NEN_MIN_STEM:
        return word[: m.start()] + "nen"
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
            rest = s[len(cc) :]
            # "+358 (0)40 ..." / "+358 040 ...": one trunk 0 only
            return rest if rest.startswith("0") else "0" + rest
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
        return " ".join(_name_word(w) for w in _NAME_WORD.findall(text.casefold()))
    return " ".join(text.casefold().split())
