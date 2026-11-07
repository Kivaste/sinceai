"""Synthetic kit for the measurer: one customer-service table, a catalog, a scenario, published baselines.

Hand-made rows only. The baseline numbers here are invented for the fixture; the real kit's published
numbers are checked in test_real_kit.py against the kit's own docs table.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from pets_release.kiteval import Lineage

ROWS = [("c1", "refund", "300"), ("c2", "refund", "500"), ("c3", "billing", "200"), ("c4", "billing", "400")]
COLS = ("conversation_id", "intent", "handle_time_s")
SCENARIO = "TEST-S1"

BENCH = {
    "generated": "x",
    "baselines": {
        "B0_customer_service": {"privacy": 0.25, "utility": 1.0, "composite": 0.4, "worst_reid": 0.5,
                                "residual_identifiers": 0.0, "utility_tasks": {"CS-U4": 1.0},
                                "utility_by_scenario": {SCENARIO: 1.0}, "runtime_s": 1.0},
        "B2_customer_service": {"privacy": 0.5, "utility": 0.75, "composite": 0.6, "worst_reid": 0.25,
                                "residual_identifiers": 0.0, "utility_tasks": {"CS-U4": None},
                                "utility_by_scenario": {SCENARIO: 0.75}, "runtime_s": 1.0},
        "B2K_customer_service": {"privacy": 0.75, "utility": 0.5, "composite": 0.6, "worst_reid": 0.0,
                                 "residual_identifiers": 0.0, "utility_tasks": {"CS-U4": 0.5},
                                 "utility_by_scenario": {SCENARIO: 0.5}, "runtime_s": 1.0},
    },
}


def write_table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(COLS), dtype=str).to_csv(path, index=False)


@pytest.fixture
def kit(tmp_path):
    root = tmp_path / "kit"
    (root / "metadata").mkdir(parents=True)
    (root / "metadata" / "scenarios.json").write_text(
        json.dumps([{"id": SCENARIO, "dataset": "customer_service", "utility_requirements": ["CS-U4"]}]),
        encoding="utf-8")
    (root / "metadata" / "field_catalog.csv").write_text(
        "dataset,table,column,privacy_role,data_kind,subtype\n"
        "customer_service,conversations,conversation_id,record_key,identifier,id\n", encoding="utf-8")
    write_table(root / "data" / "customer_service" / "conversations.csv", ROWS)
    (root / "results").mkdir()
    (root / "results" / "benchmark.json").write_text(json.dumps(BENCH), encoding="utf-8")
    return root


@pytest.fixture
def release(tmp_path):
    out = tmp_path / "release" / "customer_service"
    write_table(out / "conversations.csv", ROWS)
    rm = tmp_path / "scoring" / "rowmap_conversations.csv"
    rm.parent.mkdir(parents=True)
    pd.DataFrame({"protected_row": range(4), "original_record_id": [r[0] for r in ROWS]}).to_csv(rm, index=False)
    return out, {"conversations": rm}, tmp_path / "scoring" / "measure-out"


@pytest.fixture
def args(kit, release):
    prot, rms, out = release
    return {"root": kit, "original_dir": kit / "data" / "customer_service", "protected_dir": prot,
            "rowmaps": rms, "lineage": {"conversations": Lineage(tuple(r[0] for r in ROWS), frozenset())},
            "record_keys": {"conversations": "conversation_id"}, "out_dir": out}
