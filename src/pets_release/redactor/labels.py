"""The placeholder<->label table: one placeholder type per span label, fixed.

Submission spans carry ``label``; redacted text carries ``[<TYPE>_<n>]``. Both are
derived from this one table so they cannot drift.
"""

from __future__ import annotations

import re

# The 20 span labels of the kit's PII span guidelines, in a fixed order.
LABELS: tuple[str, ...] = (
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
)

# Labels whose detection is owned by the redactor core (ticket 12).
STRUCTURED_LABELS: frozenset[str] = frozenset(
    {
        "NATIONAL_ID",
        "IBAN",
        "PAYMENT_CARD",
        "ACCOUNT_NUMBER",
        "PHONE",
        "EMAIL",
        "IP_ADDRESS",
        "DEVICE_ID",
        "LICENSE_PLATE",
        "PROPERTY_ID",
        "URL",
        "SECRET",
        "USERNAME",
    }
)

# Labels left to lexicon passes (ticket 13, ``redactor/lexicon/``).
LEXICON_LABELS: frozenset[str] = frozenset(LABELS) - STRUCTURED_LABELS

# label -> placeholder type. Bijective; the type is the label name itself.
PLACEHOLDER_TYPE: dict[str, str] = {label: label for label in LABELS}
LABEL_OF_TYPE: dict[str, str] = {t: label for label, t in PLACEHOLDER_TYPE.items()}

_PLACEHOLDER_RE = re.compile(r"\[([A-Z_]+?)_([1-9][0-9]*)\]")


def placeholder(label: str, number: int) -> str:
    """Return the placeholder text for ``label`` and its per-conversation number."""
    if label not in PLACEHOLDER_TYPE:
        raise ValueError(f"unknown span label: {label!r}")
    if number < 1:
        raise ValueError("placeholder numbers start at 1")
    return f"[{PLACEHOLDER_TYPE[label]}_{number}]"


def parse_placeholder(text: str) -> tuple[str, int] | None:
    """Return (label, number) if ``text`` is exactly one placeholder, else None."""
    m = _PLACEHOLDER_RE.fullmatch(text)
    if not m or m.group(1) not in LABEL_OF_TYPE:
        return None
    return LABEL_OF_TYPE[m.group(1)], int(m.group(2))
