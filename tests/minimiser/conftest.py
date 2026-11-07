"""Synthetic fixture for minimiser tests: hand-made rows, nothing copied from the kit.

Two tables: ``visits`` (person table, 3 visits per person) and ``labs`` (joins to visits by visit_id).
Fake purpose checks read only the protected tables' shapes and value forms, so the search's
behaviour (withhold, coarsen, sacrifice, suppress) is predictable without any kit code.
"""

from __future__ import annotations

import hashlib
import re
import types

import pandas as pd
import pytest

from pets_release.policy.model import FieldFloor, ScenarioPolicy

TOWNS = ["Ta", "Tb", "Tc", "Td", "Te", "Tf"]


def _tables():
    v = {k: [] for k in ("visit_id", "pid", "name", "dob", "sex", "town", "ts", "dx", "flag", "spare")}
    lab = {k: [] for k in ("lab_id", "visit_id", "val", "sampled_ts")}
    dxs = ["J18.9", "I21.4", "S52.5", "K35.8"]
    # 24 persons in two age decades (p < 12, p >= 12); towns Ta/Tb hold 3 persons per decade each, Tc..Tf
    # fewer (below k=3 unless grouped); P24 is alone in a third decade (suppressed at the end).
    town_of = {0: "Ta", 1: "Ta", 2: "Ta", 3: "Tb", 4: "Tb", 5: "Tb", 6: "Tc", 7: "Tc", 8: "Td", 9: "Td",
               10: "Te", 11: "Tf"}
    n = 0
    for p in range(25):
        year = 1940 if p == 24 else (1980 if p < 12 else 1990)
        for j in range(3):
            vid = f"V{n:03d}"
            v["visit_id"].append(vid)
            v["pid"].append(f"P{p:02d}")
            v["name"].append(f"Name{p:02d}")
            v["dob"].append(f"{year}-0{1 + p % 9}-1{p % 9}")
            v["sex"].append("F" if p % 2 else "M")
            v["town"].append("Ta" if p == 24 else town_of[p % 12])
            v["ts"].append(f"2025-0{1 + j}-{10 + p % 9} {'14' if j == 1 else '08'}:{p % 6}5:00")
            v["dx"].append(dxs[(p + j) % 4])
            v["flag"].append(str((p + j) % 2))
            v["spare"].append(str(p * 7 + j))
            lab["lab_id"].append(f"L{n:03d}")
            lab["visit_id"].append(vid)
            lab["val"].append(str(10 + n % 13))
            lab["sampled_ts"].append(f"2025-0{1 + j}-{10 + p % 9} 09:{n % 6}0:00")
            n += 1
    return {"visits": pd.DataFrame(v, dtype=str), "labs": pd.DataFrame(lab, dtype=str)}


FLOORS = {
    ("labs", "lab_id"): FieldFloor("identifier", "id.pseudonym", "record key"),
    ("labs", "sampled_ts"): FieldFloor("timestamp", "ts.exact", "join-derived QI"),
    ("labs", "val"): FieldFloor("numeric", "num.exact", "measure"),
    ("labs", "visit_id"): FieldFloor("identifier", "id.pseudonym", "join"),
    ("visits", "dob"): FieldFloor("age", "age.band5", "QI"),
    ("visits", "dx"): FieldFloor("icd10", "icd.full", "diagnosis"),
    ("visits", "flag"): FieldFloor("categorical", "keep", "outcome"),
    ("visits", "name"): FieldFloor("identifier", "withheld", "direct identifier"),
    ("visits", "pid"): FieldFloor("identifier", "withheld", "linkage handle"),
    ("visits", "sex"): FieldFloor("categorical", "keep", "QI"),
    ("visits", "spare"): FieldFloor("numeric", "num.exact", "unused measure"),
    ("visits", "town"): FieldFloor("geo", "geo.full", "QI"),
    ("visits", "ts"): FieldFloor("timestamp", "ts.exact", "QI"),
    ("visits", "visit_id"): FieldFloor("identifier", "id.pseudonym", "join"),
}
CHECKS = ("U-AGE", "U-DX", "U-FLAG", "U-HOUR", "U-JOIN", "U-TOWN")
TOWN_SACRIFICE = {"check": "U-TOWN", "floor_score": 0.4, "reason": "group towns to reach k",
                  "via": [{"table": "visits", "column": "town"}]}


def make_policy(sacrifices=(TOWN_SACRIFICE,), max_share=0.25, joint=None, k=3):
    return ScenarioPolicy(
        scenario="SYN-S1",
        dataset="syn",
        purpose_checks=CHECKS,
        privacy_targets=({"id": "qi-k", "kind": "k_anonymity", "k": k, "unit": "persons", "over": "every released QI"},),
        floors=dict(FLOORS),
        direct_identifiers=(("visits", "name"), ("visits", "pid")),
        qi=(
            {"table": "visits", "column": "dob", "derived": "age_band"},
            {"table": "visits", "column": "sex", "derived": "sex"},
            {"table": "visits", "column": "town", "derived": "town"},
            {"table": "visits", "column": "ts", "derived": "ts"},
            {"table": "labs", "column": "sampled_ts", "derived": "sampled_ts", "join_via": ["visits", "visit_id"]},
        ),
        risk_vector=("qi_k_shortfall", "qi_unique_rate", "join_derived_qi", "direct_identifier_leak",
                     "attribute_inference"),
        sacrifices=tuple(sacrifices),
        joint_qi_moves=joint if joint is not None else (
            ({"table": "visits", "column": "dob", "rung": "age.band10"},
             {"table": "visits", "column": "town", "rung": "geo.topn"}),
        ),
        linked=((("labs", "visit_id"), ("visits", "visit_id")),),
        param_minimums={("visits", "town"): {"rung": "geo.topn", "param": "n", "min": 2}},
        alt_floors={("visits", "pid"): "id.pseudonym"},
        suppression={"method": "local_suppression", "unit": "persons", "k": k, "max_share": max_share,
                     "order": "record_key_ascending_iterate_to_fixpoint",
                     "then": "full_recheck_of_every_purpose_check_and_privacy_target"},
    )


KSPEC = {
    "person": {"table": "visits", "column": "pid"},
    "record_keys": {"visits": "visit_id", "labs": "lab_id"},
    "joins": [{"table": "labs", "column": "visit_id", "ref_table": "visits", "ref_column": "visit_id"}],
}
PARAMS = {("visits", "dob"): {"age.band5": {"ref_column": "ts", "output": "age_band"},
                               "age.band10": {"ref_column": "ts", "output": "age_band"}}}


class FakeKeys:
    def token(self, value, label="RECORD_KEY"):
        return hashlib.sha256(f"syn\0{label}\0{value}".encode()).hexdigest()


def _ok(score):
    return {"score": float(score), "status": "ok"}


NA = {"score": None, "status": "not_answerable"}


def fake_purpose(task, orig, prot):
    v = prot.get("visits")
    o = orig["visits"]
    if v is None:
        return dict(NA)
    if task == "U-FLAG":
        return _ok(1.0) if "flag" in v.columns else dict(NA)
    if task == "U-AGE":
        return _ok(1.0) if "age_band" in v.columns else dict(NA)
    if task == "U-HOUR":
        if "ts" not in v.columns or not v["ts"].str.contains(":").all():
            return dict(NA)
        return _ok(1.0)
    if task == "U-TOWN":
        if "town" not in v.columns:
            return dict(NA)
        return _ok(min(1.0, v["town"].nunique() / o["town"].nunique()))
    if task == "U-DX":
        if "dx" not in v.columns:
            return dict(NA)
        return _ok(v["dx"].map(lambda s: bool(re.match(r"^[A-Z]\d{2}", s))).mean())
    if task == "U-JOIN":
        lab = prot.get("labs")
        return _ok(1.0) if lab is not None and "visit_id" in lab.columns and "visit_id" in v.columns else dict(NA)
    raise AssertionError("unknown task")


@pytest.fixture
def syn():
    return types.SimpleNamespace(
        tables=_tables(), policy=make_policy, kspec=KSPEC, params=PARAMS, keys=FakeKeys(), purpose=fake_purpose,
        checks=CHECKS, sacrifice=TOWN_SACRIFICE,
    )
