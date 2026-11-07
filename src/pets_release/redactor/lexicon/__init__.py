"""Lexicon passes (ticket 13): PERSON, ADDRESS, LOCATION, ORG, DATE, AGE, HEALTH.

The pipeline calls ``passes()`` when building its default pass list. ``passes(gazetteer)`` adds the
controller gazetteer (built at runtime from the source tables, never written to disk). Lexicons and
boundary rules are the CSVs in ``data/`` (columns ``term,lang,label,match,boundary,notes``).
"""

from __future__ import annotations

from pathlib import Path

from ..passes import Pass
from . import loader
from .address import AddressPass
from .dates import AgePass, DatePass
from .gazetteer import Gazetteer
from .health import HealthPass
from .person import PersonPass
from .places import LocationPass, OrgPass

__all__ = ["Gazetteer", "loader", "passes"]


def passes(gazetteer: Gazetteer | None = None, data_dir: Path | str | None = None) -> list[Pass]:
    entries = loader.load(data_dir)
    rules = loader.load_rules(data_dir)
    location = LocationPass(entries, rules, gazetteer)
    return [
        PersonPass(entries, rules, gazetteer),
        AddressPass(entries, rules, gazetteer, location.is_known),
        location,
        OrgPass(entries, rules, gazetteer),
        DatePass(entries, rules),
        AgePass(entries, rules),
        HealthPass(entries, rules),
    ]
