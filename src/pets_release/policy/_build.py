"""Small table-driven builders shared by the two scenario modules."""
from __future__ import annotations

from .model import FieldFloor, make_entry

# Authoring shorthand -> ticket 07's canonical rung IDs (pets_release.ladders.LADDERS), per family.
_SHORT = {
    "timestamp": {"exact": "ts.exact", "hour": "ts.hour", "month_hour": "ts.month_hour", "hour_of_day": "ts.hour_of_day"},
    "age": {"age_band_5": "age.band5", "age_band_10": "age.band10"},
    "geo": {"exact": "geo.full", "top_n": "geo.topn"},
    "icd10": {"exact": "icd.full", "chars3": "icd.3", "chapter": "icd.chapter"},
    "numeric": {"exact": "num.exact", "rounded": "num.round", "binned": "num.bin"},
    "identifier": {"pseudonym": "id.pseudonym"},
    "text": {"redacted": "text.redacted"},
    "categorical": {"exact": "keep"},
    "lab_test": {"exact": "lab.full", "crp_other": "lab.crp_other"},
}


def _id(family: str, rung: str) -> str:
    return _SHORT.get(family, {}).get(rung, rung)

# row = (table, column, family, floor_rung, direct, floor_reason, hand_rung, hand_params, hand_reason)


def build(rows: list[tuple]) -> tuple[dict, tuple, list]:
    floors: dict = {}
    direct: list = []
    plan: list = []
    for table, col, family, floor, is_direct, freason, hrung, hparams, hreason in sorted(rows, key=lambda r: (r[0], r[1])):
        floor, hrung = _id(family, floor), _id(family, hrung)
        floors[(table, col)] = FieldFloor(family, floor, freason)
        if is_direct:
            direct.append((table, col))
        plan.append(make_entry(table, col, hrung, floor, hreason, hparams))
    return floors, tuple(direct), plan


def withheld_table(table: str, cols: list[tuple[str, str]], reason: str) -> list[tuple]:
    """cols: (column, family). Every column floor + hand rung = withheld."""
    return [(table, c, fam, "withheld", False, reason, "withheld", {}, reason) for c, fam in cols]
