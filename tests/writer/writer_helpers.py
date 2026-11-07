"""Fixture candidate, synthetic mini kit and producer context for the writer tests.

Built from ticket 02's hand-made synthetic fixture; nothing is copied from the kit.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "manifest"))

import build_fixture as fx

from pets_release.kit import Kit
from pets_release.pseudonym import MasterKey
from pets_release.run.context import person_normaliser
from pets_release.writer import Candidate, ProtectedTable
from pets_release.writer.assemble import NARRATIVE_KEYS

MASTER = MasterKey(fx.FIXTURE_MASTER_KEY)
KIT_TABLES = ("clinical_notes", "ed_visits", "lab_results")  # clinical_notes is withheld from the release


def _frame(data: bytes) -> pd.DataFrame:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    return pd.DataFrame(rows[1:], columns=rows[0], dtype=object)


def make_candidate(**over) -> Candidate:
    files = fx.tables()
    tables = []
    for name, data in sorted(files.items()):
        frame = _frame(data)
        stem = name[:-4]
        # Reverse the order so the writer's sort is observable; source keys are synthetic labels.
        frame = frame.iloc[::-1].reset_index(drop=True)
        final = tuple(f"src-{stem}-{i}" for i in range(len(frame)))
        tables.append(ProtectedTable(name=name, frame=frame, final=final,
                                     suppressed=frozenset({f"src-{stem}-dropped"})))
    full = fx.manifest(files)
    kw = {"scenario": fx.SCENARIO, "recipient": fx.RECIPIENT, "tables": tuple(tables), "contract": fx.contract(),
          "tool_revision": fx.TOOL_REVISION, "created": fx.CREATED,
          "narrative": {k: full[k] for k in NARRATIVE_KEYS},
          "lexicon_digests": dict(full["bindings"]["lexiconDigests"])}  # #132: text columns need the lexicon
    kw.update(over)
    return Candidate(**kw)


def source_tables(cand) -> dict[str, pd.DataFrame]:
    """Synthetic source tables matching the candidate's lineage: one person per visit, labs joined to visits."""
    by = {t.name: t for t in cand.tables}
    visits, labs = by["ed_visits.csv"], by["lab_results.csv"]
    vkeys = list(visits.final) + sorted(visits.suppressed)
    lkeys = list(labs.final) + sorted(labs.suppressed)
    return {
        "clinical_notes": pd.DataFrame({"note_key": ["note-0", "note-1"], "visit_key": vkeys[:2],
                                        "note_text": ["synthetic note", "synthetic note"]}, dtype=str),
        "ed_visits": pd.DataFrame({"visit_key": vkeys,
                                   "patient_id": [f"synthetic-person-{i:03d}" for i in range(len(vkeys))],
                                   "patient_name": [f"Synthetic Person {i:03d}" for i in range(len(vkeys))]},
                                  dtype=str),
        "lab_results": pd.DataFrame({"lab_key": lkeys, "visit_key": [vkeys[i % len(vkeys)] for i in range(len(lkeys))]},
                                    dtype=str),
    }


def make_kit(root: Path, cand=None) -> Kit:
    """A minimal synthetic kit: metadata/scenarios.json plus data/health/<table>.csv for KIT_TABLES."""
    cand = cand or make_candidate()
    (root / "metadata").mkdir(parents=True, exist_ok=True)
    (root / "metadata" / "scenarios.json").write_text(
        json.dumps([{"id": "HEALTH-S1", "dataset": "health"}, {"id": "CS-S1", "dataset": "customer_service"}]),
        encoding="utf-8")
    d = root / "data" / "health"
    d.mkdir(parents=True, exist_ok=True)
    for name, frame in source_tables(cand).items():
        frame.to_csv(d / f"{name}.csv", index=False, lineterminator="\n")
    return Kit(root)


def producer_context(cand) -> dict:
    """Context ticket 11's producer checks read (k, source, rowmaps, record keys, person, joins, ids, keys)."""
    by = {t.name: t for t in cand.tables}

    def rowmap(t):  # the writer sorts rows; the checks need the writer's row order
        pairs = sorted(zip(t.frame.itertuples(index=False, name=None), t.final, strict=True))
        return pd.DataFrame({"protected_row": [str(i) for i in range(len(pairs))],
                             "original_record_id": [k for _, k in pairs]}, dtype=str)

    src = source_tables(cand)
    return {
        "k": 5,
        "source": {"ed_visits": src["ed_visits"], "lab_results": src["lab_results"]},
        "rowmaps": {"ed_visits": rowmap(by["ed_visits.csv"]), "lab_results": rowmap(by["lab_results.csv"])},
        "record_keys": {"ed_visits": "visit_key", "lab_results": "lab_key"},
        "person": {"table": "ed_visits", "column": "patient_id", "normalise": person_normaliser()},
        "joins": [{"table": "lab_results", "column": "visit_key", "ref_table": "ed_visits",
                   "ref_column": "visit_key"}],
        "identifiers": [{"table": "ed_visits", "column": "patient_id"},
                        {"table": "ed_visits", "column": "patient_name"}],
        "keys": [fx.FIXTURE_MASTER_KEY],
    }
