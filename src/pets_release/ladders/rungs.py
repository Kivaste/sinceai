"""Rung registry: ladder order and the rung -> contract-form table.

Contract forms (consumed by ticket 10, validated by ticket 04's gate) are either an
anchored regex ``^...$`` or one of the validator IDs in ``VALIDATOR_FORMS``.
"""

from __future__ import annotations

WITHHELD = "withheld"

# Validator IDs the gate understands besides anchored regexes.
VALIDATOR_FORMS = frozenset({"hex64", "text", "integer", "decimal", "enum"})

# Ladders, finest first, `withheld` always last. Order follows the spec.
LADDERS: dict[str, tuple[str, ...]] = {
    # ts.hour_of_day (date-free HH:00) is coarser than ts.month on the privacy order (#89): for linkage it drops
    # all date meaning. It is in SACRIFICE_ONLY_RUNGS: never an ordinary coarsening step.
    "timestamp": ("ts.exact", "ts.hour", "ts.month_hour", "ts.day", "ts.week", "ts.month", "ts.hour_of_day", WITHHELD),
    "age": ("age.band5", "age.band10", WITHHELD),
    "geo": ("geo.full", "geo.topn", WITHHELD),
    "icd10": ("icd.full", "icd.3", "icd.chapter", WITHHELD),
    "numeric": ("num.exact", "num.round", "num.bin", WITHHELD),
    "identifier": ("id.pseudonym", WITHHELD),
    "text": ("text.redacted", WITHHELD),
    "categorical": ("keep", WITHHELD),
}

_NUM = r"-?\d+(?:\.\d+)?"

# rung -> contract form. ``withheld`` has no form (the column is absent).
CONTRACT_FORMS: dict[str, str] = {
    "ts.exact": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
    "ts.hour": r"^\d{4}-\d{2}-\d{2}T\d{2}:00$",
    "ts.month_hour": r"^\d{4}-\d{2}-01T\d{2}:00$",
    # Date-free `HH:00`: pets_eval.to_hour parses it to the right hour (verified); no sentinel date needed.
    "ts.hour_of_day": r"^\d{2}:00$",
    "ts.day": r"^\d{4}-\d{2}-\d{2}$",
    "ts.week": r"^\d{4}-W\d{2}$",
    "ts.month": r"^\d{4}-\d{2}$",
    "age.band5": r"^(?:\d{1,2}-\d{1,2}|90\+)$",
    "age.band10": r"^(?:\d{1,2}-\d{1,2}|90\+)$",
    "geo.full": "text",
    "geo.topn": "text",
    "icd.full": r"^[A-Z]\d{2}(?:\.[A-Z0-9]{1,4})?$",
    "icd.3": r"^[A-Z]\d{2}$",
    "icd.chapter": r"^[A-Z]$",
    "num.exact": rf"^[<>]?{_NUM}$",
    "num.round": "decimal",
    "num.bin": rf"^\[{_NUM},{_NUM}\)$",
    "id.pseudonym": "hex64",
    "text.redacted": "text",
    "keep": "text",
}

# Every rung emits an empty cell for a null or malformed source value, so every contract entry
# built from it must say `params.nullable: true` (ticket 04's gate accepts empty values then).
CONTRACT_PARAMS: dict[str, dict] = {r: {"nullable": True} for r in CONTRACT_FORMS}


def contract_entry(rung: str) -> dict:
    """``{form, params}`` for a contract column produced by ``rung``."""
    return {"form": contract_form(rung), "params": dict(CONTRACT_PARAMS[rung])}


# Rung -> ladder kind (inverse of LADDERS, without withheld).
RUNG_KIND: dict[str, str] = {r: k for k, ladder in LADDERS.items() for r in ladder if r != WITHHELD}

# Rungs that rank on a common ladder as `withheld` -> every ladder's last element.
KNOWN_RUNGS = frozenset(CONTRACT_FORMS) | {WITHHELD}


class LadderError(ValueError):
    """Plan or parameter problem. Messages carry schema names only, never values."""


def contract_form(rung: str) -> str:
    """Contract form (anchored regex or validator ID) for a released rung."""
    try:
        return CONTRACT_FORMS[rung]
    except KeyError:
        raise LadderError(f"no contract form for rung {rung!r}") from None


# Rungs a plan may hold only as a policy-enumerated rung sacrifice with measured scores (#89): no ordinary
# coarsening step, score-sacrifice walk or joint move ever lands on one.
SACRIFICE_ONLY_RUNGS = frozenset({"ts.hour_of_day"})


def coarseness(rung: str) -> tuple[str, int]:
    """(kind, position on its ladder) for a rung; `withheld` is kind '*'."""
    if rung == WITHHELD:
        return ("*", 10**6)
    kind = RUNG_KIND.get(rung)
    if kind is None:
        raise LadderError(f"unknown rung {rung!r}")
    return kind, LADDERS[kind].index(rung)


def at_least_as_coarse(rung: str, floor: str) -> bool:
    """True iff ``rung`` releases no more than ``floor`` (same ladder kind, ladder position). Fail closed: unknown
    rungs and rungs of different kinds are False; `withheld` is coarser than everything."""
    if rung not in KNOWN_RUNGS or floor not in KNOWN_RUNGS:
        return False
    if rung == WITHHELD:
        return True
    if floor == WITHHELD:
        return False
    if RUNG_KIND[rung] != RUNG_KIND[floor]:
        return False
    lad = LADDERS[RUNG_KIND[rung]]
    return lad.index(rung) >= lad.index(floor)
