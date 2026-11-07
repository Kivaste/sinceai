"""`pets-release run` without `--plan` keeps every released table's record key (#128), through the real CLI.

Rule: every released table keeps its record key as its release-scope keyed pseudonym (the invariant the producer
context, the scorecard row maps and the submission packager recompute row maps from); the search treats a
candidate that drops it as infeasible.

Rows (trigger -> result):
  default-plan HEALTH-S1 run (k reachable)  -> exit 0; every released table's header has its record-key column,
                                               and the manifest contract lists it as a release-scope token
  (before #128)                              -> lab_results released without lab_id; the packager then refuses
                                               the release with rowmap_unverifiable
"""
from __future__ import annotations

import csv
import json

import pytest
from run_helpers import CREATED, build_kit, cli, grouped_qis

# HEALTH-S1 record keys (kit schema; spec #1), an independent literal rather than the code's own table
RECORD_KEYS = {"ed_visits": "visit_id", "lab_results": "lab_id", "clinical_notes": "note_id",
               "published_weekly_stats": "stat_id"}


@pytest.fixture(scope="module")
def released(tmp_path_factory):
    base = tmp_path_factory.mktemp("reckeys")
    kit = build_kit(base / "kit", grouped_qis)
    out = base / "out" / "rel"
    proc = cli("run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED)
    return out, proc


def _header(path):
    with path.open(encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


def test_default_plan_releases_every_record_key_as_a_release_token(released):
    out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    tokens = {(t["table"], t["column"]): t["scope"] for t in m["contract"]["tokens"]}
    tables = sorted(p.stem for p in out.glob("*.csv"))
    assert "lab_results" in tables and "ed_visits" in tables  # H-U7 needs both
    missing = [f"{t}.{RECORD_KEYS[t]}" for t in tables if RECORD_KEYS[t] not in _header(out / f"{t}.csv")]
    assert missing == [], "released without its record key: " + ",".join(missing)
    untokened = [f"{t}.{RECORD_KEYS[t]}" for t in tables if tokens.get((t, RECORD_KEYS[t])) != "release"]
    assert untokened == [], "record key not a release-scope token: " + ",".join(untokened)
