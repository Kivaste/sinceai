"""Small table-driven builders shared by the two scenario modules."""
from __future__ import annotations

from .model import FieldFloor, make_entry

# row = (table, column, family, floor_rung, direct, floor_reason, hand_rung, hand_params, hand_reason)


def build(rows: list[tuple]) -> tuple[dict, tuple, list]:
    floors: dict = {}
    direct: list = []
    plan: list = []
    for table, col, family, floor, is_direct, freason, hrung, hparams, hreason in sorted(rows, key=lambda r: (r[0], r[1])):
        floors[(table, col)] = FieldFloor(family, floor, freason)
        if is_direct:
            direct.append((table, col))
        plan.append(make_entry(table, col, hrung, floor, hreason, hparams))
    return floors, tuple(direct), plan


def withheld_table(table: str, cols: list[tuple[str, str]], reason: str) -> list[tuple]:
    """cols: (column, family). Every column floor + hand rung = withheld."""
    return [(table, c, fam, "withheld", False, reason, "withheld", {}, reason) for c, fam in cols]
