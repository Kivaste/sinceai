"""Local suppression of below-k persons (policy field ``suppression``; applied as the last step).

Rule (HEALTH-S1 policy): unit persons, k from the policy, records visited in record-key ascending order, iterated to
a fixpoint, then refused if the suppressed share of persons exceeds ``max_share``. A unit is below k when ticket 11's
own per-person k (``person_k_values``, the production rule the gate re-runs) says so, or when it is an unidentified
unit (no person ID in source; those can never reach k). Every round drops every below-k unit at once: removing a
unit only shrinks the classes of others, so this equals a one-at-a-time pass in record-key order and is
order-independent. Dropping a person-table record also drops the records joined to it (e.g. its lab results).

The fixpoint is a pre-check only; the gate's ``producer.person-k`` re-check over the written release is
authoritative. Aggregates only in the report.
"""
from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from pets_release.checks.producer.kanon import person_k_values

MAX_ROUNDS = 50


class SuppressionError(Exception):
    """Content-free: suppression could not be applied or exceeded its bound."""


def _rowmap(final: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"protected_row": [str(i) for i in range(len(final))], "original_record_id": final},
                        dtype=str)


def _person_k(tables, finals, contract, base_ctx, tmp: Path):
    for p in tmp.iterdir():
        p.unlink()
    for stem, df in tables.items():
        df.to_csv(tmp / f"{stem}.csv", index=False, encoding="utf-8", lineterminator="\n")
    ctx = {**base_ctx, "rowmaps": {s: _rowmap(f) for s, f in finals.items()}}
    return person_k_values(tmp, contract, ctx)


def k_summary(res, k: int) -> dict:
    """Aggregate per-person k distribution (no values)."""
    vals = sorted(res.per_person.values())
    buckets = {"lt_k": 0, "k_to_9": 0, "10_to_19": 0, "20_to_49": 0, "50_plus": 0}
    for v in vals:
        if v < k:
            buckets["lt_k"] += 1
        elif v < 10:
            buckets["k_to_9"] += 1
        elif v < 20:
            buckets["10_to_19"] += 1
        elif v < 50:
            buckets["20_to_49"] += 1
        else:
            buckets["50_plus"] += 1
    return {"k": k, "persons": len(vals), "unidentifiedUnits": res.unidentified,
            "minK": vals[0] if vals else None, "medianK": vals[len(vals) // 2] if vals else None,
            "belowK": buckets["lt_k"], "distribution": buckets}


def apply_suppression(tables: Mapping[str, pd.DataFrame], finals: Mapping[str, list[str]], *, policy, contract,
                      base_ctx: dict) -> tuple[dict, dict, dict, dict]:
    """Return (tables, finals, suppressed {stem: set of record keys}, report). Raises SuppressionError."""
    sup = policy.suppression
    tables = {s: df.reset_index(drop=True) for s, df in tables.items()}
    finals = {s: list(f) for s, f in finals.items()}
    suppressed = {s: set() for s in tables}
    if sup is None:
        return tables, finals, suppressed, {"method": "none"}
    if sup["unit"] != "persons" or sup["method"] != "local_suppression":
        raise SuppressionError("unsupported suppression method")
    k = sup["k"]
    if contract.get("k") != k:
        raise SuppressionError("suppression k differs from the contract k")
    person_t = base_ctx["person"]["table"]
    person_c = base_ctx["person"]["column"]
    pk = base_ctx["record_keys"][person_t]
    src = base_ctx["source"]
    if person_t not in tables:
        raise SuppressionError("person table not released")
    joins = [j for j in base_ctx["joins"] if j["ref_table"] == person_t and j["table"] in tables]
    # source lookups (in memory only)
    anchor_ref = {j["table"]: dict(zip(src[person_t][pk], src[person_t][j["ref_column"]])) for j in joins}
    child_ref = {j["table"]: dict(zip(src[j["table"]][base_ctx["record_keys"][j["table"]]], src[j["table"]][j["column"]]))
                 for j in joins}
    anchor_person = dict(zip(src[person_t][pk], src[person_t][person_c]))

    rounds = 0
    with tempfile.TemporaryDirectory(prefix="pets-suppress-") as td:
        tmp = Path(td)
        res = _person_k(tables, finals, contract, base_ctx, tmp)
        before = k_summary(res, k)
        units_before = len(res.per_person) + res.unidentified
        dropped_persons: set[str] = set()
        dropped_unidentified = 0
        while True:
            rows = sorted(set(res.below_rows) | set(res.unidentified_rows))
            if not rows:
                break
            rounds += 1
            if rounds > MAX_ROUNDS:
                raise SuppressionError("suppression did not reach a fixpoint")
            drop = sorted(finals[person_t][i] for i in rows)  # record-key ascending
            for a in drop:
                p = anchor_person.get(a, "")
                if isinstance(p, str) and p.strip():
                    dropped_persons.add(p)
                else:
                    dropped_unidentified += 1
            drop_set = set(drop)
            keep = [i for i, a in enumerate(finals[person_t]) if a not in drop_set]
            suppressed[person_t] |= drop_set
            tables[person_t] = tables[person_t].iloc[keep].reset_index(drop=True)
            finals[person_t] = [finals[person_t][i] for i in keep]
            for j in joins:
                t = j["table"]
                refs = {anchor_ref[t][a] for a in drop}
                keep_c = [i for i, r in enumerate(finals[t]) if child_ref[t][r] not in refs]
                gone = set(finals[t]) - {finals[t][i] for i in keep_c}
                suppressed[t] |= gone
                tables[t] = tables[t].iloc[keep_c].reset_index(drop=True)
                finals[t] = [finals[t][i] for i in keep_c]
            res = _person_k(tables, finals, contract, base_ctx, tmp)
        after = k_summary(res, k)
    units_suppressed = len(dropped_persons) + dropped_unidentified
    share = units_suppressed / units_before if units_before else 1.0
    report = {
        "method": sup["method"], "unit": sup["unit"], "k": k, "maxShare": sup["max_share"], "order": sup["order"],
        "rounds": rounds, "unitsBefore": units_before, "personsSuppressed": len(dropped_persons),
        "unidentifiedUnitsSuppressed": dropped_unidentified, "unitsSuppressed": units_suppressed,
        "share": round(share, 6), "rowsSuppressed": {s: len(v) for s, v in sorted(suppressed.items())},
        "personKBefore": before, "personKAfter": after,
        "recheck": {"privacyTargets": "gate re-runs producer.person-k on the written release",
                    "purposeChecks": "not_measured: measurer not wired in the walking skeleton"},
        "withinBound": share <= sup["max_share"],
    }
    return tables, finals, suppressed, report
