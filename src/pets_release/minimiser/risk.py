"""Risk vector and per-person k for one candidate, using ticket 11's production per-person k.

The candidate's released QI columns are written (QI columns only) to a temporary folder with identity row
maps, and ``person_k_values`` (inner loop) or the registered ``producer.person-k`` / ``producer.row-k``
checks through 04's runner (final re-check) read them. Nothing here is logged except aggregate shares.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from pets_release.checks import all_checks, run_checks
from pets_release.checks.producer.kanon import PERSON_K, ROW_K, person_k_values
from pets_release.ladders import WITHHELD, output_column

BUILTIN_COMPONENTS = frozenset(
    {"qi_k_shortfall", "qi_unique_rate", "join_derived_qi", "direct_identifier_leak", "attribute_inference"}
)
K_COMPONENTS = frozenset({"qi_k_shortfall", "qi_unique_rate"})


def k_target(policy) -> int | None:
    ks = [t["k"] for t in policy.privacy_targets if t["kind"] == "k_anonymity"]
    if len(ks) > 1:
        raise ValueError("more than one k target")
    return ks[0] if ks else None


def contract_for(policy, plan: list, k: int | None) -> dict:
    """Minimal release contract for the k checks: released QIs (by output name) and token columns."""
    by_key = {(e["table"], e["column"]): e for e in plan}
    qi = []
    for q in policy.qi:
        e = by_key[(q["table"], q["column"])]
        if e["rung"] != WITHHELD:
            qi.append({"table": q["table"], "column": output_column(e), "derived_from": f"{q['table']}.{q['column']}"})
    tokens = [{"table": e["table"], "column": e["column"], "scope": "release"}
              for e in plan if e["rung"] == "id.pseudonym"]
    out = {"files": {}, "qi": sorted(qi, key=lambda x: (x["table"], x["column"])),
           "tokens": sorted(tokens, key=lambda x: (x["table"], x["column"]))}
    if k is not None:
        out["k"] = k
    return out


def _write(folder: Path, prot: Mapping[str, pd.DataFrame], contract: dict, source, kspec) -> dict:
    """Write QI columns of each QI table (plus the person table) and identity row maps; return rowmaps."""
    qcols: dict[str, list[str]] = {}
    for q in contract["qi"]:
        qcols.setdefault(q["table"], []).append(q["column"])
    person_t = kspec["person"]["table"]
    rowmaps = {}
    for t in sorted(set(qcols) | {person_t}):
        if t not in prot:
            continue
        df = prot[t]
        cols = sorted(qcols.get(t, []))
        rk = kspec["record_keys"][t]
        keys = source[t].loc[df.index, rk].tolist()
        rowmaps[t] = pd.DataFrame({"protected_row": [str(i) for i in range(len(df))], "original_record_id": keys},
                                  dtype=str)
        if cols:
            df[cols].to_csv(folder / f"{t}.csv", index=False)
        else:  # person table without its own QIs: one constant column keeps the row count readable
            pd.DataFrame({"_": ["0"] * len(df)}, dtype=str).to_csv(folder / f"{t}.csv", index=False)
    return rowmaps


def _context(source, rowmaps, kspec, k):
    return {"k": k, "source": source, "rowmaps": rowmaps, "record_keys": dict(kspec["record_keys"]),
            "person": dict(kspec["person"]), "joins": [dict(j) for j in kspec.get("joins", [])]}


def person_k(prot, plan, policy, source, kspec, k):
    """(PersonK, contract) from ticket 11's production per-person k. With no QI released every identified
    person shares one class and an unidentified record is still a hit (the person table is always written)."""
    contract = contract_for(policy, plan, k)
    with tempfile.TemporaryDirectory(prefix="pets-min-") as d:
        rowmaps = _write(Path(d), prot, contract, source, kspec)
        res = person_k_values(d, contract, _context(source, rowmaps, kspec, k))
    return res, contract


def gate_k(prot, plan, policy, source, kspec, k) -> dict:
    """Run the registered producer.person-k and producer.row-k checks (04's runner) on the candidate. With no
    QI released only person-k applies (row-k has no QI rows); the caller requires exactly ``k_checks_for``."""
    contract = contract_for(policy, plan, k)
    names = k_checks_for(contract)
    checks = [c for c in all_checks() if c.name in names]
    if len(checks) != len(names):
        raise RuntimeError("k checks not registered")
    with tempfile.TemporaryDirectory(prefix="pets-min-") as d:
        rowmaps = _write(Path(d), prot, contract, source, kspec)
        res = run_checks(d, contract, _context(source, rowmaps, kspec, k), checks=checks)
    return res.summary()


def k_checks_for(contract) -> tuple:
    return (PERSON_K, ROW_K) if contract["qi"] else (PERSON_K,)


def risk_vector(policy, plan, prot, source, kspec, k) -> tuple[dict, object]:
    """Built-in risk components (shares in [0, 1]) and the PersonK result (or None)."""
    by_key = {(e["table"], e["column"]): e for e in plan}
    released = {key for key, e in by_key.items() if e["rung"] != WITHHELD}
    out: dict[str, float] = {}
    pk = None
    wanted = set(policy.risk_vector)
    if wanted & K_COMPONENTS:
        pk, _ = person_k(prot, plan, policy, source, kspec, k)
        if pk is None:
            out["qi_k_shortfall"] = out["qi_unique_rate"] = 0.0
        else:
            n = len(pk.per_person) + pk.unidentified
            below = sum(1 for v in pk.per_person.values() if v < k) + pk.unidentified
            uniq = sum(1 for v in pk.per_person.values() if v == 1) + pk.unidentified
            out["qi_k_shortfall"] = below / n if n else 1.0
            out["qi_unique_rate"] = uniq / n if n else 1.0
    if "join_derived_qi" in wanted:
        jq = [(q["table"], q["column"]) for q in policy.qi if q.get("join_via")]
        out["join_derived_qi"] = (sum(1 for x in jq if x in released) / len(jq)) if jq else 0.0
    if "direct_identifier_leak" in wanted:
        di = list(policy.direct_identifiers)
        out["direct_identifier_leak"] = (sum(1 for x in di if x in released) / len(di)) if di else 0.0
    if "attribute_inference" in wanted:
        out["attribute_inference"] = _homogeneity(policy, by_key, prot, kspec)
    return {c: float(out[c]) for c in policy.risk_vector if c in out}, pk


def _homogeneity(policy, by_key, prot, kspec) -> float:
    """Proxy: share of person-table rows whose released-QI class has a single released diagnosis value."""
    t = kspec["person"]["table"]
    df = prot.get(t)
    if df is None or len(df) == 0:
        return 0.0
    sens = [output_column(e) for (tt, _), e in sorted(by_key.items())
            if tt == t and e["rung"] != WITHHELD and policy.floors[(tt, e["column"])].family == "icd10"]
    if not sens:
        return 0.0
    qcols = sorted(output_column(by_key[(q["table"], q["column"])]) for q in policy.qi
                   if q["table"] == t and by_key[(q["table"], q["column"])]["rung"] != WITHHELD)
    if not qcols:
        return 0.0
    g = df[qcols + sens].astype(str)
    homo = None
    for s in sens:
        h = g.groupby(qcols, sort=False)[s].transform("nunique") == 1
        homo = h if homo is None else (homo | h)
    return float(homo.mean())
