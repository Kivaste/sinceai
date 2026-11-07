"""Rung → form table.

Ticket 07 owns the real table (``pets_release.ladders.RUNG_FORMS``). Until that
module is importable, ``load_forms`` returns the spec-derived fallback below.
A present sibling table replaces the fallback entirely; the two are not merged.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping

# Spec: month+hour example ``2025-03-01T14:00``, form pinned in the spec text.
MONTH_HOUR_FORM = r"^\d{4}-\d{2}-01T\d{2}:00$"
# Spec and ticket 02 fixture: keyed pseudonym is 64 lowercase hex.
TOKEN_FORM = r"^[0-9a-f]{64}$"

# Assumption until ticket 07 lands: dotted rung ids, one form per rung.
# Category vocabularies below are data-dictionary closed sets, not row values.
FALLBACK_FORMS: dict[str, str] = {
    "identifier.pseudonym": TOKEN_FORM,
    "timestamp.exact": r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?$",
    "timestamp.hour": r"^\d{4}-\d{2}-\d{2}T\d{2}:00$",
    "timestamp.month_hour": MONTH_HOUR_FORM,
    "timestamp.day": r"^\d{4}-\d{2}-\d{2}$",
    "timestamp.week": r"^\d{4}-W\d{2}$",
    "timestamp.month": r"^\d{4}-\d{2}$",
    "age.band5": (
        r"^(?:0-4|5-9|10-14|15-19|20-24|25-29|30-34|35-39|40-44|45-49|"
        r"50-54|55-59|60-64|65-69|70-74|75-79|80-84|85-89|90\+)$"
    ),
    "age.band10": r"^(?:0-9|10-19|20-29|30-39|40-49|50-59|60-69|70-79|80-89|90\+)$",
    "geo.full": r"^[^\r\n]+$",
    "geo.topn": r"^(?:other|[^\r\n]+)$",
    "icd10.full": r"^(?:[A-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?(?:\|[A-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?)?)?$",
    "icd10.3char": r"^(?:[A-Z][0-9]{2}(?:\|[A-Z][0-9]{2})?)?$",
    "icd10.chapter": r"^(?:[A-Z](?:\|[A-Z])?)?$",
    "numeric.exact": r"^(?:-?\d+(?:[.,]\d+)?|<\d+(?:[.,]\d+)?|POS|NEG)?$",
    "numeric.rounded": r"^(?:-?\d+(?:[.,]\d+)?)?$",
    "numeric.binned": r"^(?:\d+(?:[.,]\d+)?-\d+(?:[.,]\d+)?|\d+\+)?$",
    "numeric.csat": r"^(?:[1-5])?$",
    "category.exact": r"^(?:[^\r\n]+)?$",
    "category.sex": r"^[MF]$",
    "category.triage": r"^[ABCDE]$",
    "category.arrival_mode": r"^(?:walk-in|ambulance|helicopter|police)$",
    "category.disposition": (
        r"^(?:home|admitted_ward|icu|transfer|died|left_without_being_seen|cancelled_duplicate)$"
    ),
    "category.channel": r"^(?:chat|phone|email)$",
    "category.language": r"^(?:fi|sv|en)$",
    "category.speaker": r"^(?:customer|agent|bot)$",
    "category.split": r"^(?:train|eval)$",
    "category.abnormal": r"^(?:H|L|A)?$",
    "flag.exact": r"^(?:[01])?$",
    "text.redacted": r"(?s)^.*$",
    "as_is": r"^[^\r\n]+$",
}

_SIBLING_MODULES = (
    "pets_release.ladders",
    "pets_release.ladders.forms",
)


def load_forms() -> dict[str, str]:
    """Rung id → form regex. Sibling table wins wholesale when it is a mapping."""
    for mod_name in _SIBLING_MODULES:
        try:
            module = importlib.import_module(mod_name)
        except ImportError:
            continue
        table = getattr(module, "RUNG_FORMS", None)
        if isinstance(table, Mapping):
            return {str(key): value for key, value in table.items()}
    return dict(FALLBACK_FORMS)
