"""Shared cue vocabulary for the cell and text secret/username rescans (follow-up #53).

The gate is an independent implementation, so it imports nothing from the redactor; the
placeholder label list is a copy of the redactor's span labels, and a test pins the two equal.
Only an *exact* redactor placeholder (``[<LABEL>_<n>]``, n >= 1, or the bare ``[<LABEL>]``) is
treated as an already-redacted value; any other bracketed token is an ordinary value.
"""
from __future__ import annotations

import re

PLACEHOLDER_LABELS: tuple[str, ...] = (
    "PERSON", "NATIONAL_ID", "EMAIL", "PHONE", "ADDRESS", "LOCATION", "DATE", "AGE", "IBAN",
    "PAYMENT_CARD", "ACCOUNT_NUMBER", "IP_ADDRESS", "LICENSE_PLATE", "ORG", "URL", "USERNAME",
    "SECRET", "HEALTH", "DEVICE_ID", "PROPERTY_ID",
)
# longest first so "[IP_ADDRESS_1]" never stops at a shorter label
PLACEHOLDER_SRC = (r"\[(?:" + "|".join(sorted(PLACEHOLDER_LABELS, key=lambda s: (-len(s), s)))
                   + r")(?:_[1-9][0-9]*)?\]")
PLACEHOLDER_RE = re.compile(PLACEHOLDER_SRC)


def is_placeholder(tok: str) -> bool:
    return PLACEHOLDER_RE.fullmatch(tok) is not None


# Words skipped between a cue and its value ("password is *the* Talvi2031", "pin is *not* 4821",
# "salasana on *edelleen* X"); see HEDGES for which of them keep a plain word a value.
FUNCTION_WORDS = frozenset("""
the a an my your his her its our their this that these those for of to at in with from
not never no still also just now really probably maybe perhaps already again
my mine minun sinun meidän teidän hänen sen ei eikä vielä edelleen nyt kai varmaan luultavasti ehkä jo myös
min mitt mina din ditt er vår inte icke ej nog kanske typ fortfarande nu redan också för till av på
""".split())
# The only function words after which a plain word still counts as the copula's value ("password is
# probably hunterxyz"). After any other ("is *a* pain", "is *really* annoying", "is *not* working") only
# a credential-shaped token counts.
HEDGES = frozenset("""
probably maybe perhaps still now varmaan kai luultavasti ehkä edelleen nyt nog kanske typ fortfarande nu
""".split())
COPULAS = frozenset({"is", "was", "on", "oli", "är", "var", "it's", "its", "=", ":"})
# Everyday words: never a value; they may sit between a cue and its value.
PROSE_WORDS = FUNCTION_WORDS | frozenset("""
and or but because while until once only even such some any all each every both other another
more most much many few less least own than then there here yes ok okay sure please thanks thank
wrong incorrect invalid expired changed correct right fine working broken locked blocked lost
forgotten unknown new old same different one too very should would could will can cannot must may
might were been being are has have had does did doesn didn isn aren wasn reset link page screen
details info information problem issue account service router modem network login logout user
name username code number what which when where why how who into onto over under about after before
oikea väärä vanha uusi sama eri liian tosi vain hukassa lukossa voimassa vanhentunut vaihdettu
unohtunut kadonnut estetty jotain mikä mitä tämä tuo hyvä huono ja tai mutta koska kun jos kaikille
kaikki kaikissa kaikkiin palveluille palveluun tunnus tunnukset lukittu lukittuna toimi toimii sivu
sivulla ongelma fel rätt gammal gamla ny nya samma annan fär mycket bara glömt ändrat borta läst
spärrat något vad detta det bra dålig och eller men
down up off offline online slow fast available unavailable required needed missing ready same
hidas nopea rikki poikki pois päällä katki tarvitaan puuttuu valmis nere uppe av långsam saknas klar
""".split())
# Tokens scanned after a cue, up to the sentence end. Generous on purpose (the redactor scans 6):
# skipped words and separator runs must not push a value out of reach.
WINDOW = 12
# A date or time: counts as a value only right after a copula ("password is 12/03/2021").
DATE_OR_TIME = re.compile(r"\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?|\d{1,2}:\d{2}")


def is_punct(word: str) -> bool:
    """A separator/punctuation run ("-", "--", "/", "#", "\u00b7"): skipped between a cue and its value."""
    return not any(c.isalnum() for c in word)
