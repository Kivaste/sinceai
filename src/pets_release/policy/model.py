"""Policy record, ladder vocabulary and Plan validation. Schema names only; no row values.

Rung IDs are the policy's pinned vocabulary. Ticket 07 (ladders) implements the same IDs; if it
renames one, change LADDERS here and nothing else.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# family -> rungs ordered finest -> coarsest (last is always "withheld")
LADDERS: dict[str, tuple[str, ...]] = {
    "timestamp": ("exact", "hour", "month_hour", "day", "week", "month", "withheld"),
    "age": ("age_band_5", "age_band_10", "withheld"),  # params: top_code
    "geo": ("exact", "top_n", "withheld"),  # municipality/postcode; top_n params: n (rest "other")
    "icd10": ("exact", "chars3", "chapter", "withheld"),
    "numeric": ("exact", "rounded", "binned", "withheld"),
    "categorical": ("exact", "withheld"),
    "identifier": ("pseudonym", "withheld"),  # keyed 64-hex; never raw
    "key": ("exact", "pseudonym", "withheld"),  # synthetic record key, conditionally kept as-is
    "text": ("redacted", "withheld"),
}
PSEUDONYM_SCOPES = ("conversation", "release", "recipient")
PLAN_KEYS = frozenset({"table", "column", "rung", "params", "floor", "reason", "source"})


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class FieldFloor:
    family: str
    rung: str  # most detailed rung the scenario allows; the search may only go coarser
    reason: str


@dataclass(frozen=True)
class ScenarioPolicy:
    scenario: str
    dataset: str
    purpose_checks: tuple[str, ...]
    privacy_targets: tuple[dict, ...]
    floors: dict  # (table, column) -> FieldFloor, in fixed (table, column) order
    direct_identifiers: tuple[tuple[str, str], ...]
    qi: tuple[dict, ...]
    risk_vector: tuple[str, ...]
    sacrifices: tuple[dict, ...]  # {check, floor_score, reason}
    joint_qi_moves: tuple[tuple[dict, ...], ...]  # each move = tuple of {table, column, rung[, params]}
    linked: tuple[tuple[tuple[str, str], ...], ...]  # column groups that must share rung + params
    param_minimums: dict  # (table, column) -> {"rung": r, "param": p, "min": n}

    def to_json(self) -> dict:
        return {
            "scenario": self.scenario,
            "dataset": self.dataset,
            "purposeChecks": list(self.purpose_checks),
            "privacyTargets": [dict(t) for t in self.privacy_targets],
            "floors": [
                {"table": t, "column": c, "family": f.family, "floor": f.rung, "reason": f.reason}
                for (t, c), f in sorted(self.floors.items())
            ],
            "directIdentifiers": [{"table": t, "column": c} for t, c in self.direct_identifiers],
            "qi": [dict(q) for q in self.qi],
            "riskVector": list(self.risk_vector),
            "sacrifices": [dict(s) for s in self.sacrifices],
            "jointQiMoves": [[dict(m) for m in mv] for mv in self.joint_qi_moves],
            "linked": [[{"table": t, "column": c} for t, c in g] for g in self.linked],
            "paramMinimums": [
                {"table": t, "column": c, **v} for (t, c), v in sorted(self.param_minimums.items())
            ],
        }


def make_entry(table: str, column: str, rung: str, floor: str, reason: str, params: dict | None = None) -> dict:
    return {
        "table": table,
        "column": column,
        "rung": rung,
        "params": dict(params or {}),
        "floor": floor,
        "reason": reason,
        "source": "hand",
    }


def validate_plan(plan: list, policy: ScenarioPolicy) -> None:
    """Fail closed: raises PlanError on any deviation from the pinned Plan shape or the policy."""
    seen: dict[tuple[str, str], dict] = {}
    for e in plan:
        if not isinstance(e, dict) or set(e) != PLAN_KEYS:
            raise PlanError(f"entry keys must be exactly {sorted(PLAN_KEYS)}")
        key = (e["table"], e["column"])
        if key in seen:
            raise PlanError(f"duplicate entry {key}")
        if key not in policy.floors:
            raise PlanError(f"unknown column {key}")
        if e["source"] not in ("hand", "search"):
            raise PlanError(f"bad source for {key}")
        if not isinstance(e["reason"], str) or not e["reason"].strip():
            raise PlanError(f"empty reason for {key}")
        if not isinstance(e["params"], dict):
            raise PlanError(f"params must be an object for {key}")
        try:
            json.dumps(e["params"], sort_keys=True)
        except (TypeError, ValueError):
            raise PlanError(f"params not JSON-serialisable for {key}") from None
        fl = policy.floors[key]
        ladder = LADDERS[fl.family]
        if e["floor"] != fl.rung:
            raise PlanError(f"floor field for {key} does not match the policy floor")
        if e["rung"] not in ladder:
            raise PlanError(f"rung {e['rung']!r} not on the {fl.family} ladder for {key}")
        if ladder.index(e["rung"]) < ladder.index(fl.rung):
            raise PlanError(f"rung for {key} is finer than its floor")
        if e["rung"] == "pseudonym" and e["params"].get("scope") not in PSEUDONYM_SCOPES:
            raise PlanError(f"pseudonym scope missing or invalid for {key}")
        seen[key] = e
    missing = set(policy.floors) - set(seen)
    if missing:
        raise PlanError(f"missing columns: {sorted(missing)}")
    for key, spec in policy.param_minimums.items():
        e = seen[key]
        if e["rung"] == spec["rung"]:
            v = e["params"].get(spec["param"])
            if not isinstance(v, int) or isinstance(v, bool) or v < spec["min"]:
                raise PlanError(f"{spec['rung']} {spec['param']} for {key} below policy minimum {spec['min']}")
    for group in policy.linked:
        first = seen[group[0]]
        for k in group[1:]:
            if seen[k]["rung"] != first["rung"] or seen[k]["params"] != first["params"]:
                raise PlanError(f"linked columns {group} must share rung and pseudonym scope/params")
