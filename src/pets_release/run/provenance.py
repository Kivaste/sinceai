"""Reconstruct every released column from the source through its declared mapping (#106 round 2, the #62 escape).

Used by the producer context (gate and ``verify --full``). The declared mapping of a released column is its source
(``params.derived_from`` or its own name, same table) and its contract ``params.rung``; rung parameters are the
policy-supported ones the run uses (the hand plan's, else the search's defaults: ``minimiser.rebuild_plan``'s rule).
The source tables are generalised with the release's own pseudonym keys, and released rows are aligned to source
records by the row maps (record-key tokens) or, for a table without one, by the join to the retained person-table
records (rows compared as a multiset). A released column that is not reproduced exactly has no trusted source: it
is returned so the caller counts it as a quasi-identifier (person-k then refuses unless it is a contract QI and k
holds over it as released). Values stay in memory; only (table, column) names leave.
"""
from __future__ import annotations

import json
from collections.abc import Mapping

import pandas as pd

from pets_release.ladders import WITHHELD, apply, output_column
from pets_release.minimiser.kit import params_from_plan
from pets_release.minimiser.search import rung_params


def _declared(contract, released) -> dict:
    """(table, released column) -> (source column, rung) as declared; unusable declarations are absent."""
    files = (contract or {}).get("files") or {}
    out = {}
    for t, df in released.items():
        cols = (files.get(f"{t}.csv") or {}).get("columns") or {}
        for c in df.columns:
            spec = cols.get(c)
            params = spec.get("params") if isinstance(spec, Mapping) else None
            if not isinstance(params, Mapping) or not isinstance(params.get("rung"), str):
                continue
            source_ref = params.get("derived_from")
            if isinstance(source_ref, str) and source_ref:
                st, _, sc = source_ref.rpartition(".")
                if st and st != t:
                    continue
            else:
                sc = c
            out[(t, c)] = (sc, params["rung"])
    return out


def unreproduced(*, policy, source: Mapping[str, pd.DataFrame], released: Mapping[str, pd.DataFrame], contract,
                 rowmaps: Mapping[str, pd.DataFrame], keys, spec: Mapping) -> list[tuple[str, str]]:
    """Sorted (table, released column) of every released column that its declared mapping does not reproduce."""
    from pets_release.policy import hand_plan

    every = sorted((t, str(c)) for t, df in released.items() for c in df.columns)
    declared = _declared(contract, released)
    params = params_from_plan(hand_plan(policy.scenario))
    plan, owner = [], {}
    for (t, c) in sorted(policy.floors):
        fl = policy.floors[(t, c)].rung
        e = {"table": t, "column": c, "rung": WITHHELD, "params": {}, "floor": fl}
        outs = [k for k, (sc, _) in declared.items() if k[0] == t and sc == c]
        if len(outs) == 1:
            rung = declared[outs[0]][1]
            alt = (policy.alt_floors or {}).get((t, c))
            pr = rung_params(policy, params, (t, c), rung) if rung not in ("text.redacted", WITHHELD) else None
            if pr is not None:
                cand = dict(e, rung=rung, params=json.loads(json.dumps(pr)), floor=alt if rung == alt else fl)
                if output_column(cand) == outs[0][1]:
                    e = cand
                    owner[outs[0]] = c
        plan.append(e)
    if not owner:
        return every
    try:
        recon = apply(plan, {t: source[t] for t in sorted({t for t, _ in policy.floors}) if t in source}, keys)
    except Exception:  # noqa: BLE001 - a mapping the ladders refuse reproduces nothing (content-free)
        return every
    bad = {k for k in every if k not in owner}
    person_t = spec["person"]["table"]
    for t, df in sorted(released.items()):
        cols = [c for c in df.columns if (t, str(c)) in owner]
        if not cols:
            continue
        rt = recon.get(t)
        rk = spec["record_keys"].get(t)
        if rt is None or rk is None or any(c not in rt.columns for c in cols):
            bad |= {(t, c) for c in cols}
            continue
        src = source[t]
        rm = rowmaps.get(t)
        if rm is not None and len(rm) == len(df):
            pos = dict(zip(src[rk].tolist(), src.index.tolist()))
            labels = [pos.get(o) for o in rm["original_record_id"].tolist()]
            if any(lb is None for lb in labels):
                bad |= {(t, c) for c in cols}
                continue
            for c in cols:
                if rt.loc[labels, c].astype(str).tolist() != df[c].astype(str).tolist():
                    bad.add((t, c))
            continue
        joins = [j for j in spec.get("joins") or [] if j["table"] == t and j["ref_table"] == person_t]
        prm = rowmaps.get(person_t)
        if len(joins) != 1 or prm is None:
            bad |= {(t, c) for c in cols}
            continue
        j = joins[0]
        ps = source[person_t]
        pk = spec["record_keys"][person_t]
        kept = set(ps.loc[ps[pk].isin(set(prm["original_record_id"])), j["ref_column"]])
        labels = src.index[src[j["column"]].isin(kept)].tolist()
        want = rt.loc[labels, cols].astype(str)
        got = df[cols].astype(str)
        for c in cols:
            if sorted(want[c].tolist()) != sorted(got[c].tolist()):
                bad.add((t, c))
        if sorted(map(tuple, want.values.tolist())) != sorted(map(tuple, got.values.tolist())):
            bad |= {(t, c) for c in cols}
    return sorted(bad)
