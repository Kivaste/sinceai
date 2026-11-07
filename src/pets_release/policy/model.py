"""Policy record, ladder vocabulary and Plan validation. Schema names only; no row values.

Rung IDs are ticket 07's (pets_release.ladders.LADDERS); this module defines none of its own.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from pets_release.ladders import (  # single source of rung IDs (ticket 07)
    CONTRACT_FORMS,
    LADDERS,
    SACRIFICE_ONLY_RUNGS,
    WITHHELD,
    at_least_as_coarse,
)

PLAN_KEYS = frozenset({"table", "column", "rung", "params", "floor", "reason", "source"})


class PlanError(ValueError):
    pass


class PolicyError(ValueError):
    """A policy record is malformed (closed sub-records: exact keys)."""


_TARGETS = {
    "k_anonymity": {"id", "kind", "k", "unit", "over"},
    "text_recall": {"id", "kind", "min", "labels"},
    "health_in_text": {"id", "kind", "max_hits"},
    "timestamp_floor": {"id", "kind", "rung"},
}
_QI_REQ = {"table", "column", "derived"}
_QI_OPT = {"note", "join_via"}
_SACRIFICE = {"check", "floor_score", "reason", "via"}
_RUNG_SACRIFICE = {"check", "table", "column", "from", "to", "reason"}
_MOVE = {"table", "column", "rung"}
_SUPPRESSION = {"method", "unit", "k", "max_share", "order", "then"}
_NOTE = {"id", "status", "note"}
_NOTE_STATUS = {"not_applicable", "open"}


def _exact(rec, keys, what, optional=frozenset()):
    if not isinstance(rec, dict):
        raise PolicyError(f"{what} must be an object")
    ks = set(rec)
    if not keys <= ks or not ks <= (keys | optional):
        raise PolicyError(f"{what} keys must be {sorted(keys)} (+optional {sorted(optional)}), got {sorted(ks)}")


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
    alt_floors: dict = field(default_factory=dict)  # (table, column) -> alternative floor rung (conditional release)
    # (table, column) -> {check, outcome}: the alt floor applies only when `check` fails with the column
    # withheld (machine-readable predicate; a search/run step evaluates it, prose is not enough)
    alt_floor_conditions: dict = field(default_factory=dict)
    residual_notes: tuple[dict, ...] = ()  # {id, status, note}: e.g. a target that is not applicable
    suppression: dict | None = None  # last-step local suppression of below-k persons (applied by ticket 21)
    # {check, table, column, from, to, reason} (#89): the only way a plan holds a sacrifice-only rung `to`.
    # Adopted only when k measured at `from` needs more suppression than the budget and `check` still passes
    # strictly at `to`; the release records the measured scores under the check's sacrifice entry.
    rung_sacrifices: tuple[dict, ...] = ()

    def __post_init__(self):
        cols = set(self.floors)
        for key, fl in self.floors.items():
            if fl.family not in LADDERS or fl.rung not in LADDERS[fl.family]:
                raise PolicyError(f"floor for {key} is not on its ladder")
        for t in self.privacy_targets:
            if not isinstance(t, dict) or t.get("kind") not in _TARGETS:
                raise PolicyError("unknown privacy target kind")
            _exact(t, _TARGETS[t["kind"]], "privacy target")
            if t["kind"] == "timestamp_floor" and t["rung"] not in LADDERS["timestamp"]:
                raise PolicyError("timestamp_floor rung must be a canonical timestamp rung ID")
        for q in self.qi:
            _exact(q, _QI_REQ, "qi row", _QI_OPT)
            if (q["table"], q["column"]) not in cols:
                raise PolicyError("qi row names an unknown column")
            jv = q.get("join_via")
            if jv is not None and (not isinstance(jv, list) or len(jv) != 2 or tuple(jv) not in cols):
                raise PolicyError("join_via must be [table, column] of a policy column")
        for sc in self.sacrifices:
            _exact(sc, _SACRIFICE, "sacrifice")
            if sc["check"] not in self.purpose_checks:
                raise PolicyError("sacrifice names a check outside the purpose checks")
            if not (isinstance(sc["floor_score"], (int, float)) and 0 <= sc["floor_score"] < 0.9):
                raise PolicyError("sacrifice floor_score must be in [0, 0.9)")
            if not isinstance(sc["via"], list) or not sc["via"]:
                raise PolicyError("sacrifice needs plan columns in via")
            for v in sc["via"]:
                _exact(v, {"table", "column"}, "sacrifice via")
                if (v["table"], v["column"]) not in cols:
                    raise PolicyError("sacrifice via names an unknown column")
        score_sacrifices = {s["check"] for s in self.sacrifices}
        seen_rs = set()
        for rs in self.rung_sacrifices:
            _exact(rs, _RUNG_SACRIFICE, "rung sacrifice")
            key = (rs["table"], rs["column"])
            if key not in cols or key in seen_rs:
                raise PolicyError("rung sacrifice names an unknown or repeated column")
            seen_rs.add(key)
            if rs["check"] not in score_sacrifices:
                raise PolicyError("rung sacrifice check needs an enumerated sacrifice entry")
            fl = self.floors[key]
            lad = LADDERS[fl.family]
            if rs["to"] not in SACRIFICE_ONLY_RUNGS or rs["to"] not in lad or rs["from"] not in lad:
                raise PolicyError("rung sacrifice must move to a sacrifice-only rung on the column's ladder")
            if rs["from"] in SACRIFICE_ONLY_RUNGS or not at_least_as_coarse(rs["from"], fl.rung) or \
                    not at_least_as_coarse(rs["to"], rs["from"]) or rs["from"] == rs["to"]:
                raise PolicyError("rung sacrifice must go from an ordinary rung at or above the floor to a coarser one")
        for mv in self.joint_qi_moves:
            for m in mv:
                _exact(m, _MOVE, "joint QI move")
                if (m["table"], m["column"]) not in cols:
                    raise PolicyError("joint QI move names an unknown column")
                if m["rung"] not in CONTRACT_FORMS and m["rung"] != WITHHELD:
                    raise PolicyError("joint QI move names an unknown rung")
            seen_cols = [(m["table"], m["column"]) for m in mv]
            if len(set(seen_cols)) != len(seen_cols):
                raise PolicyError("joint QI move names a column twice")
            qi_cols = {(q["table"], q["column"]) for q in self.qi}
            for m in mv:
                key = (m["table"], m["column"])
                fl = self.floors[key]
                ladder = LADDERS[fl.family]
                if key not in qi_cols:
                    raise PolicyError("joint QI move column is not a QI")
                if m["rung"] not in ladder:
                    raise PolicyError("joint QI move rung is not on the column's ladder")
                if not at_least_as_coarse(m["rung"], fl.rung):
                    raise PolicyError("joint QI move rung is finer than the column's floor")
        for key, rung in (self.alt_floors or {}).items():
            if key not in cols or (rung not in CONTRACT_FORMS and rung != WITHHELD):
                raise PolicyError("alt_floors entry is invalid")
        for key, cond in (self.alt_floor_conditions or {}).items():
            if key not in (self.alt_floors or {}):
                raise PolicyError("alt_floor_conditions entry has no alt floor")
            _exact(cond, {"check", "outcome"}, "alt floor condition")
            if cond["check"] not in self.purpose_checks or cond["outcome"] != "fail_without":
                raise PolicyError("alt floor condition must name a purpose check and outcome fail_without")
        for n in self.residual_notes:
            _exact(n, _NOTE, "residual note")
            if n["status"] not in _NOTE_STATUS:
                raise PolicyError("residual note status invalid")
        if self.suppression is not None:
            _exact(self.suppression, _SUPPRESSION, "suppression")
            if not 0 < self.suppression["max_share"] <= 1:
                raise PolicyError("suppression max_share must be in (0, 1]")

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
            "rungSacrifices": [dict(s) for s in self.rung_sacrifices],
            "jointQiMoves": [[dict(m) for m in mv] for mv in self.joint_qi_moves],
            "altFloors": [
                {"table": t, "column": c, "floor": r} for (t, c), r in sorted((self.alt_floors or {}).items())
            ],
            "altFloorConditions": [
                {"table": t, "column": c, **v} for (t, c), v in sorted((self.alt_floor_conditions or {}).items())
            ],
            "residualNotes": [dict(n) for n in self.residual_notes],
            "suppression": dict(self.suppression) if self.suppression else None,
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
            json.dumps(e["params"], sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            raise PlanError(f"params not JSON-serialisable for {key}") from None
        fl = policy.floors[key]
        alt = (policy.alt_floors or {}).get(key)
        if e["floor"] == fl.rung:
            ladder = LADDERS[fl.family]
            if e["rung"] not in ladder:
                raise PlanError(f"rung {e['rung']!r} not on the {fl.family} ladder for {key}")
            if not at_least_as_coarse(e["rung"], fl.rung):
                raise PlanError(f"rung for {key} is finer than its floor")
            if e["rung"] in SACRIFICE_ONLY_RUNGS and e["rung"] != fl.rung and not any(
                    (rs["table"], rs["column"], rs["to"]) == (*key, e["rung"]) for rs in policy.rung_sacrifices):
                raise PlanError(f"rung for {key} is sacrifice-only and not an enumerated rung sacrifice")
        elif alt and e["floor"] == alt:  # conditional-keep fallback: only the alt rung or withheld
            if e["rung"] not in (alt, WITHHELD):
                raise PlanError(f"rung for {key} is finer than its alternative floor")
        else:
            raise PlanError(f"floor field for {key} does not match the policy floor")
        if e["rung"] == "id.pseudonym" and not isinstance(e["params"].get("label", "RECORD_KEY"), str):
            raise PlanError(f"pseudonym label must be a string for {key}")
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
