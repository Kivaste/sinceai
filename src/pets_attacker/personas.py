"""Two HEALTH-S1 attacker personas. Output is aggregate rates only.

broker:  fuzzy-links adversary records (news, social posts, directory) to released QIs.
insider: knows a target's ED visit date and municipality; looks for the visit.
Ground truth arrives as DataFrames from pets_attacker.truth; nothing here reads files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .linkage import QI, Matcher

AGGREGATE_KEYS = (
    "evaluated", "n_targets", "n_unique_claims", "reidentification_rate", "claim_precision",
    "share_candidate_set_le5", "median_candidate_set", "attribute_inference_rate",
    "attribute_inference_coverage", "attribute_inference_precision",
)


# Sampling frame of both personas (disclosed in the manifest by the bridge): at most MAX_SAMPLE targets per run,
# a seeded random sample (SEED) when there are more.
MAX_SAMPLE = 3000
SEED = 0


class MappingError(ValueError):
    """Row map or identity truth is incomplete, duplicated or inconsistent; scoring refused."""


def _empty(**kw) -> dict:
    out = {k: None for k in AGGREGATE_KEYS}
    out.update(evaluated=False, n_targets=0, n_unique_claims=0)
    out.update(kw)
    return out


def _compatible(p: str, o: str) -> bool:
    return p == o or o.startswith(p) or p.startswith(o)


class _World:
    """protected-row -> record/person, plus true sensitive values per person."""

    def __init__(self, protected, rowmap, identity, original, record_key, sensitive):
        if identity.shape[1] < 2:
            raise MappingError("identity truth needs record and person columns")
        id_map = dict(zip(identity.iloc[:, 0].astype(str), identity.iloc[:, 1].astype(str)))
        n = len(protected)
        if not {"protected_row", "original_record_id"} <= set(rowmap.columns):
            raise MappingError("row map needs columns protected_row and original_record_id")
        rows = rowmap["protected_row"].astype(str)
        recs = rowmap["original_record_id"].astype(str)
        if n == 0 or len(rowmap) != n:
            raise MappingError("row map must cover every protected row exactly once")
        if not rows.str.fullmatch(r"\d+").all() or set(rows.astype(int)) != set(range(n)) or rows.duplicated().any():
            raise MappingError("row map protected_row must be a complete, unique 0..n-1 index")
        if recs.duplicated().any() or (recs == "").any() or (recs == "nan").any():
            raise MappingError("row map original_record_id must be non-empty and unique")
        if not set(recs) <= set(id_map):
            raise MappingError("row map record ids missing from the identity truth")
        if original is not None and record_key and not set(recs) <= set(original[record_key].astype(str)):
            raise MappingError("row map record ids missing from the original table")
        self.person = np.full(n, "", dtype=object)
        self.record = np.full(n, "", dtype=object)
        for pr, rid in zip(rows.astype(int), recs):
            self.person[pr] = id_map[rid]
            self.record[pr] = rid
        self.persons = set(self.person[self.person != ""])
        self.id_map = id_map
        self.sens_true: dict = {}
        self.prot_sens = None
        if sensitive and original is not None and record_key and sensitive in original.columns and sensitive in protected.columns:
            for rid, v in zip(original[record_key].astype(str), original[sensitive].fillna("").astype(str)):
                if v:
                    self.sens_true.setdefault(id_map.get(rid, ""), set()).add(v)
            self.prot_sens = protected[sensitive].fillna("").astype(str).to_numpy(dtype=object)


class _Tally:
    def __init__(self):
        self.n = self.claims = self.correct = self.le5 = self.attr = self.attr_ok = 0
        self.sizes: list = []

    def add(self, world: _World, cand, used, target_person: str | None, in_data: bool, has_sens: bool):
        size = len(cand)
        if in_data:
            self.n += 1
            self.sizes.append(size)
            if 0 < size <= 5 and any(world.person[c] == target_person for c in cand):
                self.le5 += 1
        if size == 1 and used > 0:
            self.claims += 1
            if in_data and world.person[cand[0]] == target_person:
                self.correct += 1
        if in_data and has_sens and size > 0 and used > 0 and world.prot_sens is not None:
            vals = {v for v in world.prot_sens[cand] if v}
            if len(vals) == 1:
                self.attr += 1
                v = next(iter(vals))
                if any(_compatible(v, o) for o in world.sens_true.get(target_person, ())):
                    self.attr_ok += 1

    def result(self, has_sens: bool) -> dict:
        n = self.n
        return {
            "evaluated": n > 0,
            "n_targets": n,
            "n_unique_claims": self.claims,
            "reidentification_rate": round(self.correct / n, 4) if n else None,
            "claim_precision": round(self.correct / self.claims, 4) if self.claims else None,
            "share_candidate_set_le5": round(self.le5 / n, 4) if n else None,
            "median_candidate_set": float(np.median(self.sizes)) if self.sizes else None,
            "attribute_inference_rate": round(self.attr_ok / n, 4) if n and has_sens else None,
            "attribute_inference_coverage": round(self.attr / n, 4) if n and has_sens else None,
            "attribute_inference_precision": round(self.attr_ok / self.attr, 4) if self.attr else None,
        }


def broker_attack(adversary: pd.DataFrame, adv_truth: pd.DataFrame, protected: pd.DataFrame,
                  rowmap: pd.DataFrame, identity: pd.DataFrame, qis: list,
                  original: pd.DataFrame | None = None, record_key: str | None = None,
                  sensitive: str | None = None, max_adversary: int = MAX_SAMPLE, seed: int = SEED, rungs: dict | None = None) -> dict:
    """Data broker: link each adversary record to protected rows through fuzzy QI matching."""
    if not qis:
        return _empty()
    world = _World(protected, rowmap, identity, original, record_key, sensitive)
    if adv_truth is None or len(adv_truth) == 0 or adv_truth.shape[1] < 2:
        raise MappingError("adversary truth is empty")
    tmap = dict(zip(adv_truth.iloc[:, 0].astype(str), adv_truth.iloc[:, 1].astype(str)))
    adv = adversary.reset_index(drop=True)
    if len(adv) > max_adversary:
        adv = adv.iloc[np.sort(np.random.default_rng(seed).choice(len(adv), max_adversary, replace=False))]
    m = Matcher(protected.reset_index(drop=True), qis, rungs or {})
    tally = _Tally()
    has_sens = world.prot_sens is not None
    for r in adv.to_dict("records"):
        pid = tmap.get(str(r[adversary.columns[0]]), "")
        cand, used = m.candidates(r)
        tally.add(world, cand, used, pid, pid in world.persons, has_sens)
    return tally.result(has_sens)


def insider_attack(original: pd.DataFrame, protected: pd.DataFrame, rowmap: pd.DataFrame, identity: pd.DataFrame,
                   date_col: str, place_col: str, record_key: str, sensitive: str | None = None,
                   max_targets: int = MAX_SAMPLE, seed: int = SEED, rungs: dict | None = None) -> dict:
    """Municipal insider: knows the visit's date and municipality and looks for the matching visit."""
    world = _World(protected, rowmap, identity, original, record_key, sensitive)
    qis = []
    if date_col in protected.columns:
        qis.append(QI("time", ("date",), (date_col,), window=(0, 0)))
    if place_col in protected.columns:
        qis.append(QI("exact", ("place",), (place_col,)))
    if not qis:
        return _empty()
    in_release = set(world.record[world.record != ""])
    targets = original[original[record_key].astype(str).isin(in_release)].sort_values(record_key, kind="stable")
    if len(targets) > max_targets:
        targets = targets.iloc[np.sort(np.random.default_rng(seed).choice(len(targets), max_targets, replace=False))]
    m = Matcher(protected.reset_index(drop=True), qis, rungs or {})
    tally = _Tally()
    has_sens = world.prot_sens is not None
    for rid, d, p in zip(targets[record_key].astype(str), targets[date_col].fillna("").astype(str), targets[place_col].fillna("").astype(str)):
        cand, used = m.candidates({"date": d[:10], "place": p})
        tally.add(world, cand, used, world.id_map.get(rid, ""), True, has_sens)
    return tally.result(has_sens)



